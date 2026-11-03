"""Frust-Erkennung (SPEC 21.2): mehrere "noch nicht" in Folge oder sehr schnelles Durchklicken.

Rein rechnend. Beurteilt werden nur abgeschlossene Antworten (richtig oder noch nicht); ein
"fast richtig" mit zweitem Versuch zählt nicht. Die Schwellen sind Einstellungen
(``lernen.frust_*``).
"""

from apps.kern.einstellungen import wert

from .models import Ergebnis

FEHLER_FOLGE = "fehler_folge"
SCHNELL = "schnell"


def erkennen(antworten):
    """``antworten``: Liste von ``(ergebnis, dauer_ms)``, älteste zuerst. Gibt den Grund
    (``FEHLER_FOLGE``, ``SCHNELL``) oder ``None`` zurück."""
    fertig = [(e, ms) for e, ms in antworten if e != Ergebnis.FAST]
    folge = wert("lernen.frust_fehler_folge")
    letzte = fertig[-folge:]
    if len(letzte) == folge and all(e == Ergebnis.NOCH_NICHT for e, _ms in letzte):
        return FEHLER_FOLGE
    anzahl = wert("lernen.frust_schnell_anzahl")
    schnell_ms = wert("lernen.frust_schnell_ms")
    letzte = fertig[-anzahl:]
    if len(letzte) == anzahl and all(ms < schnell_ms for _e, ms in letzte):
        # Schnelles Tippen richtiger Antworten ist Können; Durchklicken erkennt man an Fehlern
        falsch = sum(1 for e, _ms in letzte if e == Ergebnis.NOCH_NICHT)
        if falsch * 2 >= anzahl:
            return SCHNELL
    return None
