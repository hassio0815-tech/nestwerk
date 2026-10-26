"""Seiten: Liste mit Zähler (auch unterdrückte), Polling-Teile, Präferenzen, Pop-ups."""

from datetime import date, time

import pytest
from django.urls import reverse

from apps.benachrichtigung import router, selectors, services
from apps.benachrichtigung.models import Benachrichtigung, Praeferenz, Ruhezeit
from apps.konten.tests.conftest import angemeldet
from apps.konten.zugriff import ist_passiv

from .conftest import PIN, TYP_INFO, TYP_KIND, TYP_LISTE, veroeffentlichen

pytestmark = pytest.mark.django_db


@pytest.fixture
def eltern_client(client, mama):
    angemeldet(client, mama)
    return client


def test_liste_zeigt_ungelesen_zaehler_und_unterdrueckte(katalog, mama, uhr, eltern_client):
    uhr.lokal(date(2026, 10, 23), 23)
    services.ruhezeit_setzen(mama, von=time(21), bis=time(7))
    services.praeferenz_setzen(mama, TYP_INFO, "email", False)
    e = veroeffentlichen(TYP_INFO)
    router.router(e)
    seite = eltern_client.get(reverse("benachrichtigung:liste")).content.decode()
    assert "1 ungelesen" in seite
    assert "Aufgabe gewählt" in seite
    assert "Push: stumm (Ruhezeit)" in seite
    assert "E-Mail: abgeschaltet" in seite
    assert selectors.ungelesen(mama) == 1


def test_gelesen_markieren_senkt_zaehler(katalog, mama, eltern_client):
    router.router(veroeffentlichen(TYP_INFO))
    router.router(veroeffentlichen(TYP_INFO))
    b = Benachrichtigung.objects.filter(empfaenger=mama).first()
    antwort = eltern_client.post(reverse("benachrichtigung:gelesen", args=[b.pk]))
    assert antwort.status_code == 200 and "1 ungelesen" in antwort.content.decode()
    antwort = eltern_client.post(reverse("benachrichtigung:alle_gelesen"))
    assert "Alles gelesen" in antwort.content.decode()
    assert selectors.ungelesen(mama) == 0


def test_fremde_benachrichtigung_laesst_sich_nicht_markieren(katalog, mama, papa, eltern_client):
    router.router(veroeffentlichen(TYP_INFO))
    papas = Benachrichtigung.objects.get(empfaenger=papa)
    eltern_client.post(reverse("benachrichtigung:gelesen", args=[papas.pk]))
    papas.refresh_from_db()
    assert papas.gelesen_am is None
    assert (
        eltern_client.get(reverse("benachrichtigung:oeffnen", args=[papas.pk])).status_code == 404
    )


def test_oeffnen_markiert_und_leitet_zum_deep_link(katalog, mama, eltern_client):
    from .conftest import TYP_ENTSCHEIDUNG

    router.router(veroeffentlichen(TYP_ENTSCHEIDUNG, daten={"instanz": 9}))
    b = Benachrichtigung.objects.get(empfaenger=mama)
    antwort = eltern_client.get(reverse("benachrichtigung:oeffnen", args=[b.pk]))
    assert antwort.status_code == 302 and antwort["Location"] == "/eltern/meldung/9/"
    b.refresh_from_db()
    assert b.gelesen_am is not None


def test_polling_teile_sind_passiv():
    from apps.benachrichtigung import views

    assert ist_passiv(views.liste_teil) and ist_passiv(views.zaehler) and ist_passiv(views.popups)
    assert not ist_passiv(views.liste) and not ist_passiv(views.gelesen)


def test_polling_teil_und_zaehler(katalog, mama, eltern_client):
    router.router(veroeffentlichen(TYP_INFO))
    teil = eltern_client.get(reverse("benachrichtigung:liste_teil")).content.decode()
    assert 'hx-trigger="every 30s' in teil and "1 ungelesen" in teil
    assert "<html" not in teil  # nur das Partial
    assert "1 neu" in eltern_client.get(reverse("benachrichtigung:zaehler")).content.decode()


def test_rollenschutz(katalog, anna, client):
    angemeldet(client, anna)
    for name in ("liste", "liste_teil", "zaehler", "einstellungen"):
        assert client.get(reverse(f"benachrichtigung:{name}")).status_code == 403
    assert client.post(reverse("benachrichtigung:alle_gelesen")).status_code == 403
    assert client.post(reverse("benachrichtigung:praeferenz")).status_code == 403


def test_nicht_angemeldet_wird_umgeleitet(client):
    assert client.get(reverse("benachrichtigung:liste")).status_code == 302
    antwort = client.get(reverse("benachrichtigung:liste_teil"), HTTP_HX_REQUEST="true")
    assert antwort.status_code == 401 and "HX-Redirect" in antwort


