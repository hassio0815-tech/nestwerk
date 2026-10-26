"""Reine Regeln für Kontinuität (ohne DB, ARCHITECTURE 7.2, 13.2 K1/K5).

- **Aktive Woche:** mindestens ein aktiver Tag in der ISO-Woche.
- **Neutrale Woche:** nicht aktiv und mindestens ``neutral_ab`` Pausentage (Kind oder Familie).
- **Wochenserie:** aktiv -> +1, neutral -> unverändert, sonst -> 0.
- **Aktive Wochen gesamt:** Anzahl aktiver Wochen, nie zurückgesetzt.
- **Tagesserie:** gleiche Regel je Tag (Pausentag ohne Aktivität neutral); der laufende Tag
  bricht nie.
- **Puffer (K1):** Woche W ist ab ``Montag(W+1) 00:00 + puffer_stunden`` (lokal) abgeschlossen.
  Eine Bestätigung danach zählt für den Tag der Bestätigung statt für das Meldedatum.

Pausen sind Paare ``(von, bis)`` lokaler Daten, inklusiv, ``bis = None`` = offen.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from apps.kern import zeit
from apps.kern.zeit import IsoWoche

EIN_TAG = timedelta(days=1)

Pausen = Iterable[tuple[date, date | None]]


def finalisiert_ab(woche: IsoWoche, puffer_stunden: int, tz) -> datetime:
    """Zeitpunkt (UTC), ab dem ``woche`` abgeschlossen ist: Montag danach 00:00 lokal plus
    Puffer in lokaler Wanduhrzeit (Sommerzeit-Wechsel liegen immer auf einem Sonntag)."""
    lokal = datetime.combine(woche.montag + timedelta(days=7), time.min) + timedelta(
        hours=puffer_stunden
    )
    return zeit.lokal_zu_utc(lokal.date(), lokal.time(), tz)


def ist_finalisiert(woche: IsoWoche, jetzt: datetime, puffer_stunden: int, tz) -> bool:
    return jetzt >= finalisiert_ab(woche, puffer_stunden, tz)


def wirksames_datum(meldedatum: date, erfasst_am: datetime, puffer_stunden: int, tz) -> date:
    """K1: Meldedatum zählt, solange dessen Woche nicht abgeschlossen ist; sonst der Tag der
    Erfassung (Bestätigung)."""
    if ist_finalisiert(IsoWoche.von(meldedatum), erfasst_am, puffer_stunden, tz):
        return max(meldedatum, zeit.heute(erfasst_am, tz))
    return meldedatum


def pausiert(tag: date, pausen: Pausen) -> bool:
    return any(von <= tag and (bis is None or tag <= bis) for von, bis in pausen)


def pausentage(woche: IsoWoche, pausen: Pausen) -> int:
    pausen = list(pausen)
    return sum(1 for tag in woche.tage() if pausiert(tag, pausen))


@dataclass(frozen=True, slots=True)
class WochenErgebnis:
    woche: IsoWoche
    aktiv: bool
    neutral: bool
    pausentage: int
    wochenserie_danach: int
    aktive_wochen_gesamt: int


def wochen_auswerten(
    aktive_tage: set[date],
    pausen: Pausen,
    von_woche: IsoWoche,
    bis_woche: IsoWoche,
    neutral_ab: int,
) -> list[WochenErgebnis]:
    """Ergebnis je Woche von ``von_woche`` bis ``bis_woche`` (inklusiv), Serie startet bei 0."""
    pausen = list(pausen)
    ergebnis = []
    serie = gesamt = 0
    woche = von_woche
    while woche <= bis_woche:
        tage = woche.tage()
        aktiv = any(t in aktive_tage for t in tage)
        pt = sum(1 for t in tage if pausiert(t, pausen))
        neutral = not aktiv and pt >= neutral_ab
        if aktiv:
            serie += 1
            gesamt += 1
        elif not neutral:
            serie = 0
        ergebnis.append(WochenErgebnis(woche, aktiv, neutral, pt, serie, gesamt))
        woche = woche.naechste()
    return ergebnis


@dataclass(frozen=True, slots=True)
class TagesStand:
    tagesserie: int
    rekord: int


def tagesserie(aktive_tage: set[date], pausen: Pausen, heute: date) -> TagesStand:
    """Tagesserie am Tag ``heute`` und Rekord bis dahin (Aktivitäten nach ``heute`` zählen
    nicht). ``heute`` ohne Aktivität bricht nicht (laufender Tag)."""
    pausen = list(pausen)
    tage = [t for t in aktive_tage if t <= heute]
    if not tage:
        return TagesStand(0, 0)
    lauf = rekord = 0
    tag = min(tage)
    while tag <= heute:
        if tag in aktive_tage:
            lauf += 1
            rekord = max(rekord, lauf)
        elif tag != heute and lauf and not pausiert(tag, pausen):
            lauf = 0
        tag += EIN_TAG
    return TagesStand(lauf, rekord)


def quartal(woche: IsoWoche) -> tuple[int, int]:
    """(Jahr, Quartal) einer ISO-Woche: das Quartal ihres Donnerstags (ARCHITECTURE 7.5)."""
    donnerstag = woche.montag + timedelta(days=3)
    return donnerstag.year, (donnerstag.month - 1) // 3 + 1


def quartal_wochen(jahr: int, nummer: int) -> list[IsoWoche]:
    """ISO-Wochen, deren Donnerstag im Quartal liegt."""
    erster = date(jahr, 3 * (nummer - 1) + 1, 1)
    woche = IsoWoche.von(erster)
    if quartal(woche) != (jahr, nummer):
        woche = woche.naechste()
    wochen = []
    while quartal(woche) == (jahr, nummer):
        wochen.append(woche)
        woche = woche.naechste()
    return wochen
