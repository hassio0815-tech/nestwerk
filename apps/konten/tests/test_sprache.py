"""Zweisprachigkeit (Deutsch/Englisch): Gerätecookie, eigene Sprache, Einstellung im Konto."""

import re

import pytest
from django.conf import settings
from django.urls import reverse

from apps.kern.models import AuditEintrag
from apps.konten import services, wappen

from .conftest import angemeldet

pytestmark = pytest.mark.django_db

COOKIE = settings.LANGUAGE_COOKIE_NAME


def test_startseite_ist_standardmaessig_deutsch(anna, client):
    html = client.get(reverse("konten:start")).content.decode()
    assert "Wer ist heute dabei?" in html
    assert re.search(r"<h1[^>]*>Guten (Morgen|Tag|Abend)!</h1>", html)


def test_startseite_mit_englischem_cookie(anna, client):
    client.cookies[COOKIE] = "en"
    html = client.get(reverse("konten:start")).content.decode()
    assert re.search(r"<h1[^>]*>Good (morning|afternoon|evening)!</h1>", html)
    assert "Who&#x27;s here today?" in html or "Who's here today?" in html
    assert ">Kids<" in html
    assert "Wer ist heute dabei?" not in html
    assert "<html" in html and 'lang="en"' in html


def test_gruss_wechselt_zwischen_den_sprachen(anna, client):
    html = client.get(reverse("konten:start")).content.decode()
    assert "data-gruss-de=" in html and "data-gruss-en=" in html


def test_setlang_setzt_das_cookie(anna, client):
    antwort = client.post(reverse("set_language"), {"language": "en", "next": "/"})
    assert antwort.status_code == 302
    assert antwort.cookies[COOKIE].value == "en"
    html = client.get(reverse("konten:start")).content.decode()
    assert "Good" in html and "Guten" not in html.split("data-gruss-wechsel")[0]


def test_unbekannte_sprache_setzt_kein_cookie(anna, client):
    antwort = client.post(reverse("set_language"), {"language": "xx", "next": "/"})
    assert COOKIE not in antwort.cookies or antwort.cookies[COOKIE].value != "xx"


def test_eigene_sprache_schlaegt_das_cookie(anna, client):
    services.sprache_setzen(anna, "de")
    angemeldet(client, anna)
    client.cookies[COOKIE] = "en"
    html = client.get(reverse("konten:kind_heim")).content.decode()
    assert "Hallo Anna!" in html


def test_eigene_sprache_englisch_trotz_deutschem_cookie(anna, client):
    services.sprache_setzen(anna, "en")
    angemeldet(client, anna)
    client.cookies[COOKIE] = "de"
    html = client.get(reverse("konten:kind_heim")).content.decode()
    assert "Hello Anna!" in html


def test_ohne_eigene_sprache_gilt_das_cookie(anna, client):
    angemeldet(client, anna)
    client.cookies[COOKIE] = "en"
    html = client.get(reverse("konten:kind_heim")).content.decode()
    assert "Hello Anna!" in html


def test_sprache_aendern_per_post(anna, client):
    angemeldet(client, anna)
    antwort = client.post(reverse("konten:sprache_setzen"), {"sprache": "en"})
    assert antwort.status_code == 302
    anna.refresh_from_db()
    assert anna.sprache == "en"
    assert AuditEintrag.objects.filter(aktion="konten.sprache_gesetzt").exists()
    client.post(reverse("konten:sprache_setzen"), {"sprache": ""})
    anna.refresh_from_db()
    assert anna.sprache == ""


def test_sprache_aendern_eltern(mama, client):
    angemeldet(client, mama)
    client.post(reverse("konten:sprache_setzen"), {"sprache": "en", "next": "/eltern/"})
    mama.refresh_from_db()
    assert mama.sprache == "en"
    html = client.get(reverse("konten:eltern_heim")).content.decode()
    assert "Log out" in html


def test_sprache_aendern_lehnt_unbekannte_werte_ab(anna, client):
    angemeldet(client, anna)
    antwort = client.post(reverse("konten:sprache_setzen"), {"sprache": "fr"})
    assert antwort.status_code == 400
    anna.refresh_from_db()
    assert anna.sprache == ""


def test_sprache_aendern_braucht_anmeldung_und_post(anna, client):
    antwort = client.post(reverse("konten:sprache_setzen"), {"sprache": "en"})
    assert antwort.status_code == 302
    anna.refresh_from_db()
    assert anna.sprache == ""
    angemeldet(client, anna)
    assert client.get(reverse("konten:sprache_setzen")).status_code == 405


def test_sprache_aendern_verlangt_csrf():
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    antwort = client.post(reverse("konten:sprache_setzen"), {"sprache": "en"})
    assert antwort.status_code == 403


def test_sprache_aendern_leitet_nicht_auf_fremde_adressen(anna, client):
    angemeldet(client, anna)
    antwort = client.post(
        reverse("konten:sprache_setzen"), {"sprache": "en", "next": "https://boese.example/"}
    )
    assert antwort.status_code == 302
    assert "boese.example" not in antwort["Location"]


def test_einstellungs_baustein_zeigt_drei_optionen(anna, rf):
    from django.template.loader import render_to_string

    anna.sprache = "en"
    anfrage = rf.get("/")
    anfrage.user = anna
    html = render_to_string("konten/_sprache_einstellung.html", {"request": anfrage})
    assert "Automatisch" in html and "Deutsch" in html and "English" in html
    assert reverse("konten:sprache_setzen") in html
    assert 'value="en" lang="en" class="ist-aktiv"' in html


def test_wappen_sind_uebersetzt(mama):
    from django.utils import translation

    w = wappen.info("hausdrache")
    assert str(w.titel) == "Hausdrache"
    with translation.override("en"):
        assert str(w.titel) == "House Dragon"
        assert str(w.spruch) == "Guards the fridge"
        assert "Bank of Mum and Dad" in {str(x.titel) for x in wappen.KATALOG}
