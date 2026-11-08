"""Kacheln einer Zielgruppe für eine Anfrage zusammenstellen (Registry -> Template-Daten).

Eine defekte Kachel darf das Dashboard nicht kippen: Fehler beim Berechnen werden protokolliert
und die Kachel ausgelassen."""

import logging

from apps.kern.registry import kacheln

logger = logging.getLogger(__name__)

# Betriebs-Kacheln der Eltern: stehen in den Einstellungen (Zahnrad), nicht auf der Übersicht.
ELTERN_EINSTELLUNGEN = (
    "spielregeln.eltern_pausen",
    "oberflaeche.eltern_ereignisse",
    "oberflaeche.eltern_system",
)


def fuer(zielgruppe, request):
    """Liste ``{"kachel": Kachel, "k": kontext}`` der sichtbaren Kacheln, in Reihenfolge."""
    ergebnis = []
    for kachel in kacheln(zielgruppe):
        try:
            if kachel.sichtbar is not None and not kachel.sichtbar(request):
                continue
            kontext = kachel.kontext(request) if kachel.kontext is not None else {}
        except Exception:
            logger.exception("Kachel %s konnte nicht berechnet werden", kachel.schluessel)
            continue
        ergebnis.append({"kachel": kachel, "k": kontext})
    return ergebnis
