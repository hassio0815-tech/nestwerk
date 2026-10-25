"""Geräte-Cookie, Kiosk-Leerlauf (passive Endpunkte verlängern nicht), persönliche Geräte."""

import pytest
from django.urls import reverse

from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.konten import services
from apps.konten.geraet import COOKIE_NAME
from apps.konten.models import Geraet

from .conftest import PASSWORT, client_fuer, eltern_anmelden, kind_anmelden

pytestmark = pytest.mark.django_db

AKTIV = "/test/aktiv/"
POLLING = "/test/polling/"


@pytest.fixture(autouse=True)
def test_urls(settings):
    settings.ROOT_URLCONF = "apps.konten.tests.urls_test"


def angemeldet_bei(client):
    return "_auth_user_id" in client.session


def test_kind_auf_dem_tablet_wird_nach_leerlauf_abgemeldet(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    assert c.session["nestwerk_kiosk"] is True
    uhr.weiter(seconds=299)
    assert c.get(AKTIV).status_code == 200
    uhr.weiter(seconds=301)
    antwort = c.get(AKTIV)
    assert antwort.status_code == 302 and antwort.url == reverse("konten:start")
    assert not angemeldet_bei(c)
    assert AuditEintrag.objects.filter(aktion="konten.sitzung_abgelaufen", akteur=anna).exists()


def test_aktive_anfragen_halten_die_sitzung_offen(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    for _ in range(5):
        uhr.weiter(seconds=200)
        assert c.get(AKTIV).status_code == 200
    assert angemeldet_bei(c)


def test_polling_verlaengert_die_sitzung_nicht(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    for _ in range(2):  # 100 s und 200 s nach dem Login: Polling wird bedient
        uhr.weiter(seconds=100)
        assert c.get(POLLING).status_code == 200
    # Das Polling hat nichts verlängert: 301 s nach der letzten aktiven Anfrage ist Schluss
    uhr.weiter(seconds=101)
    assert c.get(AKTIV).status_code == 302
    assert not angemeldet_bei(c)


def test_aktive_anfrage_zwischen_pollings_verlaengert(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    uhr.weiter(seconds=200)
    assert c.get(POLLING).status_code == 200
    assert c.get(AKTIV).status_code == 200  # aktiv: Uhr startet neu
    uhr.weiter(seconds=200)
    assert c.get(POLLING).status_code == 200
    assert angemeldet_bei(c)


def test_polling_nach_ablauf_meldet_ab_und_antwortet_nicht_mit_daten(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    uhr.weiter(seconds=301)
    antwort = c.get(POLLING)
    assert antwort.status_code == 302 and b"poll" not in antwort.content
    assert not angemeldet_bei(c)


def test_htmx_polling_nach_ablauf_bekommt_401_mit_redirect(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    uhr.weiter(seconds=301)
    antwort = c.get(POLLING, headers={"HX-Request": "true"})
    assert antwort.status_code == 401 and antwort["HX-Redirect"] == reverse("konten:start")


def test_aktiver_herzschlag_des_browsers_zaehlt_als_aktivitaet(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    uhr.weiter(seconds=250)
    assert c.post(reverse("konten:aktiv")).status_code == 204
    uhr.weiter(seconds=250)
    assert c.get(AKTIV).status_code == 200


def test_eltern_auf_dem_tablet_haben_denselben_leerlauf(mama, tablet, uhr):
    c = client_fuer(tablet)
    eltern_anmelden(c, mama, vertraut=True)
    assert c.session["nestwerk_kiosk"] is True
    assert c.session.get_expiry_age() <= 12 * 3600  # "vertraut" gilt auf dem Kiosk nicht
    uhr.weiter(seconds=301)
    assert c.get(AKTIV).status_code == 302
    assert not angemeldet_bei(c)


def test_leerlauf_ist_eine_einstellung(anna, tablet, uhr):
    einstellungen.setzen("konten.kiosk_leerlauf_sekunden", 60, akteur=None)
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    uhr.weiter(seconds=61)
    assert c.get(AKTIV).status_code == 302


def test_persoenliches_geraet_bleibt_angemeldet(anna, iphone, uhr):
    c = client_fuer(iphone)
    kind_anmelden(c, anna)
    uhr.weiter(days=30)
    assert c.get(AKTIV).status_code == 200
    assert angemeldet_bei(c)


def test_unbekanntes_geraet_ohne_cookie_ist_nicht_kiosk(anna, uhr, client):
    kind_anmelden(client, anna)
    uhr.weiter(hours=3)
    assert client.get(AKTIV).status_code == 200


def test_kiosk_sitzung_bleibt_auch_ohne_cookie_kiosk(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    del c.cookies[COOKIE_NAME]
    uhr.weiter(seconds=301)
    assert c.get(AKTIV).status_code == 302


def test_gefaelschtes_geraete_cookie_wird_ignoriert(anna, tablet, uhr, client):
    client.cookies[COOKIE_NAME] = str(tablet.pk)  # unsigniert
    kind_anmelden(client, anna)
    assert client.session["nestwerk_kiosk"] is False
    client.cookies[COOKIE_NAME] = "irgendwas:1abc:xyz"
    assert client.get(AKTIV).status_code == 200


def test_widerrufenes_geraet_gilt_als_unbekannt(anna, tablet, mama, uhr):
    services.geraet_widerrufen(tablet, von=mama)
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    assert c.session["nestwerk_kiosk"] is False


def test_geraet_registrieren_setzt_signiertes_httponly_cookie(mama, client):
    eltern_anmelden(client, mama)
    antwort = client.post(reverse("konten:geraete"), {"bezeichnung": "Flur-Tablet", "typ": "kiosk"})
    assert antwort.status_code == 302
    geraet = Geraet.objects.get()
    assert (geraet.typ, geraet.registriert_von) == ("kiosk", mama)
    cookie = antwort.cookies[COOKIE_NAME]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert str(geraet.pk) not in cookie.value.split(":")[1:]  # signiert, Wert:Zeit:Signatur
    assert cookie.value.startswith(str(geraet.pk) + ":")
    assert AuditEintrag.objects.filter(
        aktion="konten.geraet_registriert", akteur=mama, objekt_id=str(geraet.pk)
    ).exists()


def test_registriertes_geraet_wird_erkannt_und_audit_nennt_es(anna, tablet):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    eintrag = AuditEintrag.objects.get(aktion="konten.angemeldet")
    assert eintrag.geraet == tablet and eintrag.akteur == anna


def test_geraet_widerrufen_per_post(mama, tablet, client):
    eltern_anmelden(client, mama)
    antwort = client.post(reverse("konten:geraet_widerrufen", args=[tablet.pk]))
    assert antwort.status_code == 302
    tablet.refresh_from_db()
    assert tablet.aktiv is False


def test_ungueltiger_geraetetyp_wird_abgelehnt(mama):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.geraet_registrieren("X", "fernseher", registriert_von=mama)


def test_passwort_nie_im_klartext_auf_dem_tablet_bekannt(mama, tablet):
    assert PASSWORT not in tablet.bezeichnung


# --- Review AP19 ------------------------------------------------------------------------------


def test_widerruf_des_geraets_beendet_dessen_sitzung(anna, tablet, uhr):
    """Regression B-06: Widerruf wirkt sofort auf Sitzungen, die auf dem Gerät begannen
    (vorher blieb nur das Kiosk-Flag in der Sitzung stehen)."""
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    assert c.session["nestwerk_geraet_id"] == str(tablet.pk)
    services.geraet_widerrufen(tablet, von=None)
    antwort = c.get(AKTIV)
    assert antwort.status_code == 302 and antwort.url == reverse("konten:start")
    assert not angemeldet_bei(c)
    eintrag = AuditEintrag.objects.filter(aktion="konten.sitzung_abgelaufen", akteur=anna).get()
    assert eintrag.details == {"grund": "geraet_widerrufen"}


def test_sitzung_ohne_registriertes_geraet_bleibt_vom_widerruf_unberuehrt(anna, tablet):
    c = client_fuer()
    kind_anmelden(c, anna)
    assert c.session["nestwerk_geraet_id"] is None
    services.geraet_widerrufen(tablet, von=None)
    assert c.get(AKTIV).status_code == 200


def test_neu_registrieren_auf_registriertem_geraet_beendet_die_sitzung_nicht(mama, iphone):
    c = client_fuer(iphone)
    eltern_anmelden(c, mama)
    assert c.session["nestwerk_geraet_id"] == str(iphone.pk)
    antwort = c.post(reverse("konten:geraete"), {"bezeichnung": "Flur", "typ": "kiosk"})
    assert antwort.status_code == 302
    neu = Geraet.objects.get(bezeichnung="Flur")
    assert c.session["nestwerk_geraet_id"] == str(neu.pk)
    assert c.get(AKTIV).status_code == 200
