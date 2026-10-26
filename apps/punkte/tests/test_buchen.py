"""Buchungs-Service: Wirkung je Art, Idempotenz, Gegenbuchung, Audit, Ereignis, Reservierungen."""

from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.ereignisse.models import Ereignis
from apps.kern import audit, zeit
from apps.kern.models import AuditEintrag
from apps.punkte import registry, selectors, services
from apps.punkte.models import Art, Buchung

from .conftest import TAG, gutschrift

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("art", "guthaben", "xp"),
    [
        (Art.AUFGABE, 20, 20),
        (Art.SERIENBONUS, 20, 20),
        (Art.SONDERPUNKTE, 20, 20),
        (Art.MODUL, 20, 20),
        (Art.EINLOESUNG, -20, 0),
        (Art.MODKAUF, -20, 0),
        (Art.KORREKTUR, 20, 20),
    ],
)
def test_wirkung_je_art(anna, art, guthaben, xp):
    gutschrift(anna, 100)
    b = gutschrift(anna, 20, art=art)
    assert (b.guthaben_delta, b.xp_delta) == (guthaben, xp)
    assert selectors.salden(anna) == selectors.Saldo(100 + guthaben, 100 + xp)


def test_ausgaben_senken_xp_nie(anna):
    gutschrift(anna, 50)
    gutschrift(anna, 30, art=Art.EINLOESUNG)
    gutschrift(anna, 20, art=Art.MODKAUF)
    assert selectors.salden(anna) == selectors.Saldo(guthaben=0, xp=50)


def test_korrektur_senkt_guthaben_und_xp(anna, mama):
    gutschrift(anna, 40)
    k = gutschrift(anna, -15, art=Art.KORREKTUR, begruendung="nicht gründlich", von=mama)
    assert (k.guthaben_delta, k.xp_delta) == (-15, -15)
    assert selectors.salden(anna) == selectors.Saldo(guthaben=25, xp=25)


def test_bezugsdatum_standard_ist_heute(anna):
    b = services.buchen(anna, Art.AUFGABE, 5, schluessel="a:1", quelle_modul="aufgaben")
    assert b.bezugsdatum == zeit.heute()


# --- Idempotenz ------------------------------------------------------------------------------


def test_doppelter_schluessel_erzeugt_keine_zweite_buchung(anna):
    erste = gutschrift(anna, 10, schluessel="aufgabe:1:basis")
    zweite = gutschrift(anna, 10, schluessel="aufgabe:1:basis")
    assert zweite.pk == erste.pk
    assert Buchung.objects.count() == 1
    assert selectors.guthaben(anna) == 10
    assert Ereignis.objects.filter(typ_id="punkte.gebucht").count() == 1
    assert AuditEintrag.objects.filter(aktion="punkte.gebucht").count() == 1


def test_doppelte_ausgabe_mit_gleichem_schluessel_bucht_einmal(anna):
    gutschrift(anna, 30)
    gutschrift(anna, 30, art=Art.EINLOESUNG, schluessel="antrag:7")
    # Guthaben ist jetzt 0; die Wiederholung darf weder buchen noch scheitern
    assert gutschrift(anna, 30, art=Art.EINLOESUNG, schluessel="antrag:7").guthaben_delta == -30
    assert selectors.guthaben(anna) == 0


def test_schluessel_fuer_anderes_kind_ist_konflikt(anna, ben):
    gutschrift(anna, 10, schluessel="aufgabe:1:basis")
    with pytest.raises(services.IdempotenzKonflikt):
        gutschrift(ben, 10, schluessel="aufgabe:1:basis")
    with pytest.raises(services.IdempotenzKonflikt):
        gutschrift(anna, 10, art=Art.SERIENBONUS, schluessel="aufgabe:1:basis")


# --- Gegenbuchung ----------------------------------------------------------------------------


