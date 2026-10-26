"""Schreibende Schnittstelle von spielregeln (AP20): Aktivität, Pausen, Wochenauswertung.

Öffentlich für andere Module:

- ``aktivitaet_erfassen(kind, datum, modul=, referenz=, erfasst_am=)``: Fakt "Kind war aktiv"
  (aufgaben über den Erledigungs-Hook; später ``lernen``). Idempotent je (modul, referenz).
- ``aktivitaet_stornieren(modul=, referenz=)``: Storno (Korrektur einer Aufgabe).
- ``pause_setzen`` / ``pause_beenden`` / ``pause_loeschen`` / ``pausen_beenden_fuer``.
- ``wochen_sicherstellen(kind=None, jetzt=None)``: bringt Wochenauswertungen und Spielstand auf
  den Soll-Stand (idempotent, Catch-up über beliebig viele Wochen). Job und Lazy-Aufruf.
- ``neu_berechnen(schreiben=False)``: Abgleich gespeicherter Stände mit der Historie.
- ``serienbonus_buchen(kind, basispunkte=, meldedatum=, erfasst_am=, schluessel=, ...)``
  (AP21): eigene Ledger-Buchung "Serienbonus" in der Transaktion des Aufrufers, idempotent je
  Schlüssel. Storno macht der Aufrufer per ``punkte.gegenbuchen`` (Schlüssel gehört ihm).
- Ränge (AP22, ``raenge``): ``raenge_pruefen(kind)``, ``rang_aendern(rang, von=, ...)``,
  ``kalibrierung_setzen(kind_oder_None, faktor, von=)``; Prüfung läuft automatisch bei
  XP-Zuwachs (``punkte.gebucht``) und in ``kind_auswerten``.
- Abzeichen/Meilensteine (AP23, ``abzeichen``): ``abzeichen_pruefen(kind)`` (Module nach
  Änderung eigener Metriken), ``abzeichen_alle_pruefen()``, ``abzeichen_speichern(...)``,
  ``abzeichen_aktiv_setzen(...)``, ``meilenstein_anlegen(schluessel, name, bedingungen, modul=)``.
  Prüfung läuft automatisch am Ende von ``kind_auswerten`` und bei ``rang.aufgestiegen``.

Gespeicherte Stände (``Wochenauswertung``, ``KindStand``) sind Zwischenspeicher: jede Auswertung
rechnet die vergangenen Wochen eines Kindes komplett aus der Historie und schreibt nur
Abweichungen. Ereignisse (``woche.ausgewertet``, ``serie.*``) entstehen genau einmal beim
Abschluss einer Woche (Ereignis-Schlüssel).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Q

from apps.ereignisse import services as ereignisse
from apps.kern import audit, zeit
from apps.konten import selectors as konten

from . import abzeichen, auswertung, events, held, raenge, serienbonus
from . import kontinuitaet as k
from .abzeichen import (  # noqa: F401 (öffentliche Abzeichen-/Meilenstein-API, AP23)
    AbzeichenFehler,
    abzeichen_aktiv_setzen,
    abzeichen_speichern,
    meilenstein_anlegen,
)
from .abzeichen import alle_pruefen as abzeichen_alle_pruefen  # noqa: F401
from .abzeichen import pruefen as abzeichen_pruefen  # noqa: F401
from .models import Aktivitaet, KindStand, Pause, PauseQuelle, Wochenauswertung
from .raenge import (  # noqa: F401 (öffentliche Rang-API, AP22; Mod-Standards AP26)
    RangFehler,
    kalibrierung_setzen,
    mod_faktoren_setzen,
    mod_standard_aendern,
    raenge_pruefen,
    rang_aendern,
    wochen_faktor_setzen,
)

logger = logging.getLogger("nestwerk.spielregeln")

GRUND_MAX = 120
WOCHEN_FELDER = (
    "montag",
    "aktiv",
    "neutral",
    "pausentage",
    "xp_woche",
    "wochenserie_danach",
    "aktive_wochen_gesamt",
)
STAND_FELDER = (
    "wochenserie",
    "rekord_wochenserie",
    "aktive_wochen_gesamt",
    "tagesserie",
    "rekord_tagesserie",
    "letzte_woche",
    "stand_datum",
)


class SpielregelnFehler(ValueError):
    """Fachlicher Fehler (Meldung ist für Eltern lesbar)."""


# --- Aktivität ------------------------------------------------------------------------------


def _kind_pruefen(kind):
    if getattr(kind, "pk", None) is None or getattr(kind, "rolle", None) != "kind":
        raise SpielregelnFehler("Aktivitäten und Pausen gibt es nur für Kinder.")


@transaction.atomic
def aktivitaet_erfassen(kind, datum: date, *, modul: str, referenz, erfasst_am=None):
    """Erfasst eine Aktivität (idempotent je ``modul``/``referenz``) und gibt sie zurück.

    ``datum`` = fachliches Bezugsdatum (aufgaben: Meldedatum, K1). Ist dessen Woche bei
    ``erfasst_am`` (Bestätigung) schon abgeschlossen, zählt der Tag der Bestätigung.
    Läuft in der Transaktion des Aufrufers.
    """
    _kind_pruefen(kind)
    referenz = str(referenz)
    if not modul or len(modul) > 40 or not referenz or len(referenz) > 60:
        raise SpielregelnFehler("modul (max. 40) und referenz (max. 60) sind Pflicht.")
    bestehend = Aktivitaet.objects.filter(modul=modul, referenz=referenz).first()
    if bestehend is not None:
        return bestehend
    erfasst_am = erfasst_am or zeit.jetzt()
    r = auswertung.regeln()
    wirksam = k.wirksames_datum(datum, erfasst_am, r.puffer_stunden, r.tz)
    aktivitaet = Aktivitaet.objects.create(
        kind=kind, datum=wirksam, modul=modul, referenz=referenz, erstellt_am=erfasst_am
    )
    stand = _nachfuehren(kind, erfasst_am)
    ereignisse.veroeffentlichen(
        events.AKTIVITAET_ERFASST,
        kind=kind,
        daten={
            "aktivitaet": aktivitaet.pk,
            "datum": wirksam.isoformat(),
            "meldedatum": datum.isoformat(),
            "modul": modul,
            "referenz": referenz,
            "tagesserie": stand.tagesserie if stand else 0,
        },
        schluessel=f"{events.AKTIVITAET_ERFASST}:{modul}:{referenz}"[:150],
    )
    return aktivitaet


@transaction.atomic
def aktivitaet_stornieren(*, modul: str, referenz, jetzt=None) -> bool:
    """Markiert eine Aktivität als storniert (Korrektur) und rechnet die Stände des Kindes neu.
    ``False``, wenn es keine (nicht stornierte) Aktivität gibt."""
    aktivitaet = Aktivitaet.objects.filter(
        modul=modul, referenz=str(referenz), storniert=False
    ).first()
    if aktivitaet is None:
        return False
    Aktivitaet.objects.filter(pk=aktivitaet.pk).update(storniert=True)
    _nachfuehren(aktivitaet.kind, jetzt)
    return True


def _nachfuehren(kind, jetzt=None):
    """Stände eines Kindes nach einer Änderung der Historie nachführen (Lazy-Evaluation).

    Läuft in einem Savepoint: Ein Fehler hier darf die fachliche Änderung (z. B. Bestätigung)
    nicht kippen; der Job holt es nach. Gibt den Stand zurück oder ``None``.
    """
    try:
        with transaction.atomic():
            return kind_auswerten(kind, jetzt)
    except Exception:
        logger.exception("Spielstand von %s konnte nicht nachgeführt werden", kind.pk)
        return None


# --- Serienbonus (AP21) ---------------------------------------------------------------------


@transaction.atomic
def serienbonus_buchen(
    kind,
    *,
    basispunkte: int,
    meldedatum: date,
    erfasst_am=None,
    schluessel: str,
    quelle_modul: str,
    referenz=None,
    von=None,
):
    """Bucht den Serienbonus auf ``basispunkte`` (nur Aufgabenpunkte, nie Sonderpunkte) und gibt
    die Buchung zurück; ``None`` bei 0 % / 0 Punkten. Bezugsdatum = Meldedatum (K1). Gibt es den
    Schlüssel schon, bleibt es bei der bestehenden Buchung (kein zweites Pop-up)."""
    from apps.punkte import selectors as punkte_selectors
    from apps.punkte import services as punkte

    _kind_pruefen(kind)
    bestehend = punkte_selectors.buchung_zu_schluessel(schluessel)
    if bestehend is not None:
        return bestehend
    r = auswertung.regeln()
    wirksam = k.wirksames_datum(meldedatum, erfasst_am or zeit.jetzt(), r.puffer_stunden, r.tz)
    woche = zeit.IsoWoche.von(wirksam)
    serie = serienbonus.serie_fuer(kind, woche)
    satz = serienbonus.prozent(serie)
    bonus = serienbonus.bonus_punkte(basispunkte, satz)
    if not bonus:
        return None
    buchung = punkte.buchen(
        kind,
        punkte.Art.SERIENBONUS,
        bonus,
        schluessel=schluessel,
        quelle_modul=quelle_modul,
        bezugsdatum=wirksam,  # wie Aktivität und Grundpunkte (Review AP31)
        referenz=referenz,
        begruendung=f"Serienbonus +{satz} % (Serie {serie})",
        von=von,
    )
    ereignisse.veroeffentlichen(
        events.SERIENBONUS_GEBUCHT,
        kind=kind,
        daten={
            "buchung": buchung.pk,
            "punkte": bonus,
            "prozent": satz,
            "serie": serie,
            "woche": str(woche),
            "basispunkte": basispunkte,
        },
        schluessel=f"{events.SERIENBONUS_GEBUCHT}:{buchung.pk}",
    )
    return buchung


# --- Pausen ---------------------------------------------------------------------------------


def _datum_text(tag: date) -> str:
    return tag.strftime("%d.%m.%Y")


def _zeitraum_text(von: date, bis: date | None) -> str:
    if bis is None:
        return f"ab {_datum_text(von)}"
    if bis == von:
        return f"am {_datum_text(von)}"
    return f"vom {_datum_text(von)} bis {_datum_text(bis)}"


def _betroffene(pause):
    return [pause.kind] if pause.kind_id else list(konten.aktive_kinder())


def _pause_daten(pause, **extra):
    return {
        "pause": pause.pk,
        "familie": pause.familie,
        "von": pause.von.isoformat(),
        "bis": pause.bis.isoformat() if pause.bis else "",
        "zeitraum": _zeitraum_text(pause.von, pause.bis),
        **extra,
    }


def _akteur_pruefen(von, quelle):
    if quelle == PauseQuelle.ELTERN and getattr(von, "rolle", None) != "eltern":
        raise SpielregelnFehler("Pausen setzen nur Eltern.")


def _audit(aktion, pause, von, **details):
    audit.protokollieren(
        aktion,
        akteur=von,
        objekt=pause,
        kind=pause.kind,
        details={"familie": pause.familie, **_pause_daten(pause), **details},
    )


def laufende_pausen(ziel_kind=None, heute=None):
    """Laufende Pausen genau dieses Ziels (Kind oder ``None`` = Familie)."""
    heute = heute or zeit.heute()
    qs = Pause.objects.filter(von__lte=heute).filter(Q(bis__isnull=True) | Q(bis__gte=heute))
    return qs.filter(kind=ziel_kind) if ziel_kind is not None else qs.filter(kind__isnull=True)


@transaction.atomic
def pause_setzen(
    kind,
    *,
    von,
    ab: date | None = None,
    bis: date | None = None,
    grund: str = "",
    quelle: str = PauseQuelle.ELTERN,
    jetzt=None,
):
    """Neue Pause für ``kind`` oder die ganze Familie (``kind=None``), ``ab`` Standard heute.

    Rückwirkende Pausen sind erlaubt (gerissene Serien werden dann neu berechnet). Eine
    zweite offene/laufende Pause desselben Ziels wird abgelehnt (Schalter "an" doppelt).
    """
    jetzt = jetzt or zeit.jetzt()
    heute = zeit.heute(jetzt)
    if kind is not None:
        _kind_pruefen(kind)
    quelle = PauseQuelle(quelle)
    _akteur_pruefen(von, quelle)
    ab = ab or heute
    grund = (grund or "").strip()
    if len(grund) > GRUND_MAX:
        raise SpielregelnFehler(f"Grund ist zu lang (höchstens {GRUND_MAX} Zeichen).")
    if bis is not None and bis < ab:
        raise SpielregelnFehler("Das Ende liegt vor dem Beginn.")
    if ab <= heute and laufende_pausen(kind, heute).exists():
        wer = kind.anzeigename if kind is not None else "Die Familie"
        raise SpielregelnFehler(f"{wer} hat schon eine laufende Pause.")
    pause = Pause.objects.create(
        kind=kind,
        von=ab,
        bis=bis,
        grund=grund,
        quelle=quelle,
        erstellt_von=von if getattr(von, "pk", None) else None,
        erstellt_am=jetzt,
    )
    _audit("pause.gesetzt", pause, von, grund=grund, quelle=quelle)
    for betroffen in _betroffene(pause):
        ereignisse.veroeffentlichen(
            events.PAUSE_GESTARTET,
            kind=betroffen,
            akteur=von if getattr(von, "pk", None) else None,
            daten=_pause_daten(pause),
            schluessel=f"{events.PAUSE_GESTARTET}:{pause.pk}:{betroffen.pk}",
        )
        _nachfuehren(betroffen, jetzt)
    return pause


@transaction.atomic
def pause_beenden(pause, *, von, bis: date | None = None, jetzt=None):
    """Beendet eine laufende Pause: ``bis`` Standard = gestern (heute zählt wieder normal),
    frühestens der erste Pausentag. Geplante Pausen (Beginn in der Zukunft) werden gelöscht."""
    jetzt = jetzt or zeit.jetzt()
    heute = zeit.heute(jetzt)
    _akteur_pruefen(von, PauseQuelle.ELTERN if getattr(von, "pk", None) else "hausautomation")
    pause = Pause.objects.select_related("kind").get(pk=pause.pk)
    if pause.von > heute:
        return pause_loeschen(pause, von=von, jetzt=jetzt)
    if pause.bis is not None and pause.bis < heute:
        raise SpielregelnFehler("Diese Pause ist schon vorbei.")
    neues_bis = bis if bis is not None else max(pause.von, heute - timedelta(days=1))
    if neues_bis < pause.von:
        raise SpielregelnFehler("Das Ende liegt vor dem Beginn.")
    if not Pause.objects.filter(pk=pause.pk, bis=pause.bis).update(bis=neues_bis):
        raise SpielregelnFehler("Die Pause wurde gerade geändert. Bitte neu laden.")
    alt, pause.bis = pause.bis, neues_bis
    _audit("pause.beendet", pause, von, bis_vorher=alt.isoformat() if alt else "")
    hinweis = f"Deine Pause endet am {_datum_text(neues_bis)}."
    if pause.familie:
        hinweis = f"Die Familienpause endet am {_datum_text(neues_bis)}."
    _pause_ende_melden(pause, von, hinweis, jetzt=jetzt)
    return pause


@transaction.atomic
def pause_loeschen(pause, *, von, jetzt=None):
    """Löscht eine geplante Pause (Beginn in der Zukunft). Begonnene Pausen werden beendet,
    nie gelöscht (Historie)."""
    jetzt = jetzt or zeit.jetzt()
    pause = Pause.objects.select_related("kind").get(pk=pause.pk)
    if pause.von <= zeit.heute(jetzt):
        raise SpielregelnFehler("Begonnene Pausen werden beendet, nicht gelöscht.")
    _akteur_pruefen(von, PauseQuelle.ELTERN if getattr(von, "pk", None) else "hausautomation")
    _audit("pause.geloescht", pause, von)
    betroffene = _betroffene(pause)
    pk = pause.pk
    pause.delete()
    pause.pk = pk
    _pause_ende_melden(
        pause, von, "Die geplante Pause entfällt.", betroffene=betroffene, jetzt=jetzt
    )
    return None


def _pause_ende_melden(pause, von, hinweis, *, betroffene=None, jetzt=None):
    for betroffen in betroffene if betroffene is not None else _betroffene(pause):
        ereignisse.veroeffentlichen(
            events.PAUSE_BEENDET,
            kind=betroffen,
            akteur=von if getattr(von, "pk", None) else None,
            daten=_pause_daten(pause, hinweis=hinweis),
            schluessel=f"{events.PAUSE_BEENDET}:{pause.pk}:{betroffen.pk}:{pause.bis or 'x'}",
        )
        _nachfuehren(betroffen, jetzt)


@transaction.atomic
def pausen_beenden_fuer(ziel_kind, *, von, jetzt=None) -> int:
    """Schalter "Pause aus": beendet alle laufenden Pausen genau dieses Ziels."""
    jetzt = jetzt or zeit.jetzt()
    anzahl = 0
    for pause in list(laufende_pausen(ziel_kind, zeit.heute(jetzt))):
        pause_beenden(pause, von=von, jetzt=jetzt)
        anzahl += 1
    return anzahl


# --- Wochenauswertung -----------------------------------------------------------------------


def _wochen_werte(e: k.WochenErgebnis, xp: int) -> dict:
    return {
        "montag": e.woche.montag,
        "aktiv": e.aktiv,
        "neutral": e.neutral,
        "pausentage": e.pausentage,
        "xp_woche": xp,
        "wochenserie_danach": e.wochenserie_danach,
        "aktive_wochen_gesamt": e.aktive_wochen_gesamt,
    }


def _stand_werte(stand: auswertung.Stand) -> dict:
    return {
        "wochenserie": stand.wochenserie,
        "rekord_wochenserie": stand.rekord_wochenserie,
        "aktive_wochen_gesamt": stand.aktive_wochen_gesamt,
        "tagesserie": stand.tagesserie,
        "rekord_tagesserie": stand.rekord_tagesserie,
        "letzte_woche": str(stand.letzte_woche) if stand.letzte_woche else "",
        "stand_datum": stand.stand_datum,
    }


@dataclass
class Zaehler:
    angelegt: int = 0
    geaendert: int = 0
    finalisiert: int = 0
    entfernt: int = 0

    def plus(self, anderer):
        for feld in ("angelegt", "geaendert", "finalisiert", "entfernt"):
            setattr(self, feld, getattr(self, feld) + getattr(anderer, feld))


def kind_auswerten(kind, jetzt=None, *, zaehler: Zaehler | None = None, melden=True):
    """Soll-Stand eines Kindes aus der Historie berechnen und speichern (idempotent).

    Gibt den ``auswertung.Stand`` zurück. ``melden=False``: keine Ereignisse (Reparatur).
    """
    jetzt = jetzt or zeit.jetzt()
    zaehler = zaehler if zaehler is not None else Zaehler()
    r = auswertung.regeln()
    a = auswertung.auswerten(kind, jetzt, r)
    xp = auswertung.xp_je_woche(kind, a.wochen)
    bestehend = {(w.iso_jahr, w.iso_woche): w for w in Wochenauswertung.objects.filter(kind=kind)}
    neu_final = []
    for i, e in enumerate(a.wochen):
        werte = _wochen_werte(e, xp.get(e.woche, 0))
        final = i < a.finalisiert
        zeile = bestehend.pop((e.woche.jahr, e.woche.woche), None)
        if zeile is None:
            Wochenauswertung.objects.create(
                kind=kind,
                iso_jahr=e.woche.jahr,
                iso_woche=e.woche.woche,
                finalisiert_am=jetzt if final else None,
                **werte,
            )
            zaehler.angelegt += 1
            if final:
                neu_final.append(i)
            continue
        geaendert = {f: v for f, v in werte.items() if getattr(zeile, f) != v}
        if final and zeile.finalisiert_am is None:
            geaendert["finalisiert_am"] = jetzt
            neu_final.append(i)
        if geaendert:
            Wochenauswertung.objects.filter(pk=zeile.pk).update(**geaendert)
            zaehler.geaendert += 1
    if bestehend:  # Wochen außerhalb des Bereichs (z. B. Go-live verschoben): Cache entfernen
        Wochenauswertung.objects.filter(pk__in=[z.pk for z in bestehend.values()]).delete()
        zaehler.entfernt += len(bestehend)
    zaehler.finalisiert += len(neu_final)

    werte = _stand_werte(a.stand)
    stand_zeile = KindStand.objects.filter(kind=kind).first()
    if stand_zeile is None:
        KindStand.objects.create(kind=kind, aktualisiert_am=jetzt, **werte)
    else:
        # aktualisiert_am = Zeitpunkt der Auswertung; Neuberechnung prüft gegen diesen Stand
        KindStand.objects.filter(kind=kind).update(aktualisiert_am=jetzt, **werte)

    if melden and neu_final:
        _abschluss_melden(kind, a, neu_final)
    # AP22: neue aktive Wochen können einen Aufstieg freischalten; Stand-Rang = höchster Fakt
    raenge.raenge_pruefen(
        kind, jetzt=jetzt, aktive_wochen=a.stand.aktive_wochen_gesamt, melden=melden
    )
    raenge._stand_rang_setzen(kind, raenge.aktueller_rang(kind))
    # AP23: Abzeichen/Meilensteine (Catch-up; Fakten bleiben, Savepoint)
    abzeichen.pruefen_sicher(kind, jetzt=jetzt, melden=melden)
    return a.stand


def _abschluss_melden(kind, a: auswertung.Auswertung, neu_final: list[int]):
    """``woche.ausgewertet`` je neu abgeschlossener Woche; Serien-Nachricht nur für die jüngste
    (Catch-up nach Ausfall erzeugt keine Pop-up-Flut)."""
    for i in neu_final:
        e = a.wochen[i]
        ereignisse.veroeffentlichen(
            events.WOCHE_AUSGEWERTET,
            kind=kind,
            daten={
                "woche": str(e.woche),
                "iso_jahr": e.woche.jahr,
                "iso_woche": e.woche.woche,
                "aktiv": e.aktiv,
                "neutral": e.neutral,
                "pausentage": e.pausentage,
                "wochenserie": e.wochenserie_danach,
                "aktive_wochen_gesamt": e.aktive_wochen_gesamt,
            },
            schluessel=f"{events.WOCHE_AUSGEWERTET}:{kind.pk}:{e.woche}",
        )
    i = neu_final[-1]
    e = a.wochen[i]
    vorher = a.wochen[i - 1].wochenserie_danach if i else 0
    daten = {"woche": str(e.woche), "wochenserie": e.wochenserie_danach, "vorher": vorher}
    if e.wochenserie_danach > vorher:
        typ = events.SERIE_GESTIEGEN
    elif e.wochenserie_danach == 0 and vorher > 0:
        typ = events.SERIE_GERISSEN
    else:
        return
    ereignisse.veroeffentlichen(
        typ, kind=kind, daten=daten, schluessel=f"{typ}:{kind.pk}:{e.woche}"
    )


def wochen_sicherstellen(kind=None, jetzt=None) -> dict:
    """Job und Lazy-Aufruf: Soll-Stand für ein Kind oder alle aktiven Kinder (je Kind eine
    Transaktion). Gibt Zähler zurück."""
    jetzt = jetzt or zeit.jetzt()
    kinder = [kind] if kind is not None else list(konten.aktive_kinder())
    gesamt = Zaehler()
    for kind in kinder:
        with transaction.atomic():
            kind_auswerten(kind, jetzt, zaehler=gesamt)
    with transaction.atomic():
        gesamt_held = held.sicherstellen(jetzt)  # AP30: Held der Woche (idempotent)
    return {"kinder": len(kinder), **gesamt.__dict__, **gesamt_held}


# --- XP der Woche aktuell halten ------------------------------------------------------------


def xp_nachfuehren(ereignis):
    """Synchroner Handler für ``punkte.gebucht``: XP einer bereits gespeicherten Woche
    nachführen (z. B. späte Sonderpunkte mit Bezugsdatum in einer abgeschlossenen Woche).
    Savepoint: ein Fehler hier darf die Buchung nicht kippen (der Job holt es nach)."""
    try:
        with transaction.atomic():
            _xp_nachfuehren(ereignis)
    except Exception:
        logger.exception("XP der Woche für Ereignis %s nicht nachgeführt", ereignis.pk)


def _xp_nachfuehren(ereignis):
    from apps.punkte import selectors as punkte

    if ereignis.kind_id is None or not ereignis.daten.get("bezugsdatum"):
        return
    woche = zeit.IsoWoche.von(date.fromisoformat(ereignis.daten["bezugsdatum"]))
    zeile = Wochenauswertung.objects.filter(
        kind_id=ereignis.kind_id, iso_jahr=woche.jahr, iso_woche=woche.woche
    ).first()
    if zeile is None:
        return
    xp = punkte.xp_zeitraum(woche.montag, woche.sonntag, kind=ereignis.kind)
    if xp != zeile.xp_woche:
        Wochenauswertung.objects.filter(pk=zeile.pk).update(xp_woche=xp)


# --- Neuberechnung --------------------------------------------------------------------------


@dataclass(frozen=True)
class Abweichung:
    kind: str
    wo: str  # "stand" oder ISO-Woche
    feld: str
    gespeichert: object
    berechnet: object

    def __str__(self):
        return f"{self.kind} {self.wo} {self.feld}: {self.gespeichert!r} -> {self.berechnet!r}"


def abweichungen(kind) -> list[Abweichung]:
    """Vergleicht die gespeicherten Stände eines Kindes mit der Neuberechnung aus der Historie,
    bezogen auf den Zeitpunkt der letzten Auswertung (``KindStand.aktualisiert_am``)."""
    name = kind.anzeigename
    stand_zeile = KindStand.objects.filter(kind=kind).first()
    zeilen = {(w.iso_jahr, w.iso_woche): w for w in Wochenauswertung.objects.filter(kind=kind)}
    if stand_zeile is None:
        if zeilen:
            return [Abweichung(name, "stand", "vorhanden", False, True)]
        return [Abweichung(name, "stand", "noch nicht ausgewertet", None, "Job ausführen")]
    a = auswertung.auswerten(kind, stand_zeile.aktualisiert_am)
    xp = auswertung.xp_je_woche(kind, a.wochen)
    ergebnis = [
        Abweichung(name, "stand", f, getattr(stand_zeile, f), v)
        for f, v in _stand_werte(a.stand).items()
        if getattr(stand_zeile, f) != v
    ]
    for i, e in enumerate(a.wochen):
        wo = str(e.woche)
        zeile = zeilen.pop((e.woche.jahr, e.woche.woche), None)
        if zeile is None:
            ergebnis.append(Abweichung(name, wo, "vorhanden", False, True))
            continue
        for f, v in _wochen_werte(e, xp.get(e.woche, 0)).items():
            if getattr(zeile, f) != v:
                ergebnis.append(Abweichung(name, wo, f, getattr(zeile, f), v))
        if (i < a.finalisiert) != (zeile.finalisiert_am is not None):
            ergebnis.append(
                Abweichung(
                    name, wo, "finalisiert", zeile.finalisiert_am is not None, i < a.finalisiert
                )
            )
    for (jahr, woche), _ in sorted(zeilen.items()):
        ergebnis.append(Abweichung(name, f"{jahr}-W{woche:02d}", "vorhanden", True, False))
    # AP22: Stand-Rang = höchster Fakt; fehlende Fakten (Bedingungen erfüllt, nie geprüft)
    rang = raenge.aktueller_rang(kind)
    if stand_zeile.rang_id != (rang.pk if rang else None):
        ergebnis.append(
            Abweichung(name, "stand", "rang", stand_zeile.rang_id, rang.pk if rang else None)
        )
    ziel = raenge.berechneter_rang(kind, aktive_wochen=a.stand.aktive_wochen_gesamt)
    if ziel is not None and rang is not None and ziel.stufe > rang.stufe:
        ergebnis.append(Abweichung(name, "stand", "rang_aufstieg_fehlt", rang.stufe, ziel.stufe))
    return ergebnis


def neu_berechnen(*, schreiben=False, jetzt=None) -> list[Abweichung]:
    """Rekonstruiert alle Stände aus der Historie und liefert die Abweichungen zum gespeicherten
    Stand. ``schreiben=True``: danach Soll-Stand speichern (ohne Ereignisse)."""
    ergebnis = []
    for kind in konten.aktive_kinder():
        ergebnis.extend(abweichungen(kind))
        if schreiben:
            with transaction.atomic():
                kind_auswerten(kind, jetzt, melden=False)
    return ergebnis


# --- Nachtragen aus Ereignissen -------------------------------------------------------------


def aktivitaeten_nachtragen() -> dict:
    """Aktivitäten aus den Ereignissen ``aufgabe.erledigt``/``aufgabe.korrigiert`` nachtragen
    (Bestand aus Phase 1, idempotent). Danach ``wochen_sicherstellen``."""
    from apps.ereignisse import selectors as ereignis_selectors

    angelegt = storniert = 0
    r = auswertung.regeln()
    with transaction.atomic():
        for e in ereignis_selectors.ereignisse_vom_typ("aufgabe.erledigt"):
            instanz = e.daten.get("instanz_id")
            if instanz is None or e.kind_id is None or not e.daten.get("bezugsdatum"):
                continue
            meldedatum = date.fromisoformat(e.daten["bezugsdatum"])
            erfasst = e.daten.get("bestaetigt_am")
            erfasst_am = datetime.fromisoformat(erfasst) if erfasst else e.zeit
            _, neu = Aktivitaet.objects.get_or_create(
                modul="aufgaben",
                referenz=str(instanz),
                defaults={
                    "kind_id": e.kind_id,
                    "datum": k.wirksames_datum(meldedatum, erfasst_am, r.puffer_stunden, r.tz),
                    "erstellt_am": erfasst_am,
                },
            )
            angelegt += neu
        for typ in ("aufgabe.korrigiert", "aufgabe.nachbessern"):
            for e in ereignis_selectors.ereignisse_vom_typ(typ):
                instanz = e.daten.get("instanz_id")
                if instanz is not None:
                    storniert += Aktivitaet.objects.filter(
                        modul="aufgaben", referenz=str(instanz), storniert=False
                    ).update(storniert=True)
    return {"angelegt": angelegt, "storniert": storniert}
