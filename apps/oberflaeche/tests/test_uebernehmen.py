"""Wochenvorschau als Kalenderleiste; Aufgabe vormerken, anmelden, übernehmen."""

from datetime import time, timedelta

import pytest
from django.urls import reverse

from apps.aufgaben import services as aufgaben_services
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.kern import zeit
from apps.konten import services as konten
from apps.konten.tests.conftest import PIN, eltern_anmelden, kind_anmelden

from . import conftest as _  # noqa: F401  (Fixtures)

VORMERKEN = "oberflaeche:uebernehmen_vormerken"
SCHLUESSEL = "nach_login_uebernehmen"


@pytest.fixture
def ben(db):
    return konten.kind_anlegen("Ben", "4321", akzentfarben=["#3377ff"])


def taeglich(mama, titel="Zähne putzen", **kw):
    kw.setdefault("punkte", 7)
    kw.setdefault("start_datum", zeit.heute() - timedelta(days=3))
    kw.setdefault("fenster_von", time(0, 0))
    kw.setdefault("fenster_bis", time(23, 59))
    aufgabe = Aufgabe.objects.create(
        titel=titel, erstellt_von=mama, wiederholungsart="intervall", intervall_tage=1, **kw
    )
    aufgaben_services.instanzen_erzeugen(aufgaben=Aufgabe.objects.filter(pk=aufgabe.pk))
    return aufgabe


def morgen():
    return zeit.heute() + timedelta(days=1)


def vormerken(client, aufgabe_id, datum):
    return client.post(reverse(VORMERKEN), {"aufgabe": aufgabe_id, "datum": str(datum)})


def instanz_von(aufgabe):
    return AufgabenInstanz.objects.get(aufgabe=aufgabe, plan_datum=morgen())


# --- Kalenderleiste ---------------------------------------------------------------------------


def test_leiste_hat_sieben_tage_mit_punkt_und_heute(client, mama, anna):
    taeglich(mama)
    html = client.get("/").content.decode()
    assert html.count("data-woche-tag") == 7
    assert html.count("data-woche-punkt") == 7  # täglich: jeder Tag hat feste Aufgaben
    assert html.count('aria-current="date"') == 1
    assert "<ol" in html and "Übernehmen" in html


def test_tage_ohne_aufgaben_sind_nicht_klickbar(client, mama):
    html = client.get("/").content.decode()
    assert html.count("data-woche-tag") == 7
    assert "data-woche-punkt" not in html and html.count("<dialog") == 0
    assert html.count("disabled") == 7 and "aria-controls" not in html


def test_popup_zeigt_aufgabe_kind_xp_rhythmus_und_alle_kinder(client, mama, anna):
    taeglich(mama, titel="Zimmer aufräumen", zugewiesen_an=anna)
    taeglich(mama, titel="Tisch decken")
    html = client.get("/").content.decode()
    assert html.count("<dialog") == 7  # ein Popup je Tag mit Aufgaben
    assert "Zimmer aufräumen" in html and "Tisch decken" in html
    assert "Anna" in html and "Alle Kinder" in html and "7&nbsp;XP" in html
    assert 'name="aufgabe"' in html and 'name="datum"' in html and "csrfmiddlewaretoken" in html


def test_je_kind_aufgaben_zeigen_den_kindernamen(client, mama, anna, ben):
    taeglich(mama, titel="Wäsche", zugewiesen_an=anna)
    taeglich(mama, titel="Wäsche", zugewiesen_an=ben)
    html = client.get("/").content.decode()
    assert html.count("Wäsche") >= 14 and "Anna" in html and "Ben" in html


def test_anmeldekacheln_bleiben_neben_der_leiste(client, mama, anna):
    taeglich(mama)
    html = client.get("/").content.decode()
    assert "data-wochenvorschau" in html and "kinder-titel" in html and "eltern-titel" in html


# --- Vormerken --------------------------------------------------------------------------------


def test_vormerken_merkt_und_zeigt_banner_mit_abbrechen(client, mama, anna):
    aufgabe = taeglich(mama)
    antwort = vormerken(client, aufgabe.pk, morgen())
    assert antwort.status_code == 302 and antwort["Location"] == reverse("konten:start")
    assert client.session[SCHLUESSEL]
    html = client.get("/").content.decode()
    assert "data-uebernehmen-banner" in html and "Zähne putzen" in html
    assert reverse("oberflaeche:uebernehmen_abbrechen") in html


def test_vormerken_nur_per_post(client, mama):
    assert client.get(reverse(VORMERKEN)).status_code == 405


@pytest.mark.parametrize(
    "aufgabe, datum",
    [
        ("abc", "2026-11-09"),
        ("1; DROP", "2026-11-09"),
        ("", ""),
        ("-5", "heute"),
        ("99999", "2026-02-30"),
    ],
)
def test_ungueltige_eingaben_werden_ignoriert(client, mama, aufgabe, datum):
    taeglich(mama)
    antwort = client.post(reverse(VORMERKEN), {"aufgabe": aufgabe, "datum": datum})
    assert antwort.status_code == 302 and SCHLUESSEL not in client.session


