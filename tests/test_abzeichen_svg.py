"""AP28: Jede Abzeichen-Grafik unter static/abzeichen/ besteht die SVG-Whitelist aus apps/avatar.

Liegt bewusst unter tests/ (nicht in apps/spielregeln): spielregeln darf nach dem Schichtenvertrag
nicht aus apps/avatar importieren, und tests/ ist von lint-imports nicht erfasst.
"""

from pathlib import Path

import pytest
from django.conf import settings

from apps.avatar.generator import svgsicher

ORDNER = Path(settings.BASE_DIR) / "static" / "abzeichen"
DATEIEN = sorted(ORDNER.glob("*.svg"))
VIEWBOX_ABZEICHEN = 'viewBox="0 0 64 64"'
# apps/avatar fixiert die Wurzel-viewBox auf 0 0 32 48 (FLAECHE). Für die Prüfung wird nur diese
# Angabe angeglichen; Elemente, Attribute und Werte werden unverändert gegen die Whitelist geprüft.
VIEWBOX_WHITELIST = 'viewBox="0 0 32 48"'


def test_ordner_enthaelt_grafiken():
    assert len(DATEIEN) >= 17  # 12 Startwert-Symbole + Rang-Varianten 2..6


@pytest.mark.parametrize("datei", DATEIEN, ids=lambda p: p.stem)
def test_grafik_besteht_whitelist(datei):
    text = datei.read_text(encoding="utf-8")
    assert VIEWBOX_ABZEICHEN in text, "Wurzel-viewBox muss 0 0 64 64 sein"
    geprueft = text.replace(VIEWBOX_ABZEICHEN, VIEWBOX_WHITELIST, 1)
    fehler = svgsicher.svg_pruefen(geprueft)
    assert fehler is None, fehler
