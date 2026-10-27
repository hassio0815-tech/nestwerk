"""Zweisprachigkeit: Englisch kommt aus den .po-Dateien, Deutsch bleibt Standard."""

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from apps.aufgaben.wiederholung import WOECHENTLICH, Plan


@pytest.fixture(autouse=True)
def _sprache_zuruecksetzen():
    """Die Locale-Middleware aktiviert die Sprache im Test-Thread; danach wieder Deutsch."""
    yield
    translation.activate(settings.LANGUAGE_CODE)


def test_eltern_liste_auf_englisch(eltern_client):
    eltern_client.cookies["nestwerk_sprache"] = "en"
    html = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "New task" in html
    assert "Neue Aufgabe" not in html


def test_eltern_liste_standard_deutsch(eltern_client):
    html = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "Neue Aufgabe" in html


def test_kind_seite_auf_englisch(kind_client):
    kind_client.cookies["nestwerk_sprache"] = "en"
    html = kind_client.get(reverse("aufgaben:kind")).content.decode()
    assert "My tasks" in html
    assert "Meine Aufgaben" not in html


def test_planbeschreibung_uebersetzt():
    plan = Plan(art=WOECHENTLICH, wochentage=0b0000101)
    assert plan.beschreiben() == "Jede Woche: Mo, Mi"
    with translation.override("en"):
        assert plan.beschreiben() == "Every week: Mon, Wed"