def test_gegenbuchung_einer_aufgabe_senkt_guthaben_und_xp(anna, mama):
    original = gutschrift(anna, 30, referenz_typ="aufgaben.instanz", referenz_id="5")
    gutschrift(anna, 12)
    storno = services.gegenbuchen(original, begruendung="doch nicht erledigt", von=mama)
    assert storno.art == Art.STORNO
    assert storno.storno_von == original
    assert (storno.guthaben_delta, storno.xp_delta) == (-30, -30)
    assert (storno.referenz_typ, storno.referenz_id) == ("aufgaben.instanz", "5")
    assert storno.idempotenz_schluessel == f"storno:{original.pk}"
    assert selectors.salden(anna) == selectors.Saldo(guthaben=12, xp=12)
    assert sum(b.guthaben_delta for b in selectors.buchungen_zu("aufgaben.instanz", 5)) == 0


def test_gegenbuchung_einer_einloesung_erstattet_nur_guthaben(anna, mama):
    gutschrift(anna, 50)
    einloesung = gutschrift(anna, 20, art=Art.EINLOESUNG)
    services.gegenbuchen(einloesung.pk, von=mama)
    assert selectors.salden(anna) == selectors.Saldo(guthaben=50, xp=50)


def test_gegenbuchung_nur_einmal(anna, mama):
    original = gutschrift(anna, 30)
    erste = services.gegenbuchen(original, von=mama)
    zweite = services.gegenbuchen(original, von=mama, schluessel="anderer")
    assert erste.pk == zweite.pk
    assert selectors.guthaben(anna) == 0


def test_storno_eines_stornos_verboten(anna, mama):
    storno = services.gegenbuchen(gutschrift(anna, 30), von=mama)
    with pytest.raises(services.UngueltigeBuchung):
        services.gegenbuchen(storno, von=mama)


def test_storno_darf_guthaben_unter_null_bringen(anna, mama):
    """Vertrauens-Aufgabe, Punkte schon ausgegeben: Korrektur bleibt möglich (kein Ausgabe)."""
    original = gutschrift(anna, 30)
    gutschrift(anna, 30, art=Art.EINLOESUNG)
    services.gegenbuchen(original, von=mama)
    assert selectors.salden(anna) == selectors.Saldo(guthaben=-30, xp=0)
    with pytest.raises(services.GuthabenUnzureichend):
        gutschrift(anna, 1, art=Art.MODKAUF)


# --- Ausgaben, Reservierungen ----------------------------------------------------------------


def test_ausgabe_ueber_guthaben_wird_abgelehnt(anna):
    gutschrift(anna, 10)
    with pytest.raises(services.GuthabenUnzureichend):
        gutschrift(anna, 11, art=Art.EINLOESUNG)
    assert gutschrift(anna, 10, art=Art.EINLOESUNG).guthaben_delta == -10
    assert selectors.guthaben(anna) == 0


def test_reservierungen_mindern_verfuegbares_guthaben(anna):
    gutschrift(anna, 100)
    with registry.isoliert():
        registry.reservierung_registrieren("test.antraege", lambda kind: 70, modul="test")
        assert selectors.reserviert(anna) == 70
        assert selectors.verfuegbar(anna) == 30
        # Mod-Kauf prüft standardmäßig gegen das verfügbare Guthaben
        with pytest.raises(services.GuthabenUnzureichend):
            gutschrift(anna, 40, art=Art.MODKAUF)
        # Einlösung (Antrag ist selbst reserviert) prüft standardmäßig gegen das Guthaben
        gutschrift(anna, 70, art=Art.EINLOESUNG)
        with pytest.raises(services.GuthabenUnzureichend):
            gutschrift(anna, 1, art=Art.EINLOESUNG, verfuegbar_pruefen=True)
    assert selectors.reserviert(anna) == 0


def test_fehlerhafter_reservierungs_provider(anna):
    with registry.isoliert():
        registry.reservierung_registrieren("test.kaputt", lambda kind: -1, modul="test")
        with pytest.raises(ValueError, match="test.kaputt"):
            selectors.verfuegbar(anna)


# --- Prüfungen -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("art", "punkte", "extra"),
    [
        (Art.AUFGABE, 0, {}),
        (Art.AUFGABE, -5, {}),
        (Art.AUFGABE, 2.5, {}),
        (Art.AUFGABE, True, {}),
        (Art.KORREKTUR, 0, {}),
        (Art.SONDERPUNKTE, 5, {"begruendung": "  "}),
        (Art.STORNO, 5, {}),
        ("unbekannt", 5, {}),
        (Art.AUFGABE, 5, {"schluessel": ""}),
        (Art.AUFGABE, 5, {"schluessel": "x" * 121}),
        (Art.AUFGABE, 5, {"quelle_modul": ""}),
        (Art.AUFGABE, 5, {"verfuegbar_pruefen": True}),
    ],
)
def test_ungueltige_eingaben(anna, art, punkte, extra):
    with pytest.raises(services.UngueltigeBuchung):
        gutschrift(anna, punkte, art=art, **extra)
    assert not Buchung.objects.exists()


