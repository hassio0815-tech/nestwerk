"""Meine Einstellungen (Kind), Mood-Anzeige, Mood-Vorschläge und Mood-Verwaltung (Eltern)."""

import pytest
from django.contrib.auth import authenticate
from django.test import Client
from django.urls import reverse

from apps.ereignisse.models import Ereignis
from apps.kern.models import AuditEintrag
from apps.konten import selectors, services
from apps.konten.models import MoodEigen, VorschlagStatus
from apps.konten.tests.conftest import FALSCHE_PIN, PASSWORT, PIN, eltern_anmelden, kind_anmelden
from apps.oberflaeche import events

NEUE_PIN = "2580"


def u(name, *args):
    return reverse(f"oberflaeche:{name}", args=args)


@pytest.fixture
def eltern(db, mama):
    c = Client()
    eltern_anmelden(c, mama, PASSWORT)
    return c


@pytest.fixture
def kind(db, anna):
    c = Client()
    kind_anmelden(c, anna)
    return c


# --- Zugriff und Zahnrad ------------------------------------------------------------------------


def test_zahnrad_im_kopf_der_kinderseiten(kind):
    html = kind.get(u("kind_heim")).content.decode()
    assert u("kind_einstellungen") in html and 'aria-label="Meine Einstellungen"' in html


def test_nur_das_angemeldete_kind(client, eltern, anna):
    ziele = ["kind_einstellungen", "kind_profil", "kind_code", "kind_mood", "kind_mood_vorschlag"]
    for name in ziele:  # anonym
        assert client.get(u(name)).status_code in (302, 403)
        assert client.post(u(name), {}).status_code in (302, 403)
    for name in ziele:  # Eltern haben diese Seiten nicht
        assert eltern.get(u(name)).status_code in (302, 403)
        assert eltern.post(u(name), {"anzeigename": "X"}).status_code in (302, 403)


def test_kind_aendert_nur_sich_selbst(kind, anna, ben):
    kind.post(
        u("kind_profil"), {"anzeigename": "Annabelle", "spitzname": "Anni", "id": str(ben.pk)}
    )
    ben.refresh_from_db()
    anna.refresh_from_db()
    assert anna.anzeigename == "Annabelle" and ben.anzeigename == "Ben" and ben.spitzname == ""


# --- Name, Spitzname ----------------------------------------------------------------------------


def test_name_und_spitzname_speichern(kind, anna):
    antwort = kind.post(u("kind_profil"), {"anzeigename": "Annabelle", "spitzname": "Anni"})
    assert antwort.status_code == 302
    html = kind.get(u("kind_einstellungen")).content.decode()
    assert 'value="Annabelle"' in html and 'value="Anni"' in html
    assert "Hallo Anni!" in kind.get(u("kind_heim")).content.decode()


def test_doppelter_name_zeigt_hinweis(kind, ben):
    antwort = kind.post(u("kind_profil"), {"anzeigename": "bEN", "spitzname": ""})
    assert antwort.status_code == 422
    assert "Diesen Namen gibt es schon" in antwort.content.decode()


def test_spitzname_auf_der_startseite(client, anna):
    services.kind_selbst_aendern(anna, "Anna", "Anni")
    html = client.get(reverse("konten:start")).content.decode()
    assert "Anni" in html


# --- Code ---------------------------------------------------------------------------------------


def test_code_aendern_ueber_die_seite(kind, anna):
    antwort = kind.post(
        u("kind_code"), {"alt": PIN, "neu": NEUE_PIN, "neu2": NEUE_PIN}, follow=True
    )
    assert "Dein Code ist geändert" in antwort.content.decode()
    assert authenticate(None, kind=anna, pin=NEUE_PIN) == anna
    assert AuditEintrag.objects.filter(aktion="konten.pin_geaendert", kind=anna).exists()


def test_falscher_alter_code(kind, anna):
    antwort = kind.post(u("kind_code"), {"alt": FALSCHE_PIN, "neu": NEUE_PIN, "neu2": NEUE_PIN})
    assert antwort.status_code == 422 and "Der alte Code stimmt nicht" in antwort.content.decode()
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_neue_codes_verschieden_oder_zu_kurz(kind, anna):
    assert kind.post(u("kind_code"), {"alt": PIN, "neu": NEUE_PIN, "neu2": "1"}).status_code == 422
    assert kind.post(u("kind_code"), {"alt": PIN, "neu": "12", "neu2": "12"}).status_code == 422
    assert authenticate(None, kind=anna, pin=PIN) == anna


