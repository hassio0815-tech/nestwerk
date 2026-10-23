"""Designsystem (AP06): Basis-Layouts und Styleguide laden nichts von fremden Hosts."""

import os
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import Client, override_settings

BASIS_LAYOUTS = [
    "basis/kind.html",
    "basis/eltern.html",
    "basis/tablet.html",
    "basis/einrichtung.html",
]

# Skript-, Stil- und Font-Einbindungen mit absoluter fremder URL.
EXTERNE_EINBINDUNG = re.compile(r"""\b(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
EXTERNE_CSS_QUELLE = re.compile(
    r"""(?:url\(\s*["']?|@import\s+["']?)\s*(?:https?:)?//""", re.IGNORECASE
)
INLINE_SKRIPT = re.compile(r"<script(?![^>]*\ssrc\s*=)[^>]*>", re.IGNORECASE)
STATISCHE_PFADE = re.compile(r"""\b(?:src|href)\s*=\s*["'](/static/[^"'?#]+)""")
CSS_URL = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""")

STATIC_CSS = ["css/tokens.css", "css/famko.css", "css/styleguide.css"]
LIZENZEN = [
    "fonts/inter/OFL-Inter.txt",
    "fonts/press-start-2p/OFL-PressStart2P.txt",
    "vendor/LICENSE-htmx.txt",
]


def externe_verweise(html):
    treffer = []
    for muster in (EXTERNE_EINBINDUNG, EXTERNE_CSS_QUELLE):
        treffer.extend(m.group(0) for m in muster.finditer(html))
    return treffer


def css_datei(relativ):
    return Path(finders.find(relativ))


@pytest.mark.parametrize("vorlage", BASIS_LAYOUTS)
def test_basis_layout_hat_keine_externen_quellen(vorlage):
    html = render_to_string(vorlage)

    assert externe_verweise(html) == []
    assert not INLINE_SKRIPT.search(html), "Inline-Skripte sind laut CSP verboten"


@pytest.mark.parametrize("vorlage", BASIS_LAYOUTS)
def test_basis_layout_verweist_nur_auf_vorhandene_statische_dateien(vorlage):
    html = render_to_string(vorlage)
    pfade = STATISCHE_PFADE.findall(html)

    assert pfade, "Layout muss Stil und Skripte einbinden"
    for pfad in pfade:
        assert finders.find(pfad.removeprefix("/static/")), pfad


def test_styleguide_ohne_debug_ist_nicht_erreichbar():
    with override_settings(DEBUG=False):
        antwort = Client().get("/styleguide/")

    assert antwort.status_code == 404


@override_settings(DEBUG=True)
def test_styleguide_rendert_in_kind_und_eltern_optik():
    antwort = Client().get("/styleguide/")
    html = antwort.content.decode()

    assert antwort.status_code == 200
    assert 'data-layout="kind"' in html
    assert 'data-layout="eltern"' in html
    assert 'data-modus="hell"' in html
    assert externe_verweise(html) == []
    assert not INLINE_SKRIPT.search(html)
    for pfad in STATISCHE_PFADE.findall(html):
        assert finders.find(pfad.removeprefix("/static/")), pfad


@pytest.mark.parametrize("datei", STATIC_CSS)
def test_css_hat_keine_externen_quellen_und_lokale_schriften_existieren(datei):
    text = css_datei(datei).read_text(encoding="utf-8")

    assert externe_verweise(text) == []
    for ziel in CSS_URL.findall(text):
        if ziel.startswith("data:"):
            continue
        pfad = os.path.normpath(os.path.join(os.path.dirname(datei), ziel))
        assert finders.find(pfad), f"{datei} verweist auf fehlende Datei {ziel}"


@pytest.mark.parametrize("lizenz", LIZENZEN)
def test_schriften_und_bibliotheken_haben_lizenzdatei(lizenz):
    assert finders.find(lizenz) is not None


def _css(name):
    return Path(finders.find(f"css/{name}")).read_text(encoding="utf-8")


def test_hidden_attribut_gewinnt_gegen_komponenten_display():
    """Regression (Screenshot-Prüfung): .stapel/.reihe (display:flex) überschrieben ``hidden``."""
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", _css("famko.css"))


@pytest.mark.parametrize("datei", ["aufgaben.css", "oberflaeche.css"])
def test_zeile_ist_eine_reihe(datei):
    """Regression: ``.karte__inhalt.zeile`` erbte flex-direction:column (riesige Karten)."""
    block = re.search(r"\.zeile\s*\{([^}]*)\}", _css(datei)).group(1)
    assert "flex-direction: row" in block
