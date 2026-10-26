"""Lesende Schnittstelle von spielregeln (AP20). Für AP21–AP23, AP29/30 und Oberflächen.

Alle Werte werden live aus der Historie berechnet (gleiche Rechnung wie Job und Neuberechnung,
``auswertung``); gespeicherte Stände sind nur Zwischenspeicher.

- ``stand(kind)``: Serie, aktive Wochen, Tagesserie, Rekorde, Pause heute.
- ``wochenserie_nach(kind, woche)``: Serie nach einer Woche (auch vor deren Abschluss).
  AP21 (Serienbonus, O5): ``wochenserie_nach(kind, woche.vorherige()) + 1``.
- ``woche_aktiv(kind, woche)``, ``pausentage(kind, woche)``, ``woche_pausiert(kind, woche)``
  (AP29: Kind gilt als pausiert ab N Pausentagen).
- ``wochenauswertung(kind, woche)``: gespeicherte Zeile (oder ``None``).
- ``quartal_voll_aktiv(kind, jahr, quartal)`` (AP23).
- ``aktuelle_pause(kind)``, ``pausen_uebersicht()`` (Eltern-UI).
- Held der Woche (AP30): ``helden(woche)``, ``zuwaechse(woche)``, ``held_titel(kind)``.
- Ränge (AP22): ``raenge()``, ``startrang()``, ``aktueller_rang(kind)`` (Rang mit ``stufe`` =
  Seltenheit 1–6, ``selten`` für ``data-selten``, ``mod_preis``, ``bauzeit_stunden``),
  ``rang_aufstiege(kind)`` (Fakten), ``rang_erreicht(kind, stufe)``, ``rang_fortschritt(kind)``,
  ``wirksamer_faktor(kind)``, ``globaler_faktor()``, ``kind_faktor(kind)``.
- Mod-Konditionen (AP26, für avatar): ``mod_preis(grund, kind)``, ``mod_bauzeit_stunden(grund,
  kind)``, ``preis_faktor(kind)``, ``bauzeit_faktor(kind)``, ``rang_zur_stufe(stufe)``.
- Abzeichen/Meilensteine (AP23): ``vitrine(kind)`` (verdient, nächste mit Fortschritt,
  Rekorde), ``verleihungen(kind)``, ``definitionen()``, ``symbol(definition, bereich)``,
  ``meilenstein_regeln()``, ``meilensteine_erreicht(kind, regel)``,
  ``meilenstein_erreicht(kind, schluessel, bereich)``, ``meilenstein_stand(kind, schluessel)``,
  ``abgeschlossene_quartale(kind)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Q

from apps.kern import zeit
from apps.kern.zeit import IsoWoche

from . import auswertung
from . import kontinuitaet as k
from .abzeichen import (  # noqa: F401 (öffentliche Abzeichen-/Meilenstein-API, AP23)
    BedingungsStand,
    Symbol,
    Vitrine,
    definitionen,
    meilenstein_erreicht,
    meilenstein_regeln,
    meilenstein_stand,
    meilensteine_erreicht,
    naechste,
    symbol,
    verleihungen,
    vitrine,
)
from .models import Aktivitaet, KindStand, Pause, Wochenauswertung
from .raenge import (  # noqa: F401 (öffentliche Rang-API, AP22; Mod-Konditionen AP26)
    RangFortschritt,
    aktueller_rang,
    bauzeit_faktor,
    globaler_faktor,
    kind_faktor,
    kind_wochen_faktor,
    mod_bauzeit_stunden,
    mod_preis,
    preis_faktor,
    raenge,
    rang_aufstiege,
    rang_erreicht,
    rang_fortschritt,
    rang_zur_stufe,
    startrang,
    wirksame_schwelle,
    wirksame_wochen,
    wirksamer_faktor,
    wochen_faktor,
)

Stand = auswertung.Stand


def stand(kind, jetzt=None) -> Stand:
    return auswertung.auswerten(kind, jetzt).stand


def gespeicherter_stand(kind) -> KindStand | None:
    return KindStand.objects.filter(kind=kind).first()


def wochenauswertung(kind, woche: IsoWoche) -> Wochenauswertung | None:
    return Wochenauswertung.objects.filter(
        kind=kind, iso_jahr=woche.jahr, iso_woche=woche.woche
    ).first()


def wochenauswertungen(kind):
    return Wochenauswertung.objects.filter(kind=kind).order_by("iso_jahr", "iso_woche")


def _ergebnisse_bis(kind, woche: IsoWoche) -> list[k.WochenErgebnis]:
    r = auswertung.regeln()
    if r.start is None or woche < IsoWoche.von(r.start):
        return []
    return k.wochen_auswerten(
        auswertung.aktive_tage(kind),
        auswertung.pausen(kind),
        IsoWoche.von(r.start),
        woche,
        r.neutral_ab,
    )


def wochenserie_nach(kind, woche: IsoWoche) -> int:
    """Wochenserie nach ``woche`` (pausenbereinigt), 0 vor Go-live. Ist ``woche`` die laufende
    Woche und noch nicht aktiv, gilt sie als neutral (laufende Woche bricht nie)."""
    ergebnisse = _ergebnisse_bis(kind, woche)
    if not ergebnisse:
        return 0
    letzte = ergebnisse[-1]
    if letzte.woche >= IsoWoche.von(zeit.heute()) and not letzte.aktiv:
        return ergebnisse[-2].wochenserie_danach if len(ergebnisse) > 1 else 0
    return letzte.wochenserie_danach


def wirksames_datum(meldedatum: date, erfasst_am) -> date:
    """K1 mit Puffer: Meldedatum, solange dessen Woche nicht abgeschlossen ist, sonst der Tag der
    Erfassung (Bestätigung). Gleiche Regel für Aktivität, Serienbonus und Punkte (Review AP31)."""
    r = auswertung.regeln()
    return k.wirksames_datum(meldedatum, erfasst_am, r.puffer_stunden, r.tz)


def woche_abgeschlossen_ab(woche: IsoWoche):
    """Zeitpunkt (UTC), ab dem ``woche`` abgeschlossen ist (Montag danach + Puffer, lokale
    Wanduhr). Einzige Quelle auch für familienziel (Review AP31)."""
    r = auswertung.regeln()
    return k.finalisiert_ab(woche, r.puffer_stunden, r.tz)


def woche_aktiv(kind, woche: IsoWoche) -> bool:
    return Aktivitaet.objects.filter(
        kind=kind, storniert=False, datum__range=(woche.montag, woche.sonntag)
    ).exists()


def aktive_tage(kind, von: date, bis: date) -> list[date]:
    return sorted(
        Aktivitaet.objects.filter(kind=kind, storniert=False, datum__range=(von, bis))
        .values_list("datum", flat=True)
        .distinct()
    )


def pausentage(kind, woche: IsoWoche) -> int:
    return k.pausentage(woche, auswertung.pausen(kind))


def woche_pausiert(kind, woche: IsoWoche) -> bool:
    """Kind gilt in ``woche`` als pausiert (ab N Pausentagen, K5) – z. B. Familienziel."""
    return pausentage(kind, woche) >= auswertung.regeln().neutral_ab


def ist_pausiert(kind, tag: date | None = None) -> bool:
    return k.pausiert(tag or zeit.heute(), auswertung.pausen(kind))


def quartal_voll_aktiv(kind, jahr: int, quartal: int) -> bool:
    """Alle Wochen des Quartals aktiv oder neutral, mindestens eine aktiv (ARCHITECTURE 7.5).
    Nur abgeschlossene Quartale sind aussagekräftig."""
    wochen = k.quartal_wochen(jahr, quartal)
    ergebnisse = {e.woche: e for e in _ergebnisse_bis(kind, wochen[-1])}
    if any(w not in ergebnisse for w in wochen):
        return False
    auswahl = [ergebnisse[w] for w in wochen]
    return all(e.aktiv or e.neutral for e in auswahl) and any(e.aktiv for e in auswahl)


def abgeschlossene_quartale(kind, jetzt=None) -> list[tuple[int, int, bool]]:
    """``(jahr, quartal, voll_aktiv)`` je Quartal ab Go-live, dessen letzte Woche finalisiert ist
    (AP23: Metrik ``quartal_voll_aktiv``). Das Go-live-Quartal zählt nur, wenn es mit Go-live
    beginnt (Wochen davor fehlen sonst, wie ``quartal_voll_aktiv``)."""
    a = auswertung.auswerten(kind, jetzt)
    final = {e.woche: e for e in a.wochen[: a.finalisiert]}
    if not final:
        return []
    erste = min(final)
    letzte = max(final)
    jahr, nummer = k.quartal(erste)
    ergebnis = []
    while True:
        wochen = k.quartal_wochen(jahr, nummer)
        if wochen[-1] > letzte:
            break
        auswahl = [final.get(w) for w in wochen]
        voll = all(e is not None and (e.aktiv or e.neutral) for e in auswahl) and any(
            e.aktiv for e in auswahl if e is not None
        )
        ergebnis.append((jahr, nummer, voll))
        jahr, nummer = (jahr + 1, 1) if nummer == 4 else (jahr, nummer + 1)
    return ergebnis


# --- Pausen ---------------------------------------------------------------------------------


def _laufend_q(heute):
    return Q(von__lte=heute) & (Q(bis__isnull=True) | Q(bis__gte=heute))


def aktuelle_pause(kind, heute: date | None = None) -> Pause | None:
    """Laufende Pause des Kindes oder der Familie (die mit dem spätesten Ende, offen zuerst)."""
    heute = heute or zeit.heute()
    pausen = list(
        Pause.objects.filter(Q(kind=kind) | Q(kind__isnull=True)).filter(_laufend_q(heute))
    )
    if not pausen:
        return None
    return max(pausen, key=lambda p: (p.bis is None, p.bis or date.min))


@dataclass(frozen=True)
class PausenUebersicht:
    laufend: list
    geplant: list
    vergangen: list


def pausen_uebersicht(heute: date | None = None, vergangen_limit=10) -> PausenUebersicht:
    heute = heute or zeit.heute()
    qs = Pause.objects.select_related("kind", "erstellt_von")
    return PausenUebersicht(
        laufend=list(qs.filter(_laufend_q(heute)).order_by("von", "id")),
        geplant=list(qs.filter(von__gt=heute).order_by("von", "id")),
        vergangen=list(qs.filter(bis__lt=heute).order_by("-bis", "-id")[:vergangen_limit]),
    )


def laufende_pause_von(ziel_kind, heute: date | None = None) -> Pause | None:
    """Laufende Pause genau dieses Ziels (Kind; ``None`` = Familie)."""
    heute = heute or zeit.heute()
    qs = Pause.objects.filter(_laufend_q(heute))
    qs = qs.filter(kind=ziel_kind) if ziel_kind is not None else qs.filter(kind__isnull=True)
    return qs.order_by("von", "id").first()


# --- Held der Woche (AP30) ------------------------------------------------------------------


def helden(woche: IsoWoche) -> list[Wochenauswertung]:
    """Helden der (bewerteten) Woche, Gleichstand = mehrere. Leer, wenn keiner oder unbewertet."""
    return list(
        Wochenauswertung.objects.filter(
            iso_jahr=woche.jahr, iso_woche=woche.woche, held_der_woche=True
        ).select_related("kind")
    )


def zuwaechse(woche: IsoWoche) -> list[Wochenauswertung]:
    """Alle bewerteten (nicht pausierten) Kinder der Woche, größter Zuwachs zuerst (Eltern)."""
    return list(
        Wochenauswertung.objects.filter(
            iso_jahr=woche.jahr, iso_woche=woche.woche, zuwachs_relativ__isnull=False
        )
        .select_related("kind")
        .order_by("-zuwachs_relativ", "kind__anzeigename")
    )


def held_titel(kind) -> int:
    """Wie oft das Kind Held der Woche war."""
    return Wochenauswertung.objects.filter(kind=kind, held_der_woche=True).count()