def test_nur_kinder_haben_ein_konto(mama):
    with pytest.raises(services.UngueltigeBuchung):
        gutschrift(mama, 5)


@pytest.mark.parametrize("art", [Art.SONDERPUNKTE, Art.KORREKTUR])
def test_kind_darf_keine_eltern_buchungen_ausloesen(anna, art):
    with pytest.raises(PermissionDenied):
        gutschrift(anna, 5, art=art, von=anna)
    original = gutschrift(anna, 5, von=anna)  # Vertrauen: Kind löst Aufgaben-Buchung aus
    with pytest.raises(PermissionDenied):
        services.gegenbuchen(original, von=anna)


def test_referenz_als_modell(anna, mama):
    b = gutschrift(anna, 5, referenz=mama)
    assert (b.referenz_typ, b.referenz_id) == ("konten.benutzer", str(mama.pk))


# --- Audit und Ereignis ----------------------------------------------------------------------


def test_audit_mit_aktuellem_elternteil(anna, mama):
    with audit.kontext(lambda: (mama, None)):
        b = gutschrift(anna, 8, art=Art.SONDERPUNKTE, begruendung="sehr gründlich")
    assert b.erstellt_von == mama
    eintrag = AuditEintrag.objects.get(aktion="punkte.gebucht")
    assert (eintrag.akteur, eintrag.kind, eintrag.rolle) == (mama, anna, "eltern")
    assert (eintrag.objekt_typ, eintrag.objekt_id) == ("punkte.buchung", str(b.pk))
    assert eintrag.details["begruendung"] == "sehr gründlich"
    assert eintrag.details["xp_delta"] == 8


def test_ohne_anfrage_bucht_das_system(anna):
    b = gutschrift(anna, 8)
    assert b.erstellt_von is None
    assert AuditEintrag.objects.get(aktion="punkte.gebucht").rolle == "system"


def test_akteur_ohne_modell_wird_nicht_gespeichert(anna):
    """z. B. Test-Doubles: Audit nimmt den Namen, ``erstellt_von`` bleibt leer."""
    papa = SimpleNamespace(anzeigename="Papa", rolle="eltern")
    b = gutschrift(anna, 8, art=Art.SONDERPUNKTE, von=papa)
    assert b.erstellt_von is None
    assert AuditEintrag.objects.get(aktion="punkte.gebucht").akteur_name == "Papa"


def test_ereignis_punkte_gebucht(anna, mama):
    b = gutschrift(anna, 8)
    storno = services.gegenbuchen(b, von=mama)
    ereignisse = list(Ereignis.objects.filter(typ_id="punkte.gebucht").order_by("id"))
    assert [e.daten["buchung"] for e in ereignisse] == [b.pk, storno.pk]
    assert ereignisse[0].daten == {
        "buchung": b.pk,
        "kind": str(anna.pk),
        "art": "aufgabe",
        "guthaben_delta": 8,
        "xp_delta": 8,
        "bezugsdatum": TAG.isoformat(),
        "quelle_modul": "aufgaben",
        "storno_von": None,
    }
    assert ereignisse[1].daten["storno_von"] == b.pk
    assert [e.kind_id for e in ereignisse] == [anna.pk, anna.pk]
    assert AuditEintrag.objects.filter(aktion="punkte.storniert").count() == 1


def test_rollback_erzeugt_weder_buchung_noch_ereignis_noch_audit(anna):
    with pytest.raises(RuntimeError), transaction.atomic():
        gutschrift(anna, 10)
        raise RuntimeError
    assert not Buchung.objects.exists()
    assert not Ereignis.objects.filter(typ_id="punkte.gebucht").exists()
    assert not AuditEintrag.objects.filter(aktion="punkte.gebucht").exists()
    assert selectors.guthaben(anna) == 0
