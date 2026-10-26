from datetime import UTC, datetime

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from apps.belohnung import selectors, services
from apps.belohnung.models import Einloeseantrag, Status, TaschengeldLimit
from apps.ereignisse.models import Ereignis
from apps.kern.models import AuditEintrag
from apps.punkte import selectors as punkte
from apps.punkte.models import Art, Buchung

from .conftest import gutschrift

pytestmark = pytest.mark.django_db


def test_offener_antrag_reserviert_guthaben(anna, suesses):
    gutschrift(anna, 50)
    services.antrag_stellen(anna, suesses)
    assert punkte.guthaben(anna) == 50
    assert punkte.reserviert(anna) == 30
    assert punkte.verfuegbar(anna) == 20


def test_ueberbeantragen_unmoeglich(anna, suesses):
    gutschrift(anna, 50)
    services.antrag_stellen(anna, suesses)
    with pytest.raises(services.GuthabenReichtNicht, match="10 Punkte"):
        services.antrag_stellen(anna, suesses)
    assert Einloeseantrag.objects.count() == 1


def test_genau_verfuegbares_guthaben_reicht(anna, suesses):
    gutschrift(anna, 30)
    services.antrag_stellen(anna, suesses)


def test_nur_kinder_stellen_antraege(mama, suesses):
    with pytest.raises(PermissionDenied):
        services.antrag_stellen(mama, suesses)


def test_inaktive_belohnung_nicht_beantragbar(anna, suesses, mama):
    gutschrift(anna, 50)
    services.belohnung_aktiv_setzen(suesses, False, von=mama)
    with pytest.raises(services.BelohnungInaktiv):
        services.antrag_stellen(anna, suesses)