def test_fehlversuche_in_den_einstellungen_sperren(kind, anna, uhr):
    for _ in range(4):
        kind.post(u("kind_code"), {"alt": FALSCHE_PIN, "neu": NEUE_PIN, "neu2": NEUE_PIN})
    antwort = kind.post(u("kind_code"), {"alt": FALSCHE_PIN, "neu": NEUE_PIN, "neu2": NEUE_PIN})
    assert antwort.status_code == 429
    assert selectors.kind_gesperrt_bis(anna) is not None


# --- Mood wählen und anzeigen -------------------------------------------------------------------


def test_mood_waehlen_und_anzeigen(kind, anna, client):
    html = kind.get(u("kind_einstellungen")).content.decode()
    assert html.count("<option") >= 51  # 50 Moods + "Kein Mood"
    assert "Kein Mood" in html and "Faultier-Modus" in html
    assert kind.post(u("kind_mood"), {"mood": "faultier"}).status_code == 302
    assert "🦥 Faultier-Modus" in kind.get(u("kind_heim")).content.decode()
    start = client.get(reverse("konten:start")).content.decode()
    assert "🦥 Faultier-Modus" in start and "nw-profil__rolle" in start
    kind.post(u("kind_mood"), {"mood": ""})
    assert "Faultier-Modus" not in client.get(reverse("konten:start")).content.decode()


def test_unbekannter_mood_wird_abgelehnt(kind, anna):
    assert kind.post(u("kind_mood"), {"mood": "unsinn"}).status_code == 422
    anna.refresh_from_db()
    assert anna.mood == ""


def test_mood_zeile_wird_maskiert(kind, anna, mama, client):
    eigen = MoodEigen.objects.create(text='"><img src=x>')
    services.mood_setzen(anna, eigen.schluessel)
    assert "<img src=x>" not in client.get(reverse("konten:start")).content.decode()
    assert "<img src=x>" not in kind.get(u("kind_einstellungen")).content.decode()


# --- Vorschläge ---------------------------------------------------------------------------------


def test_vorschlag_benachrichtigt_eltern(kind, anna):
    antwort = kind.post(u("kind_mood_vorschlag"), {"text": "Waffel-Laune"}, follow=True)
    assert "Danke" in antwort.content.decode()
    ereignis = Ereignis.objects.get(typ_id=events.MOOD_VORGESCHLAGEN)
    assert ereignis.kind == anna and ereignis.daten["vorschlag"] == "Waffel-Laune"
    assert "Waffel-Laune" in kind.get(u("kind_einstellungen")).content.decode()  # offen sichtbar


def test_vorschlag_grenzen_und_escaping(kind, anna):
    for text in ("Eins", "Zwei", "Drei"):
        assert kind.post(u("kind_mood_vorschlag"), {"text": text}).status_code == 302
    antwort = kind.post(u("kind_mood_vorschlag"), {"text": "Vier"})
    assert antwort.status_code == 422 and "3 offene Vorschläge" in antwort.content.decode()
    assert kind.post(u("kind_mood_vorschlag"), {"text": "x" * 41}).status_code == 422
    antwort = kind.post(u("kind_mood_vorschlag"), {"text": "<script>alert(1)</script>"})
    assert antwort.status_code == 422
    assert "<script>alert(1)</script>" not in antwort.content.decode()


# --- Eltern: Moods verwalten --------------------------------------------------------------------


def test_eltern_sehen_vorschlaege_und_zaehler(eltern, anna):
    services.mood_vorschlagen(anna, "Waffel-Laune")
    html = eltern.get(u("eltern_moods")).content.decode()
    assert "Waffel-Laune" in html and "von Anna" in html
    dashboard = eltern.get(u("eltern_heim")).content.decode()
    assert u("eltern_moods") in dashboard  # Schnellzugriff mit Zähler
    assert 'data-zaehler="1"' in dashboard  # Zähler am Schnellzugriff „Moods“
    # „Offen“ zählt nur Meldungen und Konflikte, keine Mood-Vorschläge
    assert 'data-zahl="offen"><strong class="zahl__wert">0<' in dashboard


