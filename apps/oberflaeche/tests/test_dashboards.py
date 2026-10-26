"""Kinder-, Eltern- und Tablet-Dashboard, Routing, Rollentrennung, Kachel-Registry."""

import pytest
from django.urls import resolve, reverse

from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.kern import registry
from apps.kern.registry import ELTERN, KIND, TABLET, Kachel
from apps.konten.tests.conftest import angemeldet, client_fuer, kind_anmelden

from .conftest import gutschrift

ELTERN_URLS = [
    "oberflaeche:eltern_heim",
    "oberflaeche:einstellungen",
    "oberflaeche:familie",
    "konten:geraete",
]


def instanz(mama, anna, status, titel="Rasen mähen"):
    aufgabe = Aufgabe.objects.create(
        titel=titel, punkte=10, erstellt_von=mama, wiederholungsart="einmalig", freigabeart="eltern"
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        kind=anna if status != InstanzStatus.OFFEN else None,
        status=status,
        titel_snapshot=titel,
        punkte_snapshot=10,
        freigabeart_snapshot="eltern",
    )


# --- Routing ---------------------------------------------------------------------------------


def test_wurzel_gehoert_der_weiche_und_dashboards_den_rollen_urls(db):
    assert resolve("/").func.__module__ == "apps.oberflaeche.views"
    assert resolve("/kind/").func.__module__ == "apps.oberflaeche.views"
    assert resolve("/eltern/").func.__module__ == "apps.oberflaeche.views"
    assert resolve("/tablet/").func.__module__ == "apps.oberflaeche.views"
    assert reverse("konten:kind_heim") == reverse("oberflaeche:kind_heim") == "/kind/"


def test_weiterleitung_je_rolle_und_geraet(client, mama, anna, tablet):
    assert client.get("/").status_code == 200  # Anmeldeauswahl
    assert client_fuer(tablet).get("/")["Location"] == reverse("oberflaeche:tablet")
    kind = angemeldet(client_fuer(), anna)
    assert kind.get("/")["Location"] == "/kind/"
    eltern = angemeldet(client_fuer(), mama)
    assert eltern.get("/")["Location"] == "/eltern/"


# --- Rollen- und Gerätetrennung --------------------------------------------------------------


@pytest.mark.parametrize("name", ELTERN_URLS)
def test_kind_bekommt_403_auf_eltern_seiten(kind_client, name):
    assert kind_client.get(reverse(name)).status_code == 403


@pytest.mark.parametrize("name", ELTERN_URLS)
def test_ohne_anmeldung_weiter_zur_anmeldung(client, name):
    antwort = client.get(reverse(name))
    assert antwort.status_code == 302 and reverse("konten:start") in antwort["Location"]


def test_eltern_bekommen_403_auf_kinder_dashboard(eltern_client):
    assert eltern_client.get(reverse("oberflaeche:kind_heim")).status_code == 403


def test_kind_darf_familie_nicht_per_post_aendern(kind_client, anna):
    for url in (
        reverse("oberflaeche:familie_kind_pin", args=[anna.pk]),
        reverse("oberflaeche:familie_kind_neu"),
        reverse("oberflaeche:familie_passwort"),
        reverse("oberflaeche:einstellungen_speichern", args=["allgemein"]),
    ):
        assert kind_client.post(url, {}).status_code == 403


# --- Kinder-Dashboard ------------------------------------------------------------------------


def test_kind_dashboard_zeigt_konto_und_aufgaben(kind_client, anna, mama):
    gutschrift(anna, 25, mama)
    instanz(mama, anna, InstanzStatus.OFFEN, titel="Fenster putzen")
    instanz(mama, anna, InstanzStatus.RESERVIERT, titel="Müll raus")
    html = kind_client.get("/kind/").content.decode()
    assert "Hallo Anna" in html
    assert "25 XP" in html
    assert "Fenster putzen" in html and "Müll raus" in html
    for schluessel in ("kind_konto", "kind_offene", "kind_laufende", "kind_belohnungen"):
        assert f'data-kachel="oberflaeche.{schluessel}"' in html
    assert reverse("belohnung:kind") in html


