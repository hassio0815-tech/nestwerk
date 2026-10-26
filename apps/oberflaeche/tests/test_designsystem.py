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

STATIC_CSS = ["css/tokens.css", "css/nestwerk.css", "css/huelle.css", "css/spiel.css", "css/styleguide.css"]
LIZENZEN = [
    "fonts/inter/OFL-Inter.txt",
    "fonts/fraunces/OFL-Fraunces.txt",
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
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", _css("nestwerk.css"))


@pytest.mark.parametrize("datei", ["aufgaben.css", "oberflaeche.css"])
def test_zeile_ist_eine_reihe(datei):
    """Regression: ``.karte__inhalt.zeile`` erbte flex-direction:column (riesige Karten)."""
    block = re.search(r"\.zeile\s*\{([^}]*)\}", _css(datei)).group(1)
    assert "flex-direction: row" in block


# --- Phase-1-Politur (Screenshot-Nachbesserung) ---------------------------------------------


def _roh(pfad):
    return (Path(__file__).resolve().parents[3] / pfad).read_text(encoding="utf-8")


def test_wochenplan_handy_tage_untereinander():
    css = _css("aufgaben.css")
    handy = re.search(r"@media \(max-width: 700px\) \{(.*?)\n\}", css, re.S).group(1)
    assert re.search(r"\.wochenplan__raster\s*\{[^}]*grid-template-columns:\s*1fr", handy)
    assert "repeat(7, 14rem)" not in css
    assert "wochenplan__tag--leer" in handy


def test_wochenplan_leerer_tag_hat_kompakte_klasse():
    html = _roh("apps/aufgaben/templates/aufgaben/_wochenplan.html")
    assert "wochenplan__tag--leer" in html


def test_tablet_basis_zeigt_keinen_fake_familienzielwert():
    html = render_to_string("basis/tablet.html", {})
    assert "Familienziel" not in html
    assert "0 / 100" not in html


def test_aufgabenformular_blendet_serienfelder_per_css_aus():
    css = _css("aufgaben.css")
    assert re.search(r"\.plan \.plan__serie\s*\{\s*display:\s*none", css.replace(",\n", ", "))
    assert "plan__serie" in _roh("apps/aufgaben/templates/aufgaben/_formular.html")
    assert "@supports not selector(:has(*))" in css


def test_einstellungen_gruppen_sind_aufklappbar():
    html = _roh("apps/oberflaeche/templates/oberflaeche/einstellungen.html")
    assert '<details class="einstellungen-gruppe' in html


def test_touchziele_und_schriftgroessen_im_css():
    css = _css("nestwerk.css")
    assert re.search(r"details > summary\s*\{[^}]*min-height:\s*var\(--tap-min\)", css)
    assert re.search(r"label\.reihe\s*\{[^}]*min-height:\s*var\(--tap-min\)", css)
    assert re.search(r"\.chip\s*\{[^}]*font-size:\s*0\.875rem", css)
    zeile_css = _css("oberflaeche.css")
    assert re.search(r"\.zeile > a\s*\{[^}]*min-height:\s*var\(--tap-min\)", zeile_css)
    for datei in ("nestwerk.css", "aufgaben.css"):
        for wert in re.findall(r"font-size:\s*([0-9.]+)(rem|em)", _css(datei)):
            if wert[1] == "em":
                raise AssertionError("relative em-Schrift unterschreitet je nach Basis 14 px")


def test_keine_schrift_unter_14px_im_css():
    """Review AP31: Ranking-Kacheln hatten 0,85rem (13,6 px) auf Kinder- und Tablet-Seiten.
    Mindestgröße 0,875rem = 14 px (Styleguide-Seite ausgenommen, nur Entwicklung)."""
    import re
    from pathlib import Path

    from django.conf import settings

    muster = re.compile(r"font-size:\s*(\d*\.?\d+)(rem|px)")
    zu_klein = []
    for datei in sorted((Path(settings.BASE_DIR) / "static/css").glob("*.css")):
        if datei.name == "styleguide.css":
            continue
        for wert, einheit in muster.findall(datei.read_text(encoding="utf-8")):
            px = float(wert) * (16 if einheit == "rem" else 1)
            if px < 14:
                zu_klein.append(f"{datei.name}: {wert}{einheit}")
    assert zu_klein == []
