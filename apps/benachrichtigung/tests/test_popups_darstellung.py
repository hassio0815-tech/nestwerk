"""AP33: einheitliche Pop-ups. Jede Art rendert die gemeinsame Hülle mit
Warteschlangen-Attributen, Effekte und Abzeichen-Grafik kommen aus den Ereignisdaten,
Animationen bleiben bei transform/opacity."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string

WURZEL = Path(__file__).resolve().parents[3]
CSS = (WURZEL / "static/css/nestwerk.css").read_text(encoding="utf-8")
JS = (WURZEL / "static/js/nestwerk.js").read_text(encoding="utf-8")

# art -> (Modifier-Klasse, Dauer in ms, Effekt-Klasse)
ARTEN = {
    "rang.aufgestiegen": ("rang", "8000", "glanz"),
    "abzeichen.verliehen": ("abzeichen", "7000", "feder"),
    "mod.fertig": ("werkstatt", "6000", "funken"),
    "serienbonus.gebucht": ("serienbonus", "5000", "zaehlen"),
    "familienziel.erreicht_kind": ("familienziel", "8000", "konfetti"),
    "familienziel.grossziel_kind": ("familienziel", "8000", "konfetti"),
    "ruhmeshalle.held": ("ruhm", "8000", "glanz"),
    "unbekannt.typ": ("erfolg", "5000", ""),
}


def _popup(art, titel="Titel", text="Text", symbol=None):
    ereignis = SimpleNamespace(daten={"symbol": symbol} if symbol else {})
    benachrichtigung = SimpleNamespace(ereignis=ereignis)
    return SimpleNamespace(art=art, titel=titel, text=text, benachrichtigung=benachrichtigung)


def _rendern(*popups):
    return render_to_string("benachrichtigung/_popups.html", {"popups": list(popups)})


@pytest.mark.parametrize("art", list(ARTEN))
def test_jede_art_nutzt_gemeinsame_huelle(art):
    klasse, dauer, effekt = ARTEN[art]
    html = _rendern(_popup(art, titel="Hallo Welt"))
    assert f"toast toast--{klasse} popup popup--{klasse}" in html
    assert f'data-schliessbar data-popup data-popup-art="{klasse}" data-dauer="{dauer}"' in html
    assert "Hallo Welt" in html and "data-schliessen" in html
    if effekt:
        assert f"popup--{effekt}" in html
    assert "<script" not in html and "style=" not in html


def test_abzeichen_springt_mit_grafik_aus_ereignisdaten():
    html = _rendern(_popup("abzeichen.verliehen", symbol="legende"))
    assert "abzeichen/legende.svg" in html
    assert "data-bild-ersatz" in html and "popup__ersatz" in html


def test_abzeichen_ohne_symbol_nimmt_stern():
    html = _rendern(_popup("abzeichen.verliehen"))
    assert "<img" not in html and "#i-stern" in html


def test_werkstatt_zeigt_hammer():
    html = _rendern(_popup("mod.fertig"))
    assert "#i-hammer" in html and html.count("<i></i>") == 8


def test_serienbonus_zaehlt_titelzahl_hoch():
    html = _rendern(_popup("serienbonus.gebucht", titel="Serienbonus +12 %"))
    assert re.search(r'<strong class="popup__titel" data-zaehl>Serienbonus \+12 %</strong>', html)


def test_sondertag_festhalten_ohne_auto_ausblenden():
    html = _rendern(
        SimpleNamespace(
            art="sondertag.angenommen",
            titel="Wunsch angenommen",
            text="",
            pk=1,
            benachrichtigung=None,
        )
    )
    assert "data-festhalten" in html and "data-dauer" not in html
    assert "st-popup" in html


def test_warteschlange_reihenfolge_bleibt_erhalten():
    html = _rendern(
        _popup("rang.aufgestiegen", titel="Erster"), _popup("mod.fertig", titel="Zweiter")
    )
    assert html.index("Erster") < html.index("Zweiter")


def test_reduced_motion_nur_einblenden():
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "animation: popup-einblenden 0.2s ease-out both !important" in CSS
    assert "@keyframes popup-einblenden { from { opacity: 0; } to { opacity: 1; } }" in CSS


def _keyframes_koerper(name):
    start = CSS.index(f"@keyframes {name} {{") + len(f"@keyframes {name} ")
    tiefe, i = 0, start
    while True:
        zeichen = CSS[i]
        if zeichen == "{":
            tiefe += 1
        elif zeichen == "}":
            tiefe -= 1
            if tiefe == 0:
                return CSS[start : i + 1]
        i += 1


@pytest.mark.parametrize(
    "name",
    [
        "popup-einblenden",
        "popup-ein",
        "popup-aus",
        "popup-feier",
        "popup-glanz",
        "popup-feder",
        "popup-hammer",
        "popup-funke",
    ],
)
def test_popup_keyframes_animieren_nur_transform_und_opacity(name):
    eigenschaften = set(re.findall(r"([a-z-]+)\s*:", _keyframes_koerper(name)))
    assert eigenschaften <= {"opacity", "transform"}, eigenschaften


def test_popup_css_ohne_layout_animation_und_ohne_inline_pfad():
    assert "transition: all" not in CSS
    assert "@keyframes popup-" in CSS and "[data-popup-wartet]" in CSS


def test_nestwerk_js_queue_und_bewegungsfilter():
    assert "prefers-reduced-motion: reduce" in JS
    assert "data-popup-aktiv" in JS and "data-popup-wartet" in JS
    assert "Escape" in JS and "MutationObserver" in JS
    assert "eval(" not in JS and "new Function" not in JS
