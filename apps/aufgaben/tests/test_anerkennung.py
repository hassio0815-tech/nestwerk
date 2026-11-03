"""Anerkennung: Punkte ohne Aufgabe (Eltern), Grenzen, Wochenlimit, Rechte, Storno, Ereignis."""

from datetime import UTC, datetime

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.aufgaben import anerkennung, events
from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, zeit
from apps.kern.models import AuditEintrag
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte
from apps.punkte.models import Art

FREITAG = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
SONNTAG = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
MONTAG = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def jetzt(monkeypatch):
    """Steuerbare Uhr: ``jetzt.setzen(datetime)``."""

    class Uhr:
        wert = FREITAG

        def setzen(self, wert):
            self.wert = wert

    uhr = Uhr()
    monkeypatch.setattr(zeit, "jetzt", lambda: uhr.wert)
    return uhr


def test_anerkennung_bucht_punkte_und_xp(db, anna, mama):
    buchung = anerkennung.vergeben(anna, 10, "Hat der Oma geholfen", von=mama)
    assert buchung.art == Art.ANERKENNUNG
    assert (buchung.guthaben_delta, buchung.xp_delta) == (10, 10)
    assert buchung.begruendung == "Hat der Oma geholfen"
    assert buchung.erstellt_von == mama
    saldo = punkte_selectors.salden(anna)
    assert (saldo.guthaben, saldo.xp) == (10, 10)
    assert not buchung.referenz_typ  # kein Aufgabenbezug


def test_anerkennung_zaehlt_fuer_familienziel_xp(db, anna, mama, jetzt):
    anerkennung.vergeben(anna, 7, "Super", von=mama)
    tag = zeit.heute()
    assert punkte_selectors.xp_zeitraum(tag, tag, kind=anna) == 7


def test_anerkennung_ereignis_und_audit(db, anna, mama):
    buchung = anerkennung.vergeben(anna, 5, "Danke fürs Helfen", von=mama)
    ereignis = Ereignis.objects.get(typ_id=events.ANERKENNUNG)
    assert ereignis.kind == anna
    assert ereignis.daten["punkte"] == 5 and ereignis.daten["begruendung"] == "Danke fürs Helfen"
    assert AuditEintrag.objects.filter(aktion="aufgabe.anerkennung", kind=anna).exists()
    assert AuditEintrag.objects.filter(aktion="punkte.gebucht", kind=anna).exists()
    assert buchung.pk == ereignis.daten["buchung"]


def test_nur_eltern_duerfen_vergeben(db, anna, ben, mama):
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 5, "Ich selbst", von=anna)
    # auch direkt im Ledger: Kinder dürfen die Art nicht buchen
    with pytest.raises(PermissionDenied):
        punkte.buchen(
            ben,
            Art.ANERKENNUNG,
            5,
            schluessel="t:1",
            quelle_modul="anerkennung",
            begruendung="x",
            von=anna,
        )
    assert punkte_selectors.guthaben(anna) == 0


def test_bemerkung_ist_pflicht(db, anna, mama):
    for leer in ("", "   ", None):
        with pytest.raises(anerkennung.AnerkennungFehler):
            anerkennung.vergeben(anna, 5, leer, von=mama)
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 5, "x" * 201, von=mama)
    assert punkte_selectors.guthaben(anna) == 0


@pytest.mark.parametrize("punkte_wert", [0, -3, 26, "5", 2.5, True])
def test_einzelgrenze(db, anna, mama, punkte_wert):
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, punkte_wert, "Grund", von=mama)
    assert punkte_selectors.guthaben(anna) == 0


def test_grenzen_sind_einstellungen(db, anna, mama):
    assert anerkennung.grenzen() == (25, 50)
    einstellungen.setzen("aufgaben.anerkennung_max_punkte", 5, akteur=None)
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 6, "Grund", von=mama)
    anerkennung.vergeben(anna, 5, "Grund", von=mama)


def test_wochenlimit_pro_kind(db, anna, ben, mama, jetzt):
    anerkennung.vergeben(anna, 25, "Eins", von=mama)
    anerkennung.vergeben(anna, 25, "Zwei", von=mama)
    with pytest.raises(anerkennung.AnerkennungFehler) as fehler:
        anerkennung.vergeben(anna, 1, "Drei", von=mama)
    assert "0" in str(fehler.value)
    assert anerkennung.woche_bisher(anna) == 50
    assert anerkennung.woche_rest(anna) == 0
    # ein anderes Kind hat sein eigenes Limit
    anerkennung.vergeben(ben, 25, "Eins", von=mama)
    assert anerkennung.woche_rest(ben) == 25


def test_wochenlimit_teilweise_ausgeschoepft(db, anna, mama, jetzt):
    anerkennung.vergeben(anna, 25, "Eins", von=mama)
    anerkennung.vergeben(anna, 20, "Zwei", von=mama)
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 6, "Drei", von=mama)
    anerkennung.vergeben(anna, 5, "Drei", von=mama)
    assert anerkennung.woche_bisher(anna) == 50