def test_eltern_lassen_zu_und_alle_koennen_waehlen(eltern, anna, ben):
    v = services.mood_vorschlagen(anna, "Waffel-Laune")
    assert eltern.post(u("eltern_mood_zulassen", v.pk)).status_code == 302
    v.refresh_from_db()
    assert v.status == VorschlagStatus.ZUGELASSEN
    ereignis = Ereignis.objects.get(typ_id=events.MOOD_ZUGELASSEN)
    assert ereignis.kind == anna
    c = Client()
    kind_anmelden(c, ben)
    assert "Waffel-Laune" in c.get(u("kind_einstellungen")).content.decode()
    # zweimal entscheiden geht nicht
    assert eltern.post(u("eltern_mood_ablehnen", v.pk)).status_code == 404


def test_eltern_lehnen_ab(eltern, anna):
    v = services.mood_vorschlagen(anna, "Doof")
    eltern.post(u("eltern_mood_ablehnen", v.pk))
    v.refresh_from_db()
    assert v.status == VorschlagStatus.ABGELEHNT
    assert Ereignis.objects.get(typ_id=events.MOOD_ABGELEHNT).kind == anna
    assert not MoodEigen.objects.exists()


def test_eltern_ergaenzen_entfernen_und_blenden_aus(eltern, kind, anna):
    assert eltern.post(u("eltern_mood_neu"), {"text": "Keks-Kaiser"}).status_code == 302
    assert eltern.post(u("eltern_mood_neu"), {"text": "Pizza-Power"}).status_code == 422
    eigen = MoodEigen.objects.get(text="Keks-Kaiser")
    assert "Keks-Kaiser" in kind.get(u("kind_einstellungen")).content.decode()
    eltern.post(u("eltern_mood_entfernen", eigen.pk))
    assert "Keks-Kaiser" not in kind.get(u("kind_einstellungen")).content.decode()
    eltern.post(u("eltern_mood_katalog", "pizza"), {"ausblenden": "1"})
    assert "Pizza-Power" not in kind.get(u("kind_einstellungen")).content.decode()
    assert "ausgeblendet" in eltern.get(u("eltern_moods")).content.decode()
    eltern.post(u("eltern_mood_katalog", "pizza"), {})
    assert "Pizza-Power" in kind.get(u("kind_einstellungen")).content.decode()


def test_kinder_sehen_die_mood_verwaltung_nicht(kind, anna):
    v = services.mood_vorschlagen(anna, "Neu")
    assert kind.get(u("eltern_moods")).status_code in (302, 403)
    assert kind.post(u("eltern_mood_zulassen", v.pk)).status_code in (302, 403)
    assert kind.post(u("eltern_mood_neu"), {"text": "X"}).status_code in (302, 403)
    assert kind.post(u("eltern_mood_katalog", "pizza"), {"ausblenden": "1"}).status_code in (
        302,
        403,
    )
    v.refresh_from_db()
    assert v.status == VorschlagStatus.OFFEN and not MoodEigen.objects.exists()


# --- Eltern: Code je Kind ändern ----------------------------------------------------------------


def test_eltern_aendern_den_code_jederzeit(eltern, anna):
    antwort = eltern.post(u("familie_kind_pin", anna.pk), {"pin": NEUE_PIN})
    assert antwort.status_code == 302
    assert authenticate(None, kind=anna, pin=NEUE_PIN) == anna
    assert AuditEintrag.objects.filter(aktion="konten.pin_zurueckgesetzt", kind=anna).exists()
    assert eltern.post(u("familie_kind_pin", anna.pk), {"pin": "1"}).status_code == 422
    assert "PIN zurücksetzen" in eltern.get(u("familie")).content.decode()


def test_kind_darf_den_code_nicht_ueber_die_eltern_seite_setzen(kind, anna, ben):
    antwort = kind.post(u("familie_kind_pin", ben.pk), {"pin": NEUE_PIN})
    assert antwort.status_code in (302, 403)
    assert authenticate(None, kind=ben, pin=PIN) == ben


# --- Punkte-Verlauf -----------------------------------------------------------------------------


def test_anerkennung_im_verlauf_des_kindes(kind, anna, mama):
    from apps.aufgaben import anerkennung

    anerkennung.vergeben(anna, 8, "Tisch gedeckt", von=mama)
    html = kind.get(u("kind_bereich")).content.decode()
    assert "Letzte Punkte" in html and "Anerkennung: Tisch gedeckt" in html and "+8" in html
