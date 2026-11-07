"""Schwierigkeit anpassen (SPEC 21.2 und 21.8): Ziel 70 bis 85 % richtig. Rein rechnend.

Start je Leistungsstufe (Grund- oder Erweiterungsniveau) und Intensität; danach folgt die
Schwierigkeit den letzten Antworten: zu viele richtig -> eine Stufe schwerer, zu wenige -> leichter.
Die Intensität begrenzt den Bereich (Aufwärmen nie über "Normal", Herausforderung nie darunter).
"""

GRUND, ERWEITERT = "grund", "erweitert"
AUFWAERMEN, NORMAL, HERAUSFORDERUNG = "aufwaermen", "normal", "herausforderung"

HOECHSTE = {GRUND: 4, ERWEITERT: 5}
_NORMAL = {GRUND: 2, ERWEITERT: 3}


def start_stufe(niveau, intensitaet):
    """Die Schwierigkeit, mit der es ohne Vorgeschichte losgeht."""
    normal = _NORMAL[niveau]
    versatz = {AUFWAERMEN: -1, HERAUSFORDERUNG: 1}.get(intensitaet, 0)
    return max(1, min(HOECHSTE[niveau], normal + versatz))


def bereich(niveau, intensitaet):
    """Erlaubter Bereich (von, bis) der Schwierigkeit."""
    normal, hoechste = _NORMAL[niveau], HOECHSTE[niveau]
    if intensitaet == AUFWAERMEN:
        return 1, normal
    if intensitaet == HERAUSFORDERUNG:
        return normal, hoechste
    return max(1, normal - 1), min(hoechste, normal + 1)


def quote(verlauf):
    """Anteil richtig (0 bis 1) oder ``None``; ``verlauf``: Paare (Schwierigkeit, richtig)."""
    return sum(1 for _s, r in verlauf if r) / len(verlauf) if verlauf else None


def schwierigkeit(
    niveau,
    intensitaet,
    verlauf,
    *,
    ziel_von=70,
    ziel_bis=85,
    fenster=8,
    mindestens=4,
    frust=False,
    versatz=0,
):
    """Die Schwierigkeit der nächsten Aufgabe.

    ``verlauf``: bisherige Antworten zu dieser Rechenart, älteste zuerst, als Paare
    ``(Schwierigkeit, richtig)``. Betrachtet werden die letzten Antworten auf der zuletzt
    erreichten Stufe (höchstens ``fenster``); erst ab ``mindestens`` Antworten ändert sich etwas.
    ``frust``: nach einer Frust-Erkennung eine Stufe leichter. ``versatz``: Wirkung der
    Selbsteinschätzung "zu leicht/zu schwer" (+1 oder -1), bleibt im erlaubten Bereich.
    """
    niedrig, hoch = bereich(niveau, intensitaet)
    if not verlauf:
        d = start_stufe(niveau, intensitaet)
    else:
        d = verlauf[-1][0]
        lauf = []
        for s, r in reversed(verlauf):
            if s != d or len(lauf) >= fenster:
                break
            lauf.append((s, r))
        anteil = quote(lauf)
        if len(lauf) >= mindestens:
            if anteil * 100 > ziel_bis:
                d += 1
            elif anteil * 100 < ziel_von:
                d -= 1
    d += versatz
    if frust:
        d -= 1
    return max(niedrig, min(hoch, max(1, d)))
