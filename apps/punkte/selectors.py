"""Lesende Abfragen von punkte: Salden immer als Summe der Buchungen (DATA_MODEL 3.1).

- ``guthaben``: ausgebbare Punkte (steigt mit Aufgaben, sinkt mit Einlösung/Mod-Kauf).
- ``xp``: Gesamtpunkte für den Rang (sinkt nur durch Korrektur/Storno, ARCHITECTURE 13.2 K2).
- ``verfuegbar``: Guthaben minus Reservierungen anderer Module (``punkte.registry``).
"""

from dataclasses import dataclass

from django.db.models import Sum
from django.db.models.functions import Coalesce

from . import registry
from .models import Art, Buchung


@dataclass(frozen=True)
class Saldo:
    guthaben: int
    xp: int


def _summen(qs):
    return qs.aggregate(
        guthaben=Coalesce(Sum("guthaben_delta"), 0), xp=Coalesce(Sum("xp_delta"), 0)
    )


def salden(kind):
    return Saldo(**_summen(Buchung.objects.filter(kind=kind)))


def guthaben(kind):
    return salden(kind).guthaben


def xp(kind):
    return salden(kind).xp


def reserviert(kind):
    """Summe aller Reservierungen (z. B. offene Einlöseanträge, AP15)."""
    summe = 0
    for r in registry.reservierungen():
        wert = r.funktion(kind)
        if not isinstance(wert, int) or isinstance(wert, bool) or wert < 0:
            raise ValueError(f"Reservierungs-Provider '{r.schluessel}' lieferte {wert!r}")
        summe += wert
    return summe


def verfuegbar(kind):
    """Zum Beantragen/Ausgeben verfügbar: Guthaben minus Reservierungen."""
    return guthaben(kind) - reserviert(kind)


def xp_zeitraum(von, bis, *, kind=None):
    """XP mit Bezugsdatum in ``[von, bis]`` (inklusiv), z. B. Familienziel-Woche (K8)."""
    qs = Buchung.objects.filter(bezugsdatum__range=(von, bis))
    if kind is not None:
        qs = qs.filter(kind=kind)
    return _summen(qs)["xp"]


def aufgaben_anzahl(kind, von, bis):
    """Anzahl bestätigter Aufgaben-Buchungen (ohne stornierte) mit Bezugsdatum in ``[von, bis]``."""
    return (
        Buchung.objects.filter(kind=kind, art=Art.AUFGABE, bezugsdatum__range=(von, bis))
        .exclude(storno__isnull=False)
        .count()
    )


def xp_je_tag(kind, von, bis):
    """``{bezugsdatum: xp}`` eines Kindes in ``[von, bis]`` (inklusiv), nur Tage mit Buchungen
    (Wochenauswertung, spielregeln)."""
    zeilen = (
        Buchung.objects.filter(kind=kind, bezugsdatum__range=(von, bis))
        .values("bezugsdatum")
        .annotate(xp=Sum("xp_delta"))
        .order_by()
    )
    return {z["bezugsdatum"]: z["xp"] for z in zeilen}


def buchungen(kind):
    """Buchungen eines Kindes, neueste zuerst."""
    return Buchung.objects.filter(kind=kind).order_by("-gebucht_am", "-id")


def buchung_zu_schluessel(schluessel):
    return Buchung.objects.filter(idempotenz_schluessel=schluessel).first()


def buchungen_zu(referenz_typ, referenz_id):
    return Buchung.objects.filter(referenz_typ=referenz_typ, referenz_id=str(referenz_id))


def buchungen_zu_schluesseln(schluessel):
    """``{schluessel: Buchung}`` für die vorhandenen Schlüssel (z. B. Serienbonus je Instanz)."""
    return {
        b.idempotenz_schluessel: b
        for b in Buchung.objects.filter(idempotenz_schluessel__in=list(schluessel))
    }
