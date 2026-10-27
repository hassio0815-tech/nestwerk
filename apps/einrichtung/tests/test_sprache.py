"""Der Assistent folgt dem Sprach-Cookie des Geräts."""

import pytest
from django.conf import settings

from .conftest import url

pytestmark = pytest.mark.django_db


def test_schritt_ist_standardmaessig_deutsch(client):
    html = client.get(url(1)).content.decode()
    assert "Willkommen bei" in html
    assert "Name der App" in html


def test_schritt_auf_englisch(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    html = client.get(url(1)).content.decode()
    assert "Welcome to" in html
    assert "Name of the app" in html
    assert "Willkommen bei" not in html
    assert "Step 1: Welcome" in html


def test_fehlermeldung_auf_englisch(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    client.post(url(1), {"app_name": "Nest"})
    antwort = client.post(url(2), {})
    html = antwort.content.decode()
    assert "This field is required" in html or "Please set a family password." in html
