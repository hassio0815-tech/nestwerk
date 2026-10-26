"""Serienbonus (AP21, ARCHITECTURE 7.3, Entscheidung 4, SPEC 18.2). Reine Rechnung, liest nur.

- Bonus-Serie (O5, laufende Serie) = Wochenserie nach der Vorwoche (pausenbereinigt) + 1, weil
  die Aufgabe ihre Woche aktiv macht. Maßgeblich ist die Woche, für die die Aufgabe als
  Aktivität zählt: die Woche des Meldedatums (K1; Meldung So, Bestätigung Mo im Puffer = alte
  Woche). Erst nach Wochenabschluss bestätigt zählt die Woche der Bestätigung (wie Aktivität).
- Prozent = ``min(deckel, (serie - start + 1) * schritt)`` ab ``serie >= start``, sonst 0.
- Bonus = ``ceil(basis * prozent / 100)`` (ganzzahlig, zugunsten des Kindes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from apps.kern import einstellungen
from apps.kern.zeit import IsoWoche

from . import auswertung
from . import kontinuitaet as k


@dataclass(frozen=True)
class Regeln:
    start: int
    schritt: int
    deckel: int


def regeln() -> Regeln:
    w = einstellungen.werte(
        "spielregeln.serienbonus_start",
        "spielregeln.serienbonus_schritt_prozent",
        "spielregeln.serienbonus_deckel_prozent",
    )
    return Regeln(
        start=w["spielregeln.serienbonus_start"],
        schritt=w["spielregeln.serienbonus_schritt_prozent"],
        deckel=w["spielregeln.serienbonus_deckel_prozent"],
    )


def prozent(serie: int, r: Regeln | None = None) -> int:
    r = r or regeln()
    if serie < r.start:
        return 0
    return min(r.deckel, (serie - r.start + 1) * r.schritt)


def bonus_punkte(basis: int, satz: int) -> int:
    """``ceil(basis * satz / 100)`` ohne Gleitkomma."""
    if basis <= 0 or satz <= 0:
        return 0
    return -(-basis * satz // 100)


def wirksame_woche(meldedatum: date, erfasst_am: datetime) -> IsoWoche:
    r = auswertung.regeln()
    return IsoWoche.von(k.wirksames_datum(meldedatum, erfasst_am, r.puffer_stunden, r.tz))


def serie_fuer(kind, woche: IsoWoche) -> int:
    """Laufende Serie, wenn ``woche`` (durch die Aufgabe) aktiv ist."""
    from .selectors import wochenserie_nach

    return wochenserie_nach(kind, woche.vorherige()) + 1
