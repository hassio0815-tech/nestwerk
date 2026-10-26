"""Held der Woche (AP30, ARCHITECTURE 7.8, Entscheidung 25).

Je abgeschlossener ISO-Woche (alle Auswertungen finalisiert) bekommt jedes nicht pausierte Kind
einen relativen Zuwachs::

    zuwachs = (xp_woche - schnitt) / max(schnitt, mindestbasis)

``schnitt`` = Mittel der letzten N aktiven Wochen *vor* dieser Woche. Hat das Kind weniger als
``held_min_wochen`` aktive Wochen, gilt die einfache Regel ``schnitt = mindestbasis`` (so
vergleichen in den ersten Wochen alle gleich). Held ist, wer ``xp_woche > 0`` und den größten
Zuwachs über 0 hat; bei Gleichstand (auf 3 Stellen) mehrere Helden. Pausierte Kinder (ab N
Pausentagen) sind ausgenommen.

Als Fakt gespeichert in ``Wochenauswertung.zuwachs_relativ`` / ``held_der_woche``. Eine Woche
gilt als bewertet, sobald ein Zuwachs gespeichert ist; spätere XP-Korrekturen ändern den Fakt
nicht mehr (idempotent, keine Nachzügler-Helden). Ereignisse nur für die jüngste Woche.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.ereignisse import services as ereignisse
from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.konten import selectors as konten

from . import auswertung, events
from .models import Wochenauswertung

logger = logging.getLogger("nestwerk.spielregeln")

GRENZE = Decimal("999.999")


def zuwachs(xp: int, historie: list[int], *, min_wochen: int, basis: int) -> Decimal:
    """Relativer Zuwachs einer Woche gegenüber der Historie (aktive Wochen, neueste zuerst)."""
    if len(historie) >= min_wochen:
        schnitt = sum(max(x, 0) for x in historie) / len(historie)
    else:
        schnitt = basis  # einfache Regel für die Anlaufzeit
    wert = Decimal(str((xp - schnitt) / max(schnitt, basis)))
    wert = wert.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return max(-GRENZE, min(GRENZE, wert))


def _historie(zeile: Wochenauswertung, anzahl: int) -> list[int]:
    return list(
        Wochenauswertung.objects.filter(kind_id=zeile.kind_id, montag__lt=zeile.montag, aktiv=True)
        .order_by("-montag")
        .values_list("xp_woche", flat=True)[:anzahl]
    )


def woche_bewerten(woche: IsoWoche, kinder, *, melden: bool, neutral_ab: int) -> list:
    """Bewertet eine Woche, falls reif und noch nicht bewertet. Gibt die Helden zurück."""
    zeilen = list(
        Wochenauswertung.objects.filter(
            iso_jahr=woche.jahr, iso_woche=woche.woche, kind__in=kinder
        ).select_related("kind")
    )
    if not zeilen or any(z.finalisiert_am is None for z in zeilen):
        return []
    if any(z.zuwachs_relativ is not None for z in zeilen):
        return []
    werte = einstellungen.werte(
        "spielregeln.held_basis_wochen",
        "spielregeln.held_min_wochen",
        "spielregeln.held_mindestbasis_punkte",
    )
    ergebnis = {}
    for z in zeilen:
        if z.neutral or z.pausentage >= neutral_ab:
            continue  # pausiert: ausgenommen
        hist = _historie(z, werte["spielregeln.held_basis_wochen"])
        ergebnis[z.pk] = zuwachs(
            z.xp_woche,
            hist,
            min_wochen=werte["spielregeln.held_min_wochen"],
            basis=werte["spielregeln.held_mindestbasis_punkte"],
        )
    if not ergebnis:
        return []
    kandidaten = {
        z.pk: ergebnis[z.pk]
        for z in zeilen
        if z.pk in ergebnis and z.aktiv and z.xp_woche > 0 and ergebnis[z.pk] > 0
    }
    beste = max(kandidaten.values(), default=None)
    helden = [z for z in zeilen if beste is not None and kandidaten.get(z.pk) == beste]
    with transaction.atomic():
        for z in zeilen:
            if z.pk in ergebnis:
                Wochenauswertung.objects.filter(pk=z.pk).update(
                    zuwachs_relativ=ergebnis[z.pk], held_der_woche=z in helden
                )
        if melden:
            for z in helden:
                _melden(z, ergebnis[z.pk], woche)
    return helden


def _melden(zeile, wert: Decimal, woche: IsoWoche):
    daten = {
        "woche": str(woche),
        "xp": zeile.xp_woche,
        "prozent": int((wert * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }
    for typ in (events.HELD, events.HELD_KIND):
        ereignisse.veroeffentlichen(
            typ, kind=zeile.kind, daten=daten, schluessel=f"{typ}:{zeile.kind_id}:{woche}"
        )


def sicherstellen(jetzt=None) -> dict:
    """Bewertet alle reifen, noch nicht bewerteten Wochen (Catch-up, idempotent)."""
    jetzt = jetzt or zeit.jetzt()
    aktuell = IsoWoche.von(jetzt)
    regeln = auswertung.regeln()
    kinder = list(konten.aktive_kinder())
    wochen = sorted(
        Wochenauswertung.objects.filter(montag__lt=aktuell.montag, kind__in=kinder)
        .values_list("iso_jahr", "iso_woche")
        .distinct()
    )
    bewertet = helden = 0
    for jahr, nr in wochen:
        woche = IsoWoche(jahr, nr)
        gefunden = woche_bewerten(
            woche, kinder, melden=woche == aktuell.vorherige(), neutral_ab=regeln.neutral_ab
        )
        helden += len(gefunden)
        bewertet += bool(gefunden)
    return {"wochen_mit_helden": bewertet, "helden": helden}