def test_antrag_ereignis_audit_und_snapshot(anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    suesses.preis_punkte = 99
    suesses.save()
    antrag.refresh_from_db()
    assert (antrag.titel_snapshot, antrag.preis_snapshot) == ("Testsüßes", 30)
    ereignis = Ereignis.objects.get(typ_id="belohnung.antrag")
    assert (ereignis.kind_id, ereignis.akteur_id) == (anna.pk, anna.pk)
    assert ereignis.daten["belohnung"] == "Testsüßes"
    eintrag = AuditEintrag.objects.get(aktion="belohnung.beantragt")
    assert eintrag.kind_id == anna.pk
    assert eintrag.akteur_name == "Anna"


def test_bestaetigen_bucht_genau_einmal(anna, mama, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    for _ in range(3):  # Doppelklick
        services.bestaetigen(antrag, von=mama)
    buchungen = Buchung.objects.filter(art=Art.EINLOESUNG)
    assert buchungen.count() == 1
    buchung = buchungen.get()
    assert (buchung.guthaben_delta, buchung.xp_delta) == (-30, 0)
    assert buchung.idempotenz_schluessel == f"antrag:{antrag.pk}"
    assert buchung.quelle_modul == "belohnung"
    antrag.refresh_from_db()
    assert (antrag.status, antrag.buchung_id) == (Status.BESTAETIGT, buchung.pk)
    assert antrag.entschieden_von == mama
    assert punkte.guthaben(anna) == 20
    assert punkte.reserviert(anna) == 0  # Reservierung wurde zur Buchung, nicht doppelt gezählt
    assert Ereignis.objects.filter(typ_id="belohnung.bestaetigt").count() == 1
    eintrag = AuditEintrag.objects.get(aktion="belohnung.bestaetigt")
    assert eintrag.akteur_name == "Mama"


def test_ablehnen_bucht_nicht_und_gibt_reservierung_frei(anna, mama, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    services.ablehnen(antrag, von=mama, grund="Heute nicht")
    antrag.refresh_from_db()
    assert (antrag.status, antrag.ablehnungsgrund, antrag.buchung_id) == (
        Status.ABGELEHNT,
        "Heute nicht",
        None,
    )
    assert not Buchung.objects.filter(art=Art.EINLOESUNG).exists()
    assert punkte.verfuegbar(anna) == 50
    assert Ereignis.objects.filter(typ_id="belohnung.abgelehnt").count() == 1
    with pytest.raises(services.AntragNichtOffen):
        services.bestaetigen(antrag, von=mama)
    assert not Buchung.objects.filter(art=Art.EINLOESUNG).exists()


def test_kind_darf_nicht_entscheiden(anna, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    with pytest.raises(PermissionDenied):
        services.bestaetigen(antrag, von=anna)
    with pytest.raises(PermissionDenied):
        services.ablehnen(antrag, von=anna)


def test_zurueckziehen(anna, ben, mama, suesses):
    gutschrift(anna, 50)
    antrag = services.antrag_stellen(anna, suesses)
    with pytest.raises(PermissionDenied):
        services.zurueckziehen(antrag, kind=ben)
    services.zurueckziehen(antrag, kind=anna)
    antrag.refresh_from_db()
    assert antrag.status == Status.ZURUECKGEZOGEN
    assert punkte.verfuegbar(anna) == 50
    with pytest.raises(services.AntragNichtOffen):
        services.bestaetigen(antrag, von=mama)
    assert not Buchung.objects.filter(art=Art.EINLOESUNG).exists()


def test_bestaetigen_scheitert_bei_fehlendem_guthaben_ohne_nebenwirkung(anna, mama, suesses):
    original = gutschrift(anna, 30)
    antrag = services.antrag_stellen(anna, suesses)
    from apps.punkte import services as punkte_services

    punkte_services.gegenbuchen(original, von=mama, begruendung="Korrektur")
    with pytest.raises(services.GuthabenReichtNicht):
        services.bestaetigen(antrag, von=mama)
    antrag.refresh_from_db()
    assert antrag.status == Status.OFFEN
    assert not Ereignis.objects.filter(typ_id="belohnung.bestaetigt").exists()


def test_antrag_hat_hoechstens_eine_buchung(anna, mama, suesses):
    gutschrift(anna, 100)
    a1 = services.antrag_stellen(anna, suesses)
    a2 = services.antrag_stellen(anna, suesses)
    b = services.bestaetigen(a1, von=mama).buchung
    a2.buchung = b
    with pytest.raises(IntegrityError), transaction.atomic():
        a2.save()


# --- Taschengeld-Limit --------------------------------------------------------------------------


def _jetzt(monkeypatch, *args):
    moment = datetime(*args, tzinfo=UTC)
    monkeypatch.setattr("apps.kern.zeit.jetzt", lambda: moment)


def test_limit_zaehlt_offene_antraege(anna, euro):
    gutschrift(anna, 1000)
    for _ in range(10):
        services.antrag_stellen(anna, euro)  # 10 x 1 € = Limit
    with pytest.raises(services.LimitUeberschritten, match="Limit"):
        services.antrag_stellen(anna, euro)
    assert selectors.taschengeld_belegt_cent(anna) == 1000
    assert selectors.taschengeld_frei_cent(anna) == 0


def test_limit_zaehlt_bestaetigte_und_gilt_je_kind(anna, ben, mama, euro):
    gutschrift(anna, 1000)
    gutschrift(ben, 1000)
    for _ in range(10):
        services.bestaetigen(services.antrag_stellen(anna, euro), von=mama)
    with pytest.raises(services.LimitUeberschritten):
        services.antrag_stellen(anna, euro)
    services.antrag_stellen(ben, euro)  # Ben hat sein eigenes Limit


def test_abgelehnt_und_zurueckgezogen_zaehlen_nicht(anna, mama, euro):
    gutschrift(anna, 1000)
    services.ablehnen(services.antrag_stellen(anna, euro), von=mama)
    services.zurueckziehen(services.antrag_stellen(anna, euro), kind=anna)
    assert selectors.taschengeld_belegt_cent(anna) == 0


def test_limit_ueber_die_monatsgrenze(anna, mama, euro, monkeypatch):
    gutschrift(anna, 1000)
    # 30.09. 23:30 Berlin = 21:30 UTC: zehn Euro im September bestätigt
    _jetzt(monkeypatch, 2026, 9, 30, 21, 30)
    for _ in range(10):
        services.bestaetigen(services.antrag_stellen(anna, euro), von=mama)
    _jetzt(monkeypatch, 2026, 9, 30, 21, 45)
    with pytest.raises(services.LimitUeberschritten):
        services.antrag_stellen(anna, euro)
    # 01.10. 00:30 Berlin = 30.09. 22:30 UTC: neuer Monat, Limit wieder frei
    _jetzt(monkeypatch, 2026, 9, 30, 22, 30)
    assert selectors.taschengeld_belegt_cent(anna) == 0
    services.antrag_stellen(anna, euro)
    # Dezember -> Januar rechnet ebenfalls korrekt
    _jetzt(monkeypatch, 2026, 12, 31, 22, 59)
    assert selectors.monat_intervall()[1] == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)


def test_offene_antraege_des_vormonats_zaehlen_weiter(anna, euro, monkeypatch):
    gutschrift(anna, 1000)
    _jetzt(monkeypatch, 2026, 9, 15, 10, 0)
    for _ in range(10):
        services.antrag_stellen(anna, euro)
    _jetzt(monkeypatch, 2026, 10, 2, 10, 0)
    assert selectors.taschengeld_frei_cent(anna) == 0  # noch offen: Entscheidung steht aus


def test_eigenes_limit_ueberschreibt_standard(anna, mama, euro):
    gutschrift(anna, 1000)
    services.limit_setzen(anna, 200, von=mama)
    assert selectors.limit_cent(anna) == 200
    services.antrag_stellen(anna, euro)
    services.antrag_stellen(anna, euro)
    with pytest.raises(services.LimitUeberschritten):
        services.antrag_stellen(anna, euro)
    services.limit_setzen(anna, None, von=mama)
    assert not TaschengeldLimit.objects.filter(kind=anna).exists()
    assert selectors.limit_cent(anna) == 1000
    assert AuditEintrag.objects.filter(aktion="belohnung.limit_gesetzt").count() == 2


def test_standard_limit_aenderbar(anna, mama, euro):
    gutschrift(anna, 1000)
    services.standard_limit_setzen(100, von=mama)
    services.antrag_stellen(anna, euro)
    with pytest.raises(services.LimitUeberschritten):
        services.antrag_stellen(anna, euro)


def test_sonstige_belohnung_ohne_limit(anna, suesses):
    gutschrift(anna, 1000)
    for _ in range(20):
        services.antrag_stellen(anna, suesses)