def test_aufgabe_ausserhalb_der_woche_oder_unbekannt_wird_nicht_gemerkt(client, mama):
    aufgabe = taeglich(mama)
    assert vormerken(client, aufgabe.pk, zeit.heute() + timedelta(days=8)).status_code == 302
    assert SCHLUESSEL not in client.session
    vormerken(client, aufgabe.pk + 1000, morgen())
    assert SCHLUESSEL not in client.session


def test_abbrechen_loescht_die_absicht(client, mama):
    vormerken(client, taeglich(mama).pk, morgen())
    antwort = client.post(reverse("oberflaeche:uebernehmen_abbrechen"))
    assert antwort["Location"] == reverse("konten:start") and SCHLUESSEL not in client.session
    assert "data-uebernehmen-banner" not in client.get("/").content.decode()


def test_abgelaufene_absicht_wird_nicht_beachtet(client, mama, anna, monkeypatch):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    sitzung = client.session
    sitzung[SCHLUESSEL] = {**sitzung[SCHLUESSEL], "t": sitzung[SCHLUESSEL]["t"] - 3600}
    sitzung.save()
    assert "data-uebernehmen-banner" not in client.get("/").content.decode()
    kind_anmelden(client, anna)
    assert instanz_von(aufgabe).kind is None


def test_angemeldete_koennen_nichts_vormerken(client, mama, anna):
    aufgabe = taeglich(mama)
    kind_anmelden(client, anna)
    vormerken(client, aufgabe.pk, morgen())
    assert SCHLUESSEL not in client.session


# --- Anmeldung -> Übernahme -------------------------------------------------------------------


def test_kind_login_uebernimmt_und_zeigt_meldung_einmalig(client, mama, anna):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    antwort = kind_anmelden(client, anna)
    assert antwort["Location"] == "/kind/"
    instanz = instanz_von(aufgabe)
    assert instanz.kind == anna and instanz.status == InstanzStatus.RESERVIERT
    assert SCHLUESSEL not in client.session
    html = client.get("/kind/").content.decode()
    assert "gehört jetzt dir" in html and "toast--erfolg" in html
    assert "gehört jetzt dir" not in client.get("/kind/").content.decode()  # nur einmal


def test_aufgabe_eines_anderen_kindes_wird_nicht_uebernommen(client, mama, anna, ben):
    aufgabe = taeglich(mama, zugewiesen_an=ben)
    vormerken(client, aufgabe.pk, morgen())
    kind_anmelden(client, anna)
    assert instanz_von(aufgabe).kind is None
    html = client.get("/kind/").content.decode()
    assert "anderes Kind" in html and "toast--fehler" in html


def test_ohne_instanz_freundliche_meldung(client, mama, anna):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    AufgabenInstanz.objects.filter(aufgabe=aufgabe).delete()
    kind_anmelden(client, anna)
    html = client.get("/kind/").content.decode()
    assert "noch nicht übernommen" in html
    assert AufgabenInstanz.objects.filter(aufgabe=aufgabe).count() == 0


def test_schon_uebernommen_sagt_hast_du_schon(client, mama, anna):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    kind_anmelden(client, anna)
    client.post(reverse("konten:abmelden"))
    vormerken(client, aufgabe.pk, morgen())
    kind_anmelden(client, anna)
    assert "hast du schon" in client.get("/kind/").content.decode()


def test_falsche_pin_behaelt_die_absicht_fuer_den_zweiten_versuch(client, mama, anna):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    assert kind_anmelden(client, anna, pin="0000").status_code == 401
    assert SCHLUESSEL in client.session and instanz_von(aufgabe).kind is None
    kind_anmelden(client, anna, pin=PIN)
    assert instanz_von(aufgabe).kind == anna


def test_eltern_login_verwirft_die_absicht_ohne_uebernahme(client, mama, anna):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    eltern_anmelden(client, mama)
    assert SCHLUESSEL not in client.session and instanz_von(aufgabe).kind is None
    client.post(reverse("konten:abmelden"))
    kind_anmelden(client, anna)
    assert instanz_von(aufgabe).kind is None
    assert "gehört jetzt dir" not in client.get("/kind/").content.decode()


def test_kein_zweites_kind_erbt_die_absicht(client, mama, anna, ben):
    aufgabe = taeglich(mama)
    vormerken(client, aufgabe.pk, morgen())
    kind_anmelden(client, anna)
    client.post(reverse("konten:abmelden"))
    kind_anmelden(client, ben, pin="4321")
    assert instanz_von(aufgabe).kind == anna


# --- Englisch ---------------------------------------------------------------------------------


def test_englisch_leiste_popup_und_meldung(client, mama, anna):
    aufgabe = taeglich(mama)
    html = client.get("/", headers={"accept-language": "en"}).content.decode()
    assert "Take it" in html and "fixed task" in html and "Übernehmen" not in html
    vormerken(client, aufgabe.pk, morgen())
    kind_anmelden(client, anna, headers={"accept-language": "en"})
    # Meldung wird in der Sprache der Anmeldung erzeugt (Kind ohne eigene Sprache: Browser)
    html = client.get("/kind/", headers={"accept-language": "en"}).content.decode()
    assert "is yours now" in html