def test_akzentfarbe_waehlen(kind_client, anna):
    antwort = kind_client.post(reverse("oberflaeche:akzent"), {"akzent": "gruen"})
    assert antwort.status_code == 302
    anna.refresh_from_db()
    assert anna.akzentfarben == ["#22c55e"]
    assert 'data-akzent="gruen"' in kind_client.get("/kind/").content.decode()
    kind_client.post(reverse("oberflaeche:akzent"), {"akzent": "#000000"})  # nicht in der Palette
    anna.refresh_from_db()
    assert anna.akzentfarben == ["#22c55e"]


# --- Eltern-Dashboard ------------------------------------------------------------------------


def test_eltern_dashboard_zaehler_kinder_und_system(eltern_client, mama, anna):
    instanz(mama, anna, InstanzStatus.GEMELDET, titel="Bad putzen")
    instanz(mama, anna, InstanzStatus.KONFLIKT, titel="Auto waschen")
    gutschrift(anna, 7, mama)
    html = eltern_client.get("/eltern/").content.decode()
    assert 'data-zaehler="2"' in html  # eine Meldung + ein Konflikt
    assert "Anna" in html and "7 XP" not in html  # XP-Details im Dungeon-Bereich
    for schluessel in ("entscheidungen", "kinder", "ereignisse", "system", "schnellzugriff"):
        assert f'data-kachel="oberflaeche.eltern_{schluessel}"' in html
    assert "Datensicherung" in html and "noch nie gelaufen" in html


def test_systemstatus_zeigt_letzten_joblauf(eltern_client):
    from apps.kern.models import JobLauf

    JobLauf.objects.create(name="db_sichern", status="ok")
    html = eltern_client.get("/eltern/").content.decode()
    assert "noch nie gelaufen" in html  # backup_pruefen fehlt noch
    JobLauf.objects.create(name="backup_pruefen", status="fehler")
    assert "Fehler" in eltern_client.get("/eltern/").content.decode()


# --- Kachel-Registry -------------------------------------------------------------------------


@pytest.mark.parametrize("zielgruppe,url", [(KIND, "/kind/"), (ELTERN, "/eltern/")])
def test_registrierte_kachel_erscheint(client, mama, anna, zielgruppe, url):
    with registry.kachel_verzeichnis.isoliert():
        registry.kachel_registrieren(
            Kachel(
                "testmodul.rang",
                "testmodul",
                "Rang-Kachel",
                "komponenten/chip.html",
                {zielgruppe},
                lambda request: {"x": 1},
                reihenfolge=5,
            )
        )
        angemeldet(client, anna if zielgruppe == KIND else mama)
        html = client.get(url).content.decode()
    assert 'data-kachel="testmodul.rang"' in html and "Rang-Kachel" in html


def test_defekte_oder_unsichtbare_kachel_kippt_das_dashboard_nicht(client, anna):
    def kaputt(request):
        raise RuntimeError("boom")

    with registry.kachel_verzeichnis.isoliert():
        for name, kwargs in (("a", {"kontext": kaputt}), ("b", {"sichtbar": lambda r: False})):
            registry.kachel_registrieren(
                Kachel(f"t.{name}", "t", name, "komponenten/chip.html", {KIND}, **kwargs)
            )
        angemeldet(client, anna)
        antwort = client.get("/kind/")
    assert antwort.status_code == 200
    assert 'data-kachel="t.a"' not in antwort.content.decode()
    assert 'data-kachel="t.b"' not in antwort.content.decode()


# --- Tablet ----------------------------------------------------------------------------------


def test_tablet_seite_und_teil_zeigen_guthaben_und_offene(client, mama, anna, ben):
    gutschrift(anna, 42, mama)
    instanz(mama, anna, InstanzStatus.OFFEN)
    voll = client.get("/tablet/")
    assert voll.status_code == 200
    html = voll.content.decode()
    assert 'hx-get="/tablet/teil/"' in html and "every 10s" in html
    teil = client.get(reverse("oberflaeche:tablet_teil")).content.decode()
    assert "Anna" in teil and "Ben" in teil and ">42<" in teil.replace(" ", "").replace("\n", "")
    assert teil.count("1 offen") == 2  # freie Aufgabe sehen alle Kinder
    assert reverse("konten:kind_pin", args=[anna.pk]) in teil
    assert "<html" not in teil  # nur Ausschnitt


