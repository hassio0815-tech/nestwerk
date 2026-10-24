"""Lesende Schnittstelle von familienziel (AP29).

Der Fortschritt wird nie gespeichert: Punkte kommen live aus ``punkte`` (XP-Zuwachs aller Kinder
mit Bezugsdatum in der Woche; Aufgaben, Serienbonus und Sonderpunkte zählen, Korrekturen mindern,
K8), die Bedingung aus ``spielregeln`` (jedes nicht pausierte Kind hat eine Aktivität).

- ``stand(iso, ziel)``: ``Stand`` mit Punkten, Prozent, Beiträgen, Bedingung.
- ``ansicht(jetzt)``: alles für Tablet-Leiste und Dashboards (aktuelle Woche, Abstimmung, Großziel).
- ``woche(iso)``, ``historie()``, ``belohnungen()``, ``wahl_optionen()``, ``serie()``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from apps.kern import einstellungen, zeit
from apps.kern.zeit import IsoWoche
from apps.konten import selectors as konten
from apps.punkte import selectors as punkte
from apps.spielregeln import selectors as spielregeln

from . import zeitplan
from .models import (
    AbstimmungStatus,
    Familienbelohnung,
    Familienwoche,
    Grossziel,
    Stimme,
    WochenStatus,
)


@dataclass(frozen=True)
class Beitrag:
    kind: object
    xp: int
    aktiv: bool
    pausiert: bool


@dataclass(frozen=True)
class Stand:
    iso: IsoWoche
    ziel: int
    punkte: int
    beitraege: list
    offen: list  # Kinder ohne bestätigte Aufgabe (nicht pausiert)
    alle_pausiert: bool

    @property
    def prozent(self):
        return min(100, int(self.punkte * 100 / self.ziel)) if self.ziel else 0

    @property
    def punkte_ok(self):
        return self.punkte >= self.ziel

    @property
    def bedingung_ok(self):
        return not self.offen

    @property
    def erreichbar(self):
        """Ziel und Bedingung erfüllt: die Woche ist (jetzt) geschafft."""
        return self.punkte_ok and self.bedingung_ok


def stand(iso: IsoWoche, ziel: int) -> Stand:
    beitraege = []
    for kind in konten.aktive_kinder():
        beitraege.append(
            Beitrag(
                kind=kind,
                xp=punkte.xp_zeitraum(iso.montag, iso.sonntag, kind=kind),
                aktiv=spielregeln.woche_aktiv(kind, iso),
                pausiert=spielregeln.woche_pausiert(kind, iso),
            )
        )
    beitraege.sort(key=lambda b: b.kind.anzeigename.lower())  # alphabetisch, keine Wertung
    summe = sum(b.xp for b in beitraege)
    return Stand(
        iso=iso,
        ziel=ziel,
        punkte=max(0, summe),
        beitraege=beitraege,
        offen=[b.kind for b in beitraege if not b.pausiert and not b.aktiv],
        alle_pausiert=all(b.pausiert for b in beitraege),
    )


def wochenziel_start() -> int:
    return einstellungen.wert("familienziel.wochenziel_punkte")


def woche(iso: IsoWoche) -> Familienwoche | None:
    return (
        Familienwoche.objects.select_related("belohnung")
        .filter(iso_jahr=iso.jahr, iso_woche=iso.woche)
        .first()
    )


def belohnungen(nur_aktive=False):
    qs = Familienbelohnung.objects.all()
    return qs.filter(aktiv=True) if nur_aktive else qs


def wahl_optionen():
    """Belohnungen, aus denen die Kinder wählen: aktiv, kein Großziel."""
    return Familienbelohnung.objects.filter(aktiv=True, ist_grossziel=False)


def historie(limit=20):
    return list(Familienwoche.objects.select_related("belohnung").order_by("-montag")[:limit])


def grossziele():
    return list(Grossziel.objects.select_related("ausloesende_woche", "belohnung"))


def serie(jetzt=None) -> int:
    """Erreichte Wochenziele in Folge seit dem letzten Großziel (neutrale Wochen zählen nicht,
    brechen aber nicht; die laufende, noch offene Woche bricht nie)."""
    heute_montag = IsoWoche.von(jetzt or zeit.jetzt()).montag
    letzte = (
        Grossziel.objects.select_related("ausloesende_woche")
        .order_by("-ausloesende_woche__montag")
        .first()
    )
    qs = Familienwoche.objects.order_by("montag")
    if letzte:
        qs = qs.filter(montag__gt=letzte.ausloesende_woche.montag)
    zaehler, vorher = 0, None
    for w in qs:
        if vorher is not None and w.montag != vorher + timedelta(days=7):
            zaehler = 0
        vorher = w.montag
        if w.status == WochenStatus.ERREICHT:
            zaehler += 1
        elif w.status == WochenStatus.VERFEHLT:
            zaehler = 0
        elif w.status == WochenStatus.LAUFEND and w.montag < heute_montag:
            zaehler = 0
    return zaehler


# --- Abstimmung -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Abstimmung:
    zielwoche: IsoWoche
    woche: Familienwoche
    optionen: list
    stimmen: dict  # belohnung_id -> Anzahl
    abgegeben: int
    kinder: int
    beginn: object
    ende: object


def abstimmung_offen(jetzt=None) -> Abstimmung | None:
    """Laufende Abstimmung (für die nächste Woche) oder ``None``."""
    jetzt = jetzt or zeit.jetzt()
    ziel = IsoWoche.von(jetzt).naechste()
    if not zeitplan.abstimmung_offen_zeitlich(ziel, jetzt):
        return None
    zeile = woche(ziel)
    if zeile is not None and zeile.abstimmung_status != AbstimmungStatus.OFFEN:
        return None
    stimmen = Counter(
        Stimme.objects.filter(woche__iso_jahr=ziel.jahr, woche__iso_woche=ziel.woche).values_list(
            "belohnung_id", flat=True
        )
    )
    beginn, ende = zeitplan.abstimmung_fenster(ziel)
    return Abstimmung(
        zielwoche=ziel,
        woche=zeile,
        optionen=list(wahl_optionen()),
        stimmen=dict(stimmen),
        abgegeben=sum(stimmen.values()),
        kinder=len(konten.aktive_kinder()),
        beginn=beginn,
        ende=ende,
    )


def eigene_stimme(kind, abstimmung: Abstimmung | None):
    if abstimmung is None or abstimmung.woche is None:
        return None
    return (
        Stimme.objects.select_related("belohnung").filter(woche=abstimmung.woche, kind=kind).first()
    )


def gleichstand_wochen():
    """Wochen, für die die Eltern das Ziel wählen müssen."""
    return list(
        Familienwoche.objects.select_related("belohnung")
        .filter(abstimmung_status=AbstimmungStatus.GLEICHSTAND, status=WochenStatus.LAUFEND)
        .order_by("montag")
    )


# --- Gesamtansicht --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ansicht:
    iso: IsoWoche
    woche: Familienwoche | None
    stand: Stand
    belohnung: Familienbelohnung | None
    status: str
    abstimmung: Abstimmung | None
    serie: int
    serie_ziel: int
    grossziel: Grossziel | None  # freigeschaltet, noch nicht eingelöst
    fehlt: int = 0
    namen_offen: list = field(default_factory=list)

    @property
    def erreicht(self):
        return self.status == WochenStatus.ERREICHT


def ansicht(jetzt=None) -> Ansicht:
    jetzt = jetzt or zeit.jetzt()
    iso = IsoWoche.von(jetzt)
    zeile = woche(iso)
    ziel = zeile.ziel_punkte if zeile else wochenziel_start()
    st = stand(iso, ziel)
    offen_gross = (
        Grossziel.objects.select_related("belohnung")
        .filter(eingeloest_am__isnull=True)
        .order_by("-freigeschaltet_am")
        .first()
    )
    return Ansicht(
        iso=iso,
        woche=zeile,
        stand=st,
        belohnung=zeile.belohnung if zeile else None,
        status=zeile.status if zeile else WochenStatus.LAUFEND,
        abstimmung=abstimmung_offen(jetzt),
        serie=serie(jetzt),
        serie_ziel=einstellungen.wert("familienziel.grossziel_serie"),
        grossziel=offen_gross,
        fehlt=max(0, st.ziel - st.punkte),
        namen_offen=[k.anzeigename for k in st.offen],
    )