def test_einstellungen_zeigt_matrix(katalog, mama, eltern_client):
    seite = eltern_client.get(reverse("benachrichtigung:einstellungen")).content.decode()
    assert "Aufgabe gewählt" in seite and "Aufgabe gemeldet" in seite
    assert "Pop-up" not in seite.split("<tbody>")[0]  # Pop-up ist kein Eltern-Kanal
    assert "Aufgabe bestätigt" not in seite  # Kind-Typ nicht in der Eltern-Matrix


def test_praeferenz_per_htmx_setzen(katalog, mama, eltern_client):
    antwort = eltern_client.post(
        reverse("benachrichtigung:praeferenz"),
        {"typ": TYP_INFO, "kanal": "email", "aktiv": "0"},
        HTTP_HX_REQUEST="true",
    )
    assert antwort.status_code == 200
    assert Praeferenz.objects.get(benutzer=mama, ereignistyp=TYP_INFO, kanal="email").aktiv is False
    assert 'aria-checked="false"' in antwort.content.decode()


def test_praeferenz_unbekannter_kanal_oder_typ(katalog, mama, eltern_client):
    url = reverse("benachrichtigung:praeferenz")
    assert eltern_client.post(url, {"typ": TYP_INFO, "kanal": "gibtsnicht"}).status_code == 400
    assert eltern_client.post(url, {"typ": "gibt.es_nicht", "kanal": "push"}).status_code == 400
    assert not Praeferenz.objects.exists()


def test_eltern_stellen_kinder_ein_aber_nicht_fremde(katalog, mama, papa, anna, eltern_client):
    url = reverse("benachrichtigung:praeferenz")
    eltern_client.post(url, {"typ": TYP_KIND, "kanal": "popup", "aktiv": "0", "fuer": str(anna.pk)})
    assert Praeferenz.objects.get(benutzer=anna).aktiv is False
    # Einstellungen eines anderen Elternteils sind tabu
    assert (
        eltern_client.post(
            url, {"typ": TYP_INFO, "kanal": "push", "fuer": str(papa.pk)}
        ).status_code
        == 403
    )
    seite = eltern_client.get(reverse("benachrichtigung:einstellungen"), {"fuer": str(anna.pk)})
    assert "Aufgabe bestätigt" in seite.content.decode()


def test_ruhezeit_speichern_und_entfernen(katalog, mama, eltern_client):
    url = reverse("benachrichtigung:ruhezeit")
    antwort = eltern_client.post(
        url, {"von": "21:30", "bis": "06:45", "tage": ["0", "1", "2"], "email": "1"}
    )
    assert antwort.status_code == 200
    r = Ruhezeit.objects.get(benutzer=mama)
    assert (r.von, r.bis, r.wochentage, r.gilt_fuer_email) == (time(21, 30), time(6, 45), 7, True)
    fehler = eltern_client.post(url, {"von": "x", "bis": "06:45", "tage": ["0"]})
    assert "Uhrzeiten" in fehler.content.decode()
    fehler = eltern_client.post(url, {"von": "21:00", "bis": "06:45"})
    assert "Wochentag" in fehler.content.decode()
    eltern_client.post(url, {"aktion": "entfernen"})
    assert not Ruhezeit.objects.exists()


def test_profil_umschalten(katalog, mama, eltern_client):
    url = reverse("benachrichtigung:profil")
    antwort = eltern_client.post(url, {"nur_entscheidungen": "1"})
    assert selectors.mail_nur_entscheidungen(mama)
    assert "nur Entscheidungen" in antwort.content.decode()
    eltern_client.post(url, {"nur_entscheidungen": "0"})
    assert not selectors.mail_nur_entscheidungen(mama)


def test_popups_fuer_kinder_werden_einmal_ausgeliefert(katalog, mama, anna, client):
    from apps.benachrichtigung import versand

    router.router(veroeffentlichen(TYP_KIND, kind=anna))
    versand.zustellungen_senden()
    angemeldet(client, anna)
    antwort = client.get(reverse("benachrichtigung:popups"))
    assert antwort.status_code == 200 and "Aufgabe bestätigt" in antwort.content.decode()
    assert client.get(reverse("benachrichtigung:popups")).status_code == 204


def test_popups_nur_fuer_kinder(katalog, mama, eltern_client):
    assert eltern_client.get(reverse("benachrichtigung:popups")).status_code == 403


def test_kachel_ist_registriert(katalog, mama, rf):
    from apps.kern import registry as kern_registry

    kacheln = [k.schluessel for k in kern_registry.kacheln("eltern")]
    assert "benachrichtigung.liste" in kacheln
    router.router(veroeffentlichen(TYP_LISTE))
    anfrage = rf.get("/")
    anfrage.user = mama
    kachel = next(
        k for k in kern_registry.kacheln("eltern") if k.schluessel == "benachrichtigung.liste"
    )
    assert kachel.kontext(anfrage)["ungelesen"] == 1


def test_pin_konstante_wird_genutzt():
    assert PIN


def test_kinderseite_bindet_popup_abruf_ein(katalog, anna, client):
    angemeldet(client, anna)
    seite = client.get(reverse("konten:kind_heim")).content.decode()
    assert reverse("benachrichtigung:popups") in seite
