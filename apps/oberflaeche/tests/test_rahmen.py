"""Einheitlicher Rahmen: Kopfleiste (Start, Lernen, Zahnrad, Abmelden) und Seitenkopf."""

import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten.tests.conftest import PASSWORT, eltern_anmelden, kind_anmelden

ELTERN_SEITEN = [
    "aufgaben:liste",
    "konten:geraete",
    "oberflaeche:einstellungen",
    "benachrichtigung:liste",
    "benachrichtigung:einstellungen",
    "lernen:eltern",
    "lernen:eltern_kinder",
    "spielregeln:raenge",
    "familienziel:eltern",
    "sondertag:eltern",
]
KIND_SEITEN = [
    "aufgaben:kind",
    "belohnung:kind",
    "oberflaeche:kind_einstellungen",
    "lernen:start",
    "lernen:tutor",
    "avatar:kind_wahl",
]


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


def _kopfleiste(html):
    m = re.search(r'<nav class="kopfleiste.*?</nav>', html, re.S)
    assert m, "Kopfleiste fehlt"
    return m.group(0)


def _ziele(leiste):
    return re.findall(r'data-kopf="(\w+)"', leiste)


def test_eltern_kopfleiste_hat_vier_elemente(eltern):
    html = eltern.get(reverse("oberflaeche:einstellungen")).content.decode()
    leiste = _kopfleiste(html)
    assert _ziele(leiste) == ["start", "lernen", "einstellungen", "abmelden"]
    assert reverse("oberflaeche:module") in leiste
    assert reverse("lernen:eltern") in leiste
    assert reverse("oberflaeche:einstellungen") in leiste
    assert 'aria-label="Einstellungen"' in leiste and "#i-zahnrad" in leiste
    assert reverse("konten:abmelden") in leiste and "Abmelden" in leiste


def test_kind_kopfleiste_hat_vier_elemente(kind):
    html = kind.get(reverse("oberflaeche:kind_einstellungen")).content.decode()
    leiste = _kopfleiste(html)
    assert _ziele(leiste) == ["start", "lernen", "einstellungen", "abmelden"]
    assert reverse("konten:kind_heim") in leiste
    assert reverse("lernen:start") in leiste
    assert reverse("oberflaeche:kind_einstellungen") in leiste
    assert 'aria-label="Meine Einstellungen"' in leiste and "#i-zahnrad" in leiste
    assert reverse("konten:abmelden") in leiste


def test_kopfleiste_auch_auf_den_startseiten(eltern, kind):
    assert _ziele(_kopfleiste(eltern.get("/eltern/").content.decode())) == [
        "start",
        "lernen",
        "einstellungen",
        "abmelden",
    ]
    assert _ziele(_kopfleiste(kind.get("/kind/").content.decode())) == [
        "start",
        "lernen",
        "einstellungen",
        "abmelden",
    ]


def test_startseiten_haben_keinen_seitenkopf(eltern, kind):
    assert 'class="seitenkopf"' not in eltern.get("/eltern/").content.decode()
    assert 'class="seitenkopf"' not in kind.get("/kind/").content.decode()


def _pruefe_seitenkopf(antwort):
    assert antwort.status_code == 200
    html = antwort.content.decode()
    assert html.count('class="seitenkopf"') == 1
    assert html.count("<h1") == 1
    kopf = re.search(r'<div class="seitenkopf">(.*?)</div>', html, re.S).group(1)
    assert kopf.count("seitenkopf__zurueck") == 1 and "←" in kopf
    assert kopf.index("seitenkopf__zurueck") < kopf.index("<h1")
    # Zurück-Link vor der Überschrift, nichts Zweites mit Pfeil im Inhalt
    assert html.count("←") == 1


@pytest.mark.parametrize("name", ELTERN_SEITEN)
def test_eltern_unterseite_hat_seitenkopf(eltern, name):
    _pruefe_seitenkopf(eltern.get(reverse(name)))


@pytest.mark.parametrize("name", KIND_SEITEN)
def test_kind_unterseite_hat_seitenkopf(kind, name):
    _pruefe_seitenkopf(kind.get(reverse(name)))
