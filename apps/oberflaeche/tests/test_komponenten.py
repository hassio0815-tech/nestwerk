"""Komponenten-Includes: Pflichtelemente der Designvorgaben."""

from django.template.loader import render_to_string


def test_button_zeigt_symbol_und_text():
    html = render_to_string("komponenten/button.html", {"text": "Erledigt", "icon": "check"})

    assert 'href="#i-check"' in html
    assert "<span>Erledigt</span>" in html
    assert "<button" in html


def test_button_als_link_mit_gross_variante():
    html = render_to_string(
        "komponenten/button.html",
        {"text": "Mod kaufen", "href": "/mods/", "gross": True, "variante": "primaer"},
    )

    assert html.strip().startswith('<a class="knopf knopf--primaer knopf--gross" href="/mods/">')


def test_pin_pad_hat_vier_stellen_und_zehn_ziffern():
    html = render_to_string("komponenten/pin_pad.html")

    assert html.count("data-pin-punkt") == 4
    assert html.count("data-pin-taste=") == 10
    assert 'name="pin"' in html
    assert "data-pin-ok disabled" in html


def test_chip_ohne_stufe_ist_common():
    html = render_to_string("komponenten/chip.html")

    assert 'data-selten="common"' in html
    assert ">Common<" in html


def test_chip_god_mode_mit_regenbogen_attribut():
    html = render_to_string("komponenten/chip.html", {"stufe": "god"})

    assert 'data-selten="god"' in html
    assert ">God Mode<" in html


def test_fortschritt_nutzt_native_progress_ohne_inline_style():
    html = render_to_string("komponenten/fortschritt.html", {"label": "Ziel", "wert": 3, "max": 6})

    assert 'value="3"' in html
    assert 'max="6"' in html
    assert "style=" not in html


def test_feld_mit_fehler_verknuepft_hinweis():
    html = render_to_string(
        "komponenten/feld.html",
        {"name": "pin", "id": "pin-feld", "label": "PIN", "fehler": "Falsch."},
    )

    assert 'aria-describedby="pin-feld-hinweis"' in html
    assert 'aria-invalid="true"' in html
    assert "feld--fehler" in html


def test_leerer_zustand_mit_aktion():
    html = render_to_string(
        "komponenten/leer.html",
        {"titel": "Nichts da", "aktion_text": "Neu", "aktion_href": "/neu/"},
    )

    assert "Nichts da" in html
    assert 'href="/neu/"' in html
