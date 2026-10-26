"""AP28: Abzeichen-Grafiken. Jedes Symbol der Startwerte und jedes aktive Abzeichen in der DB hat
eine Datei unter static/abzeichen/. Die SVG-Whitelist prüft test_abzeichen_svg.py (kern.svg)."""

from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, override_settings

from apps.spielregeln.abzeichen_start import startwerte
from apps.spielregeln.models import AbzeichenDefinition
from apps.spielregeln.raenge_start import RAENGE

ORDNER = Path(settings.BASE_DIR) / "static" / "abzeichen"
RANG_STUFEN = [stufe for stufe, *_ in RAENGE if stufe >= 2]


def _namen(symbol, gruppe):
    """Dateinamen (ohne .svg): Grundgrafik, bei Rang je Stufe 2..6 eine Variante."""
    namen = [symbol]
    if gruppe == "rang":
        namen += [f"{symbol}-rang-{n}" for n in RANG_STUFEN]
    return namen


def test_startwerte_symbole_haben_grafik():
    fehlend = [
        n
        for zeile in startwerte()
        for n in _namen(zeile["symbol"], zeile["gruppe"])
        if not finders.find(f"abzeichen/{n}.svg")
    ]
    assert fehlend == []


@pytest.mark.django_db
def test_jedes_aktive_abzeichen_in_der_db_hat_grafik():
    definitionen = list(AbzeichenDefinition.objects.filter(aktiv=True))
    assert definitionen, "Startwerte-Migration hat keine Abzeichen angelegt"
    fehlend = [
        n
        for d in definitionen
        for n in _namen(d.symbol, d.gruppe)
        if not finders.find(f"abzeichen/{n}.svg")
    ]
    assert fehlend == []


def test_rang_grafiken_je_stufe_zwei_bis_sechs():
    assert RANG_STUFEN == [2, 3, 4, 5, 6]
    for n in RANG_STUFEN:
        assert finders.find(f"abzeichen/rangaufstieg-rang-{n}.svg"), n


@pytest.mark.django_db
def test_galerie_nur_im_debug_und_zeigt_grafiken():
    with override_settings(DEBUG=False):
        assert Client().get("/abzeichen/galerie/").status_code == 404
    with override_settings(DEBUG=True):
        antwort = Client().get("/abzeichen/galerie/")
    assert antwort.status_code == 200
    html = antwort.content.decode()
    assert 'data-galerie="tagesserie-7"' in html
    assert 'data-galerie="rangaufstieg"' in html
    assert "abzeichen/rangaufstieg-rang-6.svg" in html
