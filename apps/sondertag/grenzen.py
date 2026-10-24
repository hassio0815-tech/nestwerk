"""Sondertag-Grenzen (ARCHITECTURE 7.6, Entscheidung 1): reine Rechnung ohne DB.

- höchstens ``max_pro_jahr`` angenommene Sondertage je **App-Jahr** (ab Go-live, 29.02. -> 28.02.,
  ``kern.zeit.app_jahr``),
- mindestens ``abstand`` Tage zwischen zwei Sondertagen (Bezugsdatum = Annahmedatum; auch zu
  später datierten Einträgen, z. B. nach einer Korrektur),
- ``einloesbar_ab`` = frühestes Datum ab ``frueheste``, an dem beide Grenzen erfüllt sind.
- **Warteschlange:** mehrere offene Ansprüche werden der Reihe nach (FIFO) eingeplant; jeder
  spätere rechnet mit dem geplanten Datum der früheren (``plan``).

Tage vor Go-live gehören zu keinem App-Jahr (dort gilt nur der Abstand, z. B. für manuell
erfasste Sondertage vor dem Start).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from apps.kern import zeit

MAX_SCHRITTE = 10_000


@dataclass(frozen=True)
class Regeln:
    go_live: date
    max_pro_jahr: int
    abstand: int  # Tage


def _im_app_jahr(tag: date, daten: Iterable[date], regeln: Regeln) -> tuple[int, date | None]:
    """(Anzahl Sondertage im App-Jahr von ``tag``, Ende des App-Jahrs). Vor Go-live: (0, None)."""
    if tag < regeln.go_live:
        return 0, None
    jahr = zeit.app_jahr(tag, go_live=regeln.go_live)
    return sum(1 for d in daten if jahr.enthaelt(d)), jahr.ende


def erlaubt(tag: date, angenommen: Iterable[date], regeln: Regeln) -> bool:
    """Darf an ``tag`` ein (weiterer) Sondertag angenommen werden?"""
    daten = list(angenommen)
    if any(abs((tag - d).days) < regeln.abstand for d in daten):
        return False
    anzahl, _ = _im_app_jahr(tag, daten, regeln)
    return anzahl < regeln.max_pro_jahr


def einloesbar_ab(frueheste: date, angenommen: Iterable[date], regeln: Regeln) -> date:
    """Frühestes Datum ``>= frueheste``, an dem beide Grenzen erfüllt sind."""
    daten = sorted(angenommen)
    tag = frueheste
    for _ in range(MAX_SCHRITTE):
        verschoben = False
        for d in daten:
            if abs((tag - d).days) < regeln.abstand:
                tag = d + timedelta(days=regeln.abstand)
                verschoben = True
        anzahl, ende = _im_app_jahr(tag, daten, regeln)
        if ende is not None and anzahl >= regeln.max_pro_jahr:
            tag = ende
            verschoben = True
        if not verschoben:
            return tag
    raise RuntimeError("Sondertag-Grenzen: kein Datum gefunden")  # pragma: no cover


def plan(
    offene_ab: list[date], angenommen: Iterable[date], regeln: Regeln, heute: date
) -> list[date]:
    """Einlösbar-ab je offenem Anspruch (in Reihenfolge der Warteschlange).

    ``offene_ab``: frühestes Datum je Anspruch (Verdienstdatum). Der erste Anspruch bekommt sein
    echtes ``einloesbar_ab`` (darf in der Vergangenheit liegen = schon einlösbar). Für die
    folgenden wird angenommen, dass die früheren frühestens heute angenommen werden."""
    daten = list(angenommen)
    ergebnis = []
    for frueheste in offene_ab:
        start = frueheste if not ergebnis else max(frueheste, ergebnis[-1])
        ab = einloesbar_ab(start, daten, regeln)
        ergebnis.append(ab)
        daten.append(max(ab, heute))
    return ergebnis
