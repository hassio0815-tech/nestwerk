"""Schreibt ``apps/avatar/daten_texte.py``: alle sichtbaren Texte der JSON-Daten als
``gettext_noop``, damit ``makemessages`` sie findet (es liest kein JSON).

Sichtbar sind die Felder ``name`` und ``beschreibung`` in ``apps/avatar/daten/**/*.json``.
Nach Änderungen an den JSON-Dateien: ``python manage.py daten_texte_erzeugen``, dann
``makemessages`` (siehe docs/i18n.md). Ein Test (``test_daten_texte``) schlägt an, wenn das fehlt.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

APP = Path(__file__).resolve().parents[2]
DATEN = APP / "daten"
ZIEL = APP / "daten_texte.py"
SICHTBAR = ("name", "beschreibung")

KOPF = '''"""Sichtbare Texte der JSON-Daten für ``makemessages`` (erzeugt, nicht von Hand ändern).

Erzeugen: ``python manage.py daten_texte_erzeugen``. Angezeigt werden die Texte mit
``gettext(...)`` (Filter ``uebersetzt`` in Templates). Die Namen in der Datenbank bleiben deutsch.
"""
# ruff: noqa: E501

from django.utils.translation import gettext_noop

TEXTE = (
'''


def sammeln():
    """Alle sichtbaren Strings der JSON-Daten, ohne Doppelte, in stabiler Reihenfolge."""
    texte = {}

    def lauf(wert):
        if isinstance(wert, dict):
            for schluessel, inhalt in wert.items():
                if schluessel in SICHTBAR and isinstance(inhalt, str) and inhalt:
                    texte.setdefault(inhalt)
                else:
                    lauf(inhalt)
        elif isinstance(wert, list):
            for inhalt in wert:
                lauf(inhalt)

    for pfad in sorted(DATEN.rglob("*.json")):
        lauf(json.loads(pfad.read_text(encoding="utf-8")))
    return list(texte)


def quelltext():
    zeilen = [f"    gettext_noop({json.dumps(t, ensure_ascii=False)})," for t in sammeln()]
    return KOPF + "\n".join(zeilen) + "\n)\n"


class Command(BaseCommand):
    help = "Schreibt apps/avatar/daten_texte.py aus den JSON-Daten."

    def handle(self, *args, **opts):
        ZIEL.write_text(quelltext(), encoding="utf-8")
        self.stdout.write(f"{ZIEL.name}: {len(sammeln())} Texte")
