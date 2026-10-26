"""Auswertung aus der Historie (liest nur): Aktivitäten + Pausen + Einstellungen -> Wochen und
Stand eines Kindes zu einem Zeitpunkt. Grundlage für Job, Selectors und Neuberechnung, damit alle
drei garantiert dieselbe Rechnung verwenden (ARCHITECTURE 7.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Q

from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche

from . import kontinuitaet as k
from .models import Aktivitaet, Pause


@dataclass(frozen=True)
class Regeln:
    puffer_stunden: int
    neutral_ab: int
    tz: object
    start: date | None  # Go-live; None = noch nicht eingerichtet (keine Wochen auswerten)


def regeln() -> Regeln:
    werte = einstellungen.werte("spielregeln.puffer_stunden", "spielregeln.neutral_ab_pausentagen")
    try:
        start = zeit.go_live_datum()
    except einstellungen.EinstellungFehlt:
        start = None
    return Regeln(
        puffer_stunden=werte["spielregeln.puffer_stunden"],
        neutral_ab=werte["spielregeln.neutral_ab_pausentagen"],
        tz=zeit.zeitzone(),
        start=start,
    )


def aktive_tage(kind) -> set[date]:
    return set(
        Aktivitaet.objects.filter(kind=kind, storniert=False)
        .values_list("datum", flat=True)
        .distinct()
    )


def pausen(kind) -> list[tuple[date, date | None]]:
    """Pausen des Kindes und der Familie als ``(von, bis)``."""
    return list(Pause.objects.filter(Q(kind=kind) | Q(kind__isnull=True)).values_list("von", "bis"))


@dataclass(frozen=True)
class Stand:
    """Stand eines Kindes zu ``jetzt``. Wochenwerte beziehen sich auf die letzte
    **finalisierte** Woche (die laufende Woche und Wochen im Puffer brechen nie)."""

    wochenserie: int
    aktive_wochen_gesamt: int
    rekord_wochenserie: int
    tagesserie: int
    rekord_tagesserie: int
    letzte_woche: IsoWoche | None
    woche_aktiv: bool  # laufende Woche hat schon eine Aktivität
    heute_pausiert: bool
    stand_datum: date


@dataclass(frozen=True)
class Auswertung:
    wochen: list[k.WochenErgebnis]  # alle vergangenen Wochen ab Go-live
    finalisiert: int  # die ersten n Einträge von ``wochen`` sind abgeschlossen
    stand: Stand


def vergangene_wochen(r: Regeln, heute: date) -> tuple[IsoWoche, IsoWoche] | None:
    """(erste, letzte) vergangene Woche ab Go-live oder ``None``."""
    if r.start is None:
        return None
    erste = IsoWoche.von(r.start)
    letzte = IsoWoche.von(heute).vorherige()
    return (erste, letzte) if erste <= letzte else None


def auswerten(kind, jetzt: datetime | None = None, r: Regeln | None = None) -> Auswertung:
    jetzt = jetzt or zeit.jetzt()
    r = r or regeln()
    heute = zeit.heute(jetzt, r.tz)
    tage = aktive_tage(kind)
    p = pausen(kind)
    bereich = vergangene_wochen(r, heute)
    wochen = k.wochen_auswerten(tage, p, *bereich, r.neutral_ab) if bereich else []
    finalisiert = sum(
        1 for w in wochen if k.ist_finalisiert(w.woche, jetzt, r.puffer_stunden, r.tz)
    )
    abgeschlossen = wochen[:finalisiert]
    letzte = abgeschlossen[-1] if abgeschlossen else None
    tagesstand = k.tagesserie(tage, p, heute)
    stand = Stand(
        wochenserie=letzte.wochenserie_danach if letzte else 0,
        aktive_wochen_gesamt=letzte.aktive_wochen_gesamt if letzte else 0,
        rekord_wochenserie=max((w.wochenserie_danach for w in abgeschlossen), default=0),
        tagesserie=tagesstand.tagesserie,
        rekord_tagesserie=tagesstand.rekord,
        letzte_woche=letzte.woche if letzte else None,
        woche_aktiv=any(t in tage for t in IsoWoche.von(heute).tage()),
        heute_pausiert=k.pausiert(heute, p),
        stand_datum=heute,
    )
    return Auswertung(wochen=wochen, finalisiert=finalisiert, stand=stand)


def xp_je_woche(kind, wochen: list[k.WochenErgebnis]) -> dict[IsoWoche, int]:
    """XP mit Bezugsdatum je Woche (K8: alles, was XP bewegt)."""
    from apps.punkte import selectors as punkte

    if not wochen:
        return {}
    je_tag = punkte.xp_je_tag(kind, wochen[0].woche.montag, wochen[-1].woche.sonntag)
    summe = dict.fromkeys((w.woche for w in wochen), 0)
    for tag, xp in je_tag.items():
        woche = IsoWoche.von(tag)
        if woche in summe:
            summe[woche] += xp
    return summe
