"""Englische Oberfläche (Entscheidung 45): Sprache per Cookie, Deutsch bleibt Standard."""

from django.conf import settings
from django.urls import reverse

from apps.aufgaben.models import InstanzStatus

from .test_dashboards import instanz


def test_familie_seite_auf_englisch(eltern_client, anna):
    eltern_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    antwort = eltern_client.get(reverse("oberflaeche:familie"))
    html = antwort.content.decode()
    assert '<html lang="en">' in html
    assert "Add a child" in html and "Reset PIN" in html
    assert "Kind anlegen" not in html
    assert "Anna" in html  # Namen der Familie bleiben unübersetzt


def test_einstellungen_titel_auf_englisch(eltern_client):
    eltern_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
    assert "Appearance" in html and "Dungeon area" in html
    assert "Darstellung" not in html


def test_standard_bleibt_deutsch(eltern_client, anna):
    html = eltern_client.get(reverse("oberflaeche:familie")).content.decode()
    assert "Kind anlegen" in html and "Add a child" not in html


def test_kind_dashboard_uebersetzt_start_aufgaben(kind_client, anna, mama):
    """Aus Vorlagen angelegte Aufgaben stehen deutsch in der DB und erscheinen englisch."""
    instanz(mama, anna, InstanzStatus.OFFEN, titel="Müll rausbringen")
    instanz(mama, anna, InstanzStatus.RESERVIERT, titel="Flur saugen")
    instanz(mama, anna, InstanzStatus.OFFEN, titel="Selbst getippte Aufgabe")
    kind_client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    html = kind_client.get("/kind/").content.decode()
    assert "Take out the rubbish" in html
    assert "Müll rausbringen" not in html and "Flur saugen" not in html
    assert "Selbst getippte Aufgabe" in html  # Eltern-Text bleibt unverändert
