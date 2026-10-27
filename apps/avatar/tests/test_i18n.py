"""Mehrsprachigkeit (Deutsch Quellsprache, Englisch aus .po) und Vollständigkeit der JSON-Texte."""

import ast

import pytest
from django.urls import reverse
from django.utils import translation

from apps.avatar import daten_texte, mods, selectors, services
from apps.avatar.management.commands.daten_texte_erzeugen import ZIEL, quelltext, sammeln

pytestmark = pytest.mark.django_db


def test_alle_sichtbaren_json_texte_stehen_in_daten_texte():
    """Neue Namen/Beschreibungen in den JSON-Daten: ``manage.py daten_texte_erzeugen`` ausführen."""
    baum = ast.parse(ZIEL.read_text(encoding="utf-8"))
    in_datei = {
        n.args[0].value
        for n in ast.walk(baum)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "gettext_noop"
    }
    fehlend = [t for t in sammeln() if t not in in_datei]
    assert not fehlend, f"Fehlt in daten_texte.py (daten_texte_erzeugen ausführen): {fehlend[:5]}"
    assert set(daten_texte.TEXTE) == set(sammeln())
    assert ZIEL.read_text(encoding="utf-8") == quelltext()


def test_json_namen_sind_englisch_uebersetzt():
    with translation.override("en"):
        namen = {n for _, n, _ in selectors.figur_optionen()["haut"]}
        assert {"Light", "Honey"} <= namen
        assert translation.gettext("Ritter") == "Knight"
    with translation.override("de"):
        assert translation.gettext("Ritter") == "Ritter"


def test_dauer_und_rest_text_englisch():
    with translation.override("en"):
        assert mods.dauer_text(72) == "3 days"
        assert mods.dauer_text(24) == "1 day"
        assert mods.dauer_text(0) == "right away"
        assert mods.inszenierung(None) == ("Workshop", "is being built")


def test_wahlseite_auf_englisch(kind_client):
    kind_client.cookies["nestwerk_sprache"] = "en"
    html = kind_client.get(reverse("avatar:kind_wahl")).content.decode()
    assert "Build your avatar" in html
    assert "Skin tone" in html
    assert "Knight" in html
    assert "Bau deinen Avatar" not in html


def test_fehlermeldung_auf_englisch(anna):
    with translation.override("en"):
        with pytest.raises(mods.ModFehler, match="There is no such mod"):
            services.mod_anlegen(anna, "gibt_es_nicht")
