"""Gemeinsamer SVG-Sanitizer (Review AP31): viewBox konfigurierbar, Verläufe optional."""

import pytest

from apps.kern.svg import SvgUnzulaessig, svg_bereinigen, svg_pruefen

NS = 'xmlns="http://www.w3.org/2000/svg"'


def doc(inhalt, viewbox="0 0 64 64"):
    return f'<svg {NS} viewBox="{viewbox}">{inhalt}</svg>'


VERLAUF = (
    '<defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0%" stop-color="#ffcc00"/><stop offset="100%" stop-color="#aa6600" '
    'stop-opacity="0.8"/></linearGradient></defs><rect x="1" y="1" width="9" height="9" '
    'fill="url(#g1)"/>'
)


def test_viewbox_ist_konfigurierbar():
    assert svg_pruefen(doc("<rect x='1'/>"), viewbox=(0, 0, 64, 64)) is None
    assert svg_pruefen(doc("<rect x='1'/>"), viewbox=(0, 0, 32, 48))
    assert svg_pruefen(doc("<rect x='1'/>", "0 0 32 48")) is None  # Standard = Avatar
    assert svg_pruefen(doc("<rect x='1'/>", "0 0 999 1"), viewbox=None) is None


def test_verlaeufe_nur_wenn_erlaubt():
    assert svg_pruefen(doc(VERLAUF), viewbox=(0, 0, 64, 64))  # Standard: aus
    sauber = svg_bereinigen(doc(VERLAUF), viewbox=(0, 0, 64, 64), verlaeufe=True)
    assert 'fill="url(#g1)"' in sauber and "<linearGradient" in sauber


@pytest.mark.parametrize(
    "inhalt",
    [
        '<rect fill="url(#fehlt)"/>',  # Verweis ohne Definition
        '<rect fill="url(http://evil.example/x.svg#a)"/>',  # externe Referenz
        '<rect fill="url(javascript:alert(1))"/>',
        '<linearGradient id="a" href="#b"/>',  # Verlauf-Verkettung per href
        '<linearGradient id="a" gradientTransform="matrix(1 0 0 1 0 0)"/>',
        '<linearGradient id="a"/><linearGradient id="a"/>',  # doppelte id
        '<stop offset="0" stop-color="red"/>',  # nur Hex-Farben
        '<linearGradient id="a" style="fill:url(x)"/>',
        "<pattern id='p'/>",
    ],
)
def test_boese_verlaeufe_werden_abgewiesen(inhalt):
    with pytest.raises(SvgUnzulaessig):
        svg_bereinigen(doc(inhalt), viewbox=(0, 0, 64, 64), verlaeufe=True)
