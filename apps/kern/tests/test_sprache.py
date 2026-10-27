"""Sprache außerhalb einer Anfrage (``fuer``) und Anzeige von Start-Inhalten (``uebersetzt``)."""

from types import SimpleNamespace

import pytest
from django.utils import translation

from apps.kern import einstellungen, sprache


def test_eigene_sprache_geht_vor(kern_werte):
    einstellungen.setzen("allgemein.sprache", "en", akteur=None)
    assert sprache.fuer(SimpleNamespace(sprache="de")) == "de"


def test_ohne_eigene_sprache_gilt_die_der_familie(kern_werte):
    einstellungen.setzen("allgemein.sprache", "en", akteur=None)
    assert sprache.fuer(SimpleNamespace(sprache="")) == "en"
    assert sprache.fuer(None) == "en"


def test_ohne_alles_deutsch(db):
    assert sprache.fuer(SimpleNamespace(sprache="")) == "de"
    assert sprache.fuer(SimpleNamespace()) == "de"


def test_unbekannte_eigene_sprache_wird_ignoriert(kern_werte):
    einstellungen.setzen("allgemein.sprache", "en", akteur=None)
    assert sprache.fuer(SimpleNamespace(sprache="xx")) == "en"


def test_uebersetzt_start_inhalt():
    with translation.override("en"):
        assert sprache.uebersetzt("Küche") == "Kitchen"
    with translation.override("de"):
        assert sprache.uebersetzt("Küche") == "Küche"


@pytest.mark.parametrize("text", ["Eigene Kategorie der Eltern", "", None])
def test_uebersetzt_unbekannten_text_unveraendert(text):
    with translation.override("en"):
        assert sprache.uebersetzt(text) == text


def test_uebersetzt_erzeugte_namen_ueber_muster():
    with translation.override("en"):
        assert sprache.uebersetzt("Küche · Set 2") == "Kitchen · Set 2"
        assert sprache.uebersetzt("Eigener Name · Set 2") == "Eigener Name · Set 2"