def test_tablet_teil_aktualisiert_sich(client, mama, anna):
    assert "0 offen" in client.get("/tablet/teil/").content.decode()
    instanz(mama, anna, InstanzStatus.OFFEN)
    assert "1 offen" in client.get("/tablet/teil/").content.decode()


def test_tablet_polling_verlaengert_die_sitzung_nicht(anna, tablet, uhr):
    c = client_fuer(tablet)
    kind_anmelden(c, anna)
    for _ in range(2):
        uhr.weiter(seconds=100)
        assert c.get("/tablet/teil/").status_code == 200
    uhr.weiter(seconds=101)  # 301 s seit der letzten aktiven Anfrage
    assert c.get("/kind/").status_code == 302
    assert c.get("/kind/")["Location"].startswith(reverse("konten:start"))


def test_tablet_slot_nimmt_registry_kacheln_auf(client, anna):
    with registry.kachel_verzeichnis.isoliert():
        registry.kachel_registrieren(
            Kachel("fz.leiste", "familienziel", "Familienziel", "komponenten/chip.html", {TABLET})
        )
        assert 'data-kachel="fz.leiste"' in client.get("/tablet/").content.decode()


def test_tablet_nur_im_heimnetz(client, anna, settings):
    from apps.kern import einstellungen

    einstellungen.setzen("konten.kind_netze_cidr", ["192.168.0.0/16"], akteur=None)
    antwort = client.get("/tablet/", REMOTE_ADDR="8.8.8.8")
    assert antwort.status_code == 403
    assert client.get("/tablet/teil/", REMOTE_ADDR="8.8.8.8").status_code == 403
    assert client.get("/tablet/", REMOTE_ADDR="192.168.1.5").status_code == 200


def test_tablet_intervall_ist_einstellung(client, anna):
    from apps.kern import einstellungen

    einstellungen.setzen("oberflaeche.tablet_aktualisierung_sekunden", 20, akteur=None)
    assert "every 20s" in client.get("/tablet/").content.decode()


def test_modul_launcher_nur_fuer_eltern_und_datengetrieben(eltern_client):
    html = eltern_client.get(reverse("oberflaeche:module")).content.decode()
    assert "Eltern-Bereich" in html and reverse("oberflaeche:einstellungen") in html
    from django.test import Client

    assert Client().get(reverse("oberflaeche:module")).status_code == 302


# --- Dungeon-Bereich der Eltern ------------------------------------------------------------------


def test_eltern_dashboard_ohne_spielkacheln_dungeon_mit(eltern_client):
    heim = eltern_client.get("/eltern/").content.decode()
    for schluessel in ("spielregeln.eltern_raenge", "avatar.eltern_mods", "sondertag.eltern"):
        assert f'data-kachel="{schluessel}"' not in heim
    assert 'data-kachel="oberflaeche.eltern_entscheidungen"' in heim
    dungeon = eltern_client.get("/eltern/dungeon/").content.decode()
    assert 'data-kachel="spielregeln.eltern_raenge"' in dungeon
    assert 'data-kachel="oberflaeche.eltern_entscheidungen"' not in dungeon


def test_dungeon_anzeige_schalter_blendet_menue_und_launcher_aus(eltern_client):
    assert "/eltern/dungeon/" in eltern_client.get("/module/").content.decode()
    assert "/eltern/dungeon/" in eltern_client.get("/eltern/").content.decode()
    eltern_client.post(reverse("oberflaeche:dungeon_anzeige"), {})  # Haken aus
    assert "/eltern/dungeon/" not in eltern_client.get("/module/").content.decode()
    assert "/eltern/dungeon/" not in eltern_client.get("/eltern/").content.decode()
    assert eltern_client.get("/eltern/dungeon/").status_code == 200  # per Adresse erreichbar
    eltern_client.post(reverse("oberflaeche:dungeon_anzeige"), {"dungeon_anzeigen": "1"})
    assert "/eltern/dungeon/" in eltern_client.get("/module/").content.decode()


def test_kind_alte_spielwelt_adresse_leitet_um(kind_client):
    antwort = kind_client.get("/kind/spielwelt/")
    assert antwort.status_code == 301 and antwort["Location"] == "/kind/dungeon/"
