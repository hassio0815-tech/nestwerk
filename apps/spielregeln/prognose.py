"""Rang-Prognose (AP32, ARCHITECTURE 7.9, P-07).

Reine Rechnung (``rang_ziele``) plus ein dünner Leser für die Basis (``basis``). Die Prognose ist
reproduzierbar: gleiche Eingabe (Basis, Stand, Schwellen, Faktoren, Stichtag) ergibt dasselbe
Ergebnis; es wird nichts gespeichert.

- Basis: mittlere XP je Woche und Anteil aktiver Wochen der letzten N abgeschlossenen, nicht
  neutralen Wochen (``spielregeln.prognose_wochen``). Zu wenig Historie
  (``spielregeln.prognose_min_wochen``): keine Zahl, nur ein Hinweis.
- Rang: ``max(Wochen bis XP-Schwelle, Wochen bis Mindest-Aktivwochen)``; der größere Wert ist der
  **Engpass** (``xp``, ``wochen`` oder ``beides``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche

from . import raenge
from .models import Wochenauswertung

XP = "xp"
WOCHEN = "wochen"
BEIDES = "beides"
MAX_WOCHEN = 520  # darüber: "mehr als 10 Jahre" gilt als keine sinnvolle Prognose


@dataclass(frozen=True)
class Basis:
    """Beobachtung der letzten Wochen."""

    wochen: int  # tatsächlich verwendete (nicht neutrale) Wochen
    xp_schnitt: Fraction  # XP je Kalenderwoche
    aktivquote: Fraction  # Anteil aktiver Wochen 0–1
    genug: bool  # mindestens ``prognose_min_wochen`` Wochen

    @property
    def hinweis(self) -> str:
        if self.genug:
            return ""
        return (
            f"Zu wenig Verlauf für eine Prognose: {self.wochen} abgeschlossene "
            f"{'Woche' if self.wochen == 1 else 'Wochen'} (nötig sind mehr)."
        )


@dataclass(frozen=True)
class StufeBedarf:
    """Was ein Rang verlangt (bereits mit Faktoren skaliert)."""

    stufe: int
    name: str
    schwelle: int
    min_wochen: int


@dataclass(frozen=True)
class RangZiel:
    stufe: int
    name: str
    xp_fehlt: int
    wochen_fehlen: int  # aktive Wochen
    wochen_xp: int | None  # Kalenderwochen bis XP-Schwelle (None = nie bei diesem Tempo)
    wochen_aktiv: int | None  # Kalenderwochen bis Mindest-Aktivwochen
    wochen: int | None  # max der beiden; None = keine Prognose möglich
    datum: date | None
    engpass: str  # xp | wochen | beides | "" (schon erreicht)

    @property
    def erreicht(self) -> bool:
        return self.xp_fehlt == 0 and self.wochen_fehlen == 0


def aufrunden(menge: int, je_woche: Fraction) -> int | None:
    if menge <= 0:
        return 0
    if je_woche <= 0:
        return None
    return math.ceil(Fraction(menge) / je_woche)


def rang_ziele(
    basis: Basis,
    *,
    xp: int,
    aktive_wochen: int,
    stufen: list[StufeBedarf],
    stichtag: date,
) -> list[RangZiel]:
    """Prognose je noch nicht erreichter Stufe (aufsteigend). Leer bei zu wenig Historie."""
    if not basis.genug:
        return []
    ergebnis = []
    for s in stufen:
        xp_fehlt = max(0, s.schwelle - xp)
        wochen_fehlen = max(0, s.min_wochen - aktive_wochen)
        w_xp = aufrunden(xp_fehlt, basis.xp_schnitt)
        w_akt = aufrunden(wochen_fehlen, basis.aktivquote)
        if w_xp is None or w_akt is None:
            wochen, engpass = None, XP if w_xp is None else WOCHEN
        else:
            wochen = max(w_xp, w_akt)
            if wochen == 0:
                engpass = ""
            elif w_xp == w_akt:
                engpass = BEIDES
            else:
                engpass = XP if w_xp > w_akt else WOCHEN
        if wochen is not None and wochen > MAX_WOCHEN:
            wochen = None
        datum = stichtag + timedelta(weeks=wochen) if wochen is not None else None
        ergebnis.append(
            RangZiel(s.stufe, s.name, xp_fehlt, wochen_fehlen, w_xp, w_akt, wochen, datum, engpass)
        )
    return ergebnis


def xp_bindet(ziele: list[RangZiel]) -> bool:
    """Ist bei mindestens einer künftigen Stufe die XP-Schwelle der Engpass? (P-07: sonst
    bestimmen allein die Mindest-Aktivwochen das Tempo.)"""
    return any(z.engpass in (XP, BEIDES) for z in ziele)


# --- Lesen ------------------------------------------------------------------------------------


def _montag(tag: date) -> date:
    return IsoWoche.von(tag).montag


def basis(kind, stichtag: date | None = None, *, n: int | None = None) -> Basis:
    """Letzte ``n`` abgeschlossene, nicht neutrale Wochen vor der Woche des Stichtags."""
    stichtag = stichtag or zeit.heute()
    werte = einstellungen.werte("spielregeln.prognose_wochen", "spielregeln.prognose_min_wochen")
    n = n or werte["spielregeln.prognose_wochen"]
    zeilen = list(
        Wochenauswertung.objects.filter(kind=kind, neutral=False, montag__lt=_montag(stichtag))
        .order_by("-montag")
        .values_list("xp_woche", "aktiv")[:n]
    )
    if not zeilen:
        return Basis(0, Fraction(0), Fraction(0), False)
    anzahl = len(zeilen)
    return Basis(
        wochen=anzahl,
        xp_schnitt=Fraction(sum(x for x, _ in zeilen), anzahl),
        aktivquote=Fraction(sum(1 for _, a in zeilen if a), anzahl),
        genug=anzahl >= werte["spielregeln.prognose_min_wochen"],
    )


def stufen_offen(kind, faktor_schwelle: Decimal, faktor_wochen: Decimal) -> list[StufeBedarf]:
    """Alle noch nicht erreichten Stufen mit den Faktoren skaliert (global x Kind-Faktor wird vom
    Aufrufer eingerechnet)."""
    aktuell = raenge.aktueller_rang(kind)
    return [
        StufeBedarf(
            r.stufe,
            r.name,
            raenge.wirksame_schwelle(r, faktor_schwelle),
            raenge.wirksame_wochen(r, faktor_wochen),
        )
        for r in raenge.raenge()
        if aktuell is None or r.stufe > aktuell.stufe
    ]


def naechster_rang(kind, stichtag: date | None = None) -> RangZiel | None:
    """Prognose nur für den nächsten Rang (Kind-Kachel). ``None`` = Endstufe, zu wenig Verlauf
    oder kein Fortschritt absehbar."""
    stichtag = stichtag or zeit.heute()
    b = basis(kind, stichtag)
    if not b.genug:
        return None
    f = raenge.rang_fortschritt(kind)
    stufen = stufen_offen(kind, raenge.wirksamer_faktor(kind), raenge.wochen_faktor(kind))[:1]
    ziele = rang_ziele(b, xp=f.xp, aktive_wochen=f.aktive_wochen, stufen=stufen, stichtag=stichtag)
    return ziele[0] if ziele and ziele[0].wochen is not None else None
