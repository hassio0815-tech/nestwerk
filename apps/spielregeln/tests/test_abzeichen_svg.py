"""AP28/Review AP31: Jede Abzeichen-Grafik unter static/abzeichen/ besteht den gemeinsamen
SVG-Sanitizer (``kern.svg``) mit der Abzeichen-Fläche ``viewBox 0 0 64 64`` – ohne Ersetzen der
viewBox (früher nötig, weil die Whitelist in apps/avatar 32 x 48 fest verdrahtet hatte)."""

from pathlib import Path

import pytest
from django.conf import settings

from apps.spielregeln import abzeichen

ORDNER = Path(settings.BASE_DIR) / "static" / "abzeichen"
DATEIEN = sorted(ORDNER.glob("*.svg"))


def test_ordner_enthaelt_grafiken():
    assert len(DATEIEN) >= 17  # 12 Startwert-Symbole + Rang-Varianten 2..6


@pytest.mark.parametrize("datei", DATEIEN, ids=lambda p: p.stem)
def test_grafik_besteht_whitelist(datei):
    assert abzeichen.grafik_pruefen(datei.read_text(encoding="utf-8")) is None


def test_falsche_flaeche_oder_script_wird_abgewiesen():
    text = DATEIEN[0].read_text(encoding="utf-8")
    assert abzeichen.grafik_pruefen(text.replace("0 0 64 64", "0 0 32 48", 1))
    assert abzeichen.grafik_pruefen(text.replace("</svg>", "<script>x()</script></svg>"))