def test_wochengrenze_sonntag_montag(db, anna, mama, jetzt):
    jetzt.setzen(SONNTAG)
    anerkennung.vergeben(anna, 25, "Sonntag eins", von=mama)
    anerkennung.vergeben(anna, 25, "Sonntag zwei", von=mama)
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 1, "Noch einer", von=mama)
    jetzt.setzen(MONTAG)  # neue Woche, Zähler beginnt bei 0
    assert anerkennung.woche_bisher(anna) == 0
    anerkennung.vergeben(anna, 25, "Montag", von=mama)
    assert anerkennung.woche_bisher(anna) == 25


def test_storno_gibt_wochenplatz_frei(db, anna, mama, jetzt):
    erste = anerkennung.vergeben(anna, 25, "Eins", von=mama)
    anerkennung.vergeben(anna, 25, "Zwei", von=mama)
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 10, "Drei", von=mama)
    storno = punkte.gegenbuchen(erste, begruendung="Irrtum", von=mama)
    assert (storno.guthaben_delta, storno.xp_delta) == (-25, -25)
    assert anerkennung.woche_bisher(anna) == 25
    anerkennung.vergeben(anna, 25, "Drei", von=mama)
    assert punkte_selectors.guthaben(anna) == 50


def test_doppelter_absendeklick_bucht_einmal(db, anna, mama):
    vorgang = anerkennung.neuer_vorgang()
    a = anerkennung.vergeben(anna, 10, "Grund", von=mama, vorgang=vorgang)
    b = anerkennung.vergeben(anna, 10, "Grund", von=mama, vorgang=vorgang)
    assert a.pk == b.pk
    assert punkte_selectors.guthaben(anna) == 10
    assert Ereignis.objects.filter(typ_id=events.ANERKENNUNG).count() == 1


def test_inaktives_kind_oder_eltern_als_ziel(db, anna, mama, papa):
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(papa, 5, "Grund", von=mama)
    anna.aktiv = False
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 5, "Grund", von=mama)


def test_fehlgeschlagene_vergabe_hinterlaesst_nichts(db, anna, mama):
    with pytest.raises(anerkennung.AnerkennungFehler):
        anerkennung.vergeben(anna, 5, "", von=mama)
    assert Ereignis.objects.filter(typ_id=events.ANERKENNUNG).count() == 0
    assert not AuditEintrag.objects.filter(aktion="aufgabe.anerkennung").exists()


# --- Oberfläche ---------------------------------------------------------------------------------


def test_maske_nur_fuer_eltern(client, kind_client):
    assert kind_client.get(reverse("aufgaben:anerkennung")).status_code in (302, 403)
    antwort = kind_client.post(reverse("aufgaben:anerkennung"), {"punkte": "5"})
    assert antwort.status_code in (302, 403)


def test_maske_anonym_gesperrt(client):
    assert client.get(reverse("aufgaben:anerkennung")).status_code in (302, 403)


def test_maske_zeigt_kinder_und_limit(eltern_client, anna, ben):
    html = eltern_client.get(reverse("aufgaben:anerkennung")).content.decode()
    assert "Anna" in html and "Ben" in html
    assert 'name="punkte"' in html and 'name="bemerkung"' in html
    assert html.index('name="punkte"') < html.index('name="bemerkung"')
    assert 'max="25"' in html


def test_maske_vergibt(eltern_client, anna):
    antwort = eltern_client.post(
        reverse("aufgaben:anerkennung"),
        {
            "kind_id": str(anna.pk),
            "punkte": "12",
            "bemerkung": "Prima Einsatz",
            "vorgang": "ab12cd34",
        },
    )
    assert antwort.status_code == 200
    assert "12 Punkte Anerkennung für Anna" in antwort.content.decode()
    assert punkte_selectors.guthaben(anna) == 12


def test_maske_fehler_als_hinweis(eltern_client, anna):
    url = reverse("aufgaben:anerkennung")
    antwort = eltern_client.post(
        url, {"kind_id": str(anna.pk), "punkte": "99", "bemerkung": "Zu viel"}
    )
    assert antwort.status_code == 422 and "1 bis 25" in antwort.content.decode()
    assert "Zu viel" in antwort.content.decode()  # Eingabe bleibt stehen
    assert eltern_client.post(url, {"punkte": "5", "bemerkung": "x"}).status_code == 422
    assert (
        eltern_client.post(
            url, {"kind_id": "kein-uuid", "punkte": "5", "bemerkung": "x"}
        ).status_code
        == 422
    )
    assert (
        eltern_client.post(
            url, {"kind_id": str(anna.pk), "punkte": "abc", "bemerkung": "x"}
        ).status_code
        == 422
    )
    assert punkte_selectors.guthaben(anna) == 0


def test_bemerkung_wird_maskiert(eltern_client, anna):
    eltern_client.post(
        reverse("aufgaben:anerkennung"),
        {"kind_id": str(anna.pk), "punkte": "99", "bemerkung": "<script>alert(1)</script>"},
    )
    antwort = eltern_client.post(
        reverse("aufgaben:anerkennung"),
        {"kind_id": str(anna.pk), "punkte": "99", "bemerkung": "<script>alert(1)</script>"},
    )
    assert "<script>alert(1)</script>" not in antwort.content.decode()
