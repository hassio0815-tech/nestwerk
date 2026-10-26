"""Instanz-Erzeugung, Verfall und Reservierungsablauf (AP11, ARCHITECTURE 6).

Öffentlich über ``aufgaben.services``. Alle Jobs arbeiten den Soll-Zustand bis ``jetzt`` ab
(Catch-up) und sind idempotent:

- Erzeugung: ``unique(aufgabe, plan_datum)`` + Teil-Unique "max. 1 laufende ungebundene".
- Verfall/Ablauf: bedingtes ``UPDATE ... WHERE status = alt``; Ereignis mit ``schluessel``.
- Vorwarnung/Erinnerung: ``vorwarnung_am``/``erinnert_am IS NULL`` + Ereignis-Schlüssel.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.ereignisse import services as ereignisse
from apps.kern import audit, einstellungen, zeit

from . import events, faelligkeit, wiederholung, zustand
from .models import (
    LAUFENDE_STATUS,
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Interesse,
    InteresseStatus,
    Status,
)

# Rückblick für ungebundene Aufgaben (nur der jüngste fällige Termin zählt, kein Stapel)
_RUECKBLICK_MIN_TAGE = 7


# --- Erzeugung --------------------------------------------------------------------------------


def _start_ersatz(aufgabe, tz) -> date:
    """Fehlt ``start_datum``, gilt der Anlagetag der Aufgabe."""
    return zeit.heute(aufgabe.erstellt_am, tz)


def _anlegen(aufgabe, plan_datum, fenster_start, fenster_ende) -> AufgabenInstanz | None:
    """Legt eine Instanz an; Konflikt mit einem Eindeutigkeitsschlüssel -> ``None``."""
    try:
        with transaction.atomic():
            return AufgabenInstanz.objects.create(
                aufgabe=aufgabe,
                plan_datum=plan_datum,
                faellig_am=plan_datum,
                fenster_start=fenster_start,
                fenster_ende=fenster_ende,
                titel_snapshot=aufgabe.titel,
                punkte_snapshot=aufgabe.punkte,
                freigabeart_snapshot=aufgabe.freigabeart,
            )
    except IntegrityError:
        return None


def _zeitgebunden_erzeugen(aufgabe, *, jetzt, heute, horizont, tz) -> int:
    plan = aufgabe.plan
    bestehende = aufgabe.instanzen.all()
    if plan.art == wiederholung.EINMALIG and bestehende.exists():
        return 0
    # Mehrtägige Fenster können vor heute begonnen haben und noch laufen
    von = heute - timedelta(days=(plan.fenster_tage or 0) + 1)
    bis = heute + timedelta(days=horizont)
    tage = faelligkeit.termine(plan, von, bis, start=_start_ersatz(aufgabe, tz))
    vorhanden = set(bestehende.filter(plan_datum__in=tage).values_list("plan_datum", flat=True))
    neu = 0
    for tag in tage:
        if tag in vorhanden:
            continue
        beginn, ende = faelligkeit.fenster(plan, tag, tz)
        if ende <= jetzt:
            continue  # Fenster schon vorbei (z. B. nach Ausfall): nichts nachträglich anlegen
        if _anlegen(aufgabe, tag, beginn, ende):
            neu += 1
    return neu


def _ungebunden_erzeugen(aufgabe, *, heute, tz) -> int:
    """K9: höchstens eine laufende Instanz; die nächste erst zum nächsten Termin danach."""
    plan = aufgabe.plan
    bestehende = aufgabe.instanzen.all()
    if bestehende.filter(status__in=LAUFENDE_STATUS, fenster_ende__isnull=True).exists():
        return 0
    if plan.art == wiederholung.EINMALIG:
        if bestehende.exists():
            return 0
        tag = plan.start_datum
        if tag is not None and tag > heute:
            return 0
        beginn = zeit.tag_beginn(tag or heute, tz)
        return 1 if _anlegen(aufgabe, tag, beginn, None) else 0

    start = plan.start_datum or _start_ersatz(aufgabe, tz)
    rueckblick = max(_RUECKBLICK_MIN_TAGE, plan.intervall_tage or 0)
    von = max(start, heute - timedelta(days=rueckblick))
    letzte = bestehende.exclude(plan_datum__isnull=True).order_by("-plan_datum").first()
    if letzte is not None:
        grenze = letzte.plan_datum
        if letzte.abgeschlossen_am is not None:
            grenze = max(grenze, zeit.heute(letzte.abgeschlossen_am, tz))
        von = max(von, grenze + timedelta(days=1))
    tage = faelligkeit.termine(plan, von, heute, start=start)
    if not tage:
        return 0
    tag = tage[-1]  # nur der jüngste fällige Termin (kein Stapel nach Ausfall)
    return 1 if _anlegen(aufgabe, tag, zeit.tag_beginn(tag, tz), None) else 0


def instanzen_erzeugen(*, jetzt: datetime | None = None, aufgaben=None) -> dict:
    """Erzeugt fehlende Instanzen aller aktiven Aufgaben (oder der übergebenen).

    Zeitgebunden: alle Plan-Tage bis ``heute + aufgaben.instanz_horizont_tage``, deren Fenster
    noch nicht vorbei ist. Ungebunden: höchstens eine laufende, erst ab Fälligkeit.
    Pausierte und beendete Aufgaben erzeugen nichts.
    """
    jetzt = jetzt or zeit.jetzt()
    tz = zeit.zeitzone()
    heute = zeit.heute(jetzt, tz)
    horizont = einstellungen.wert("aufgaben.instanz_horizont_tage")
    if aufgaben is None:
        aufgaben = Aufgabe.objects.all()
    aufgaben = aufgaben.filter(status=Status.AKTIV)
    zaehler = {"aufgaben": 0, "neu": 0}
    for aufgabe in aufgaben.iterator():
        zaehler["aufgaben"] += 1
        if aufgabe.zeitgebunden:
            zaehler["neu"] += _zeitgebunden_erzeugen(
                aufgabe, jetzt=jetzt, heute=heute, horizont=horizont, tz=tz
            )
        else:
            zaehler["neu"] += _ungebunden_erzeugen(aufgabe, heute=heute, tz=tz)
    return zaehler


def offene_entfernen(aufgabe, *, verschobene_behalten=False) -> int:
    """Entfernt freie (``offen``) Instanzen, z. B. nach Plan-Änderung, Pause oder Ende.

    Frei = gerade kein Kind dran (reserviert/Konflikt/gemeldet bleiben immer). Der nächste
    Erzeugungslauf legt (falls aktiv) neue Instanzen mit aktuellem Plan und Snapshot an.

    ``verschobene_behalten`` (Plan-Änderung, nicht Pause/Ende): im Wochenplan manuell
    verschobene Instanzen (``faellig_am != plan_datum``) sind eine bewusste Eltern-Entscheidung
    für einen bestimmten Tag und bleiben, solange die Aufgabe aktiv ist und die Art (mit/ohne
    Zeitfenster) passt. Sie bekommen den neuen Snapshot (Titel, Punkte, Freigabeart) und das
    Zeitfenster des neuen Plans an ihrem Tag. Ihr ``plan_datum`` blockiert über
    ``unique(aufgabe, plan_datum)`` die Neuerzeugung dieses Plan-Tags (kein Doppel).
    """
    offene = AufgabenInstanz.objects.filter(aufgabe=aufgabe, status=InstanzStatus.OFFEN)
    if verschobene_behalten and aufgabe.status == Status.AKTIV:
        for instanz in offene.exclude(plan_datum__isnull=True):
            if instanz.verschoben and instanz.zeitgebunden == aufgabe.zeitgebunden:
                _an_plan_anpassen(instanz, aufgabe)
                offene = offene.exclude(pk=instanz.pk)
    anzahl, _ = offene.delete()
    return anzahl


def _an_plan_anpassen(instanz, aufgabe) -> None:
    felder = {
        "titel_snapshot": aufgabe.titel,
        "punkte_snapshot": aufgabe.punkte,
        "freigabeart_snapshot": aufgabe.freigabeart,
    }
    tag = instanz.faellig_am
    if aufgabe.zeitgebunden and tag is not None:
        beginn, ende = faelligkeit.fenster(aufgabe.plan, tag)
        if (beginn, ende) != (instanz.fenster_start, instanz.fenster_ende):
            felder.update(fenster_start=beginn, fenster_ende=ende, vorwarnung_am=None)
    AufgabenInstanz.objects.filter(pk=instanz.pk, status=InstanzStatus.OFFEN).update(**felder)


# --- Verschieben (Wochenplan, AP14) -----------------------------------------------------------

VERSCHIEBBAR = (InstanzStatus.OFFEN, InstanzStatus.KONFLIKT, InstanzStatus.RESERVIERT)


@transaction.atomic
def instanz_verschieben(instanz, neues_datum: date, *, von, sortierung=None) -> AufgabenInstanz:
    """Setzt das wirksame Datum (``faellig_am``) neu; ``plan_datum`` bleibt (Idempotenz).

    Das Zeitfenster wird aus dem Plan der Aufgabe für den neuen Tag berechnet. Eine bereits
    gesendete Vorwarnung wird zurückgesetzt; bei zeitgebundener Reservierung folgt
    ``reserviert_bis`` dem neuen Fensterende.
    """
    instanz = AufgabenInstanz.objects.select_related("aufgabe").get(pk=instanz.pk)
    if instanz.status not in VERSCHIEBBAR:
        raise ValueError(f"Instanz im Status '{instanz.status}' kann nicht verschoben werden")
    alt = instanz.faellig_am
    felder = {"faellig_am": neues_datum}
    if instanz.zeitgebunden:
        beginn, ende = faelligkeit.fenster(instanz.aufgabe.plan, neues_datum)
        felder.update(fenster_start=beginn, fenster_ende=ende, vorwarnung_am=None)
        if instanz.status == InstanzStatus.RESERVIERT:
            felder.update(reserviert_bis=ende, erinnert_am=None)
    else:
        felder["fenster_start"] = zeit.tag_beginn(neues_datum)
    if sortierung is not None:
        felder["sortierung"] = sortierung
    aktualisiert = AufgabenInstanz.objects.filter(pk=instanz.pk, status=instanz.status).update(
        **felder
    )
    if not aktualisiert:
        raise ValueError("Instanz wurde zwischenzeitlich geändert")
    instanz.refresh_from_db()
    audit.protokollieren(
        "aufgabe.instanz_verschoben",
        akteur=von,
        objekt=instanz,
        details={"titel": instanz.titel_snapshot, "von": str(alt), "nach": str(neues_datum)},
    )
    return instanz


# --- Verfall + Vorwarnung ---------------------------------------------------------------------


def _daten(instanz) -> dict:
    return {
        "instanz_id": instanz.pk,
        "aufgabe_id": instanz.aufgabe_id,
        "aufgabe": instanz.titel_snapshot,
        "faellig_am": instanz.faellig_am.isoformat() if instanz.faellig_am else None,
        "fenster_ende": instanz.fenster_ende.isoformat() if instanz.fenster_ende else None,
    }


# Noch niemandem gehörend: verfallen am Fensterende (Konflikt = Eltern haben nicht zugeteilt)
NICHT_UEBERNOMMEN_AUS = (InstanzStatus.OFFEN, InstanzStatus.KONFLIKT)


def verfall_pruefen(*, jetzt: datetime | None = None) -> dict:
    """Zeitgebundene, nicht übernommene Instanzen (``offen`` oder ``konflikt``) verfallen nach
    Fensterende still (``nicht_uebernommen``, Ereignis an Eltern); Konflikt-Interessen werden
    ``abgelaufen``. Vorwarnung an Eltern X h vorher, genau einmal.
    """
    jetzt = jetzt or zeit.jetzt()
    zaehler = {"verfallen": 0, "vorgewarnt": 0}

    faellige = AufgabenInstanz.objects.filter(
        status__in=NICHT_UEBERNOMMEN_AUS, fenster_ende__lte=jetzt
    )
    for pk, status in list(faellige.values_list("pk", "status")):
        with transaction.atomic():
            zustand.pruefen(status, InstanzStatus.NICHT_UEBERNOMMEN)
            if not faellige.filter(pk=pk, status=status).update(
                status=InstanzStatus.NICHT_UEBERNOMMEN, abgeschlossen_am=jetzt
            ):
                continue
            Interesse.objects.filter(instanz_id=pk, status=InteresseStatus.AKTIV).update(
                status=InteresseStatus.ABGELAUFEN, geaendert_am=jetzt
            )
            instanz = AufgabenInstanz.objects.get(pk=pk)
            ereignisse.veroeffentlichen(
                events.NICHT_UEBERNOMMEN,
                daten=_daten(instanz),
                schluessel=f"{events.NICHT_UEBERNOMMEN}:{pk}",
            )
            zaehler["verfallen"] += 1

    stunden = einstellungen.wert("aufgaben.vorwarnung_stunden_vorher")
    if stunden <= 0:
        return zaehler
    bald = AufgabenInstanz.objects.filter(
        status__in=NICHT_UEBERNOMMEN_AUS,
        vorwarnung_am__isnull=True,
        fenster_ende__gt=jetzt,
        fenster_ende__lte=jetzt + timedelta(hours=stunden),
    )
    for pk in list(bald.values_list("pk", flat=True)):
        with transaction.atomic():
            if not bald.filter(pk=pk).update(vorwarnung_am=jetzt):
                continue
            instanz = AufgabenInstanz.objects.get(pk=pk)
            ereignisse.veroeffentlichen(
                events.VERFALL_VORWARNUNG,
                daten=_daten(instanz),
                schluessel=f"{events.VERFALL_VORWARNUNG}:{pk}:{instanz.fenster_ende.isoformat()}",
            )
            zaehler["vorgewarnt"] += 1
    return zaehler


# --- Reservierung -----------------------------------------------------------------------------

_ablauf_hooks: list[Callable] = []


def reservierungsablauf_hook_registrieren(funktion: Callable) -> Callable:
    """``funktion(instanz, kind)`` läuft in der Ablauf-Transaktion (z. B. Interesse ->
    ``abgelaufen``). ``instanz`` ist bereits ``offen`` bzw. ``nicht_uebernommen``."""
    if funktion not in _ablauf_hooks:
        _ablauf_hooks.append(funktion)
    return funktion


def reservierung_frist(instanz, ab: datetime) -> datetime:
    """Ende einer Reservierung (E22): zeitgebunden = Fensterende, sonst ``ab`` + 48 h (Einst.).

    K11: ``ab`` ist der Reservierungszeitpunkt bei einem Interessenten bzw. der Zeitpunkt der
    Zuteilung durch die Eltern bei Mehrfachinteresse (die Uhr startet erst dann).
    """
    if instanz.fenster_ende is not None:
        return instanz.fenster_ende
    return ab + timedelta(hours=einstellungen.wert("aufgaben.reservierung_stunden"))


def reservierungen_pruefen(*, jetzt: datetime | None = None) -> dict:
    """Erinnerung ans Kind X h vor Ablauf (genau einmal je Reservierung); nach Ablauf wird die
    Instanz wieder ``offen`` (ohne Strafe) und die Eltern werden informiert.

    Zeitgebunden (Frist = Fensterende): wieder frei wäre sinnlos, die Instanz wird direkt
    ``nicht_uebernommen``. Die Eltern bekommen genau **eine** Meldung
    (``reservierung.abgelaufen``), kein zusätzliches ``aufgabe.nicht_uebernommen``.
    """
    jetzt = jetzt or zeit.jetzt()
    zaehler = {"abgelaufen": 0, "erinnert": 0}

    abgelaufen = AufgabenInstanz.objects.filter(
        status=InstanzStatus.RESERVIERT, reserviert_bis__lte=jetzt
    )
    zeilen = abgelaufen.values_list("pk", "kind_id", "reserviert_bis", "fenster_ende")
    for pk, kind_id, bis, fenster_ende in list(zeilen):
        fenster_vorbei = fenster_ende is not None and fenster_ende <= jetzt
        if fenster_vorbei:
            ziel = {"status": InstanzStatus.NICHT_UEBERNOMMEN, "abgeschlossen_am": jetzt}
        else:
            ziel = {"status": InstanzStatus.OFFEN, "kind": None}
        zustand.pruefen(InstanzStatus.RESERVIERT, ziel["status"])
        with transaction.atomic():
            if not abgelaufen.filter(pk=pk, kind_id=kind_id, reserviert_bis=bis).update(
                reserviert_bis=None, erinnert_am=None, **ziel
            ):
                continue
            instanz = AufgabenInstanz.objects.get(pk=pk)
            kind = _benutzer(kind_id)
            ereignisse.veroeffentlichen(
                events.RESERVIERUNG_ABGELAUFEN,
                kind=kind,
                daten=_daten(instanz)
                | {"kind_id": str(kind_id), "nicht_uebernommen": fenster_vorbei},
                schluessel=f"{events.RESERVIERUNG_ABGELAUFEN}:{pk}:{bis.isoformat()}",
            )
            for hook in _ablauf_hooks:
                hook(instanz, kind)
            zaehler["abgelaufen"] += 1

    stunden = einstellungen.wert("aufgaben.erinnerung_kind_stunden_vorher")
    if stunden <= 0:
        return zaehler
    bald = AufgabenInstanz.objects.filter(
        status=InstanzStatus.RESERVIERT,
        erinnert_am__isnull=True,
        reserviert_bis__gt=jetzt,
        reserviert_bis__lte=jetzt + timedelta(hours=stunden),
    )
    for pk, kind_id, bis in list(bald.values_list("pk", "kind_id", "reserviert_bis")):
        with transaction.atomic():
            if not bald.filter(pk=pk, kind_id=kind_id).update(erinnert_am=jetzt):
                continue
            instanz = AufgabenInstanz.objects.get(pk=pk)
            ereignisse.veroeffentlichen(
                events.RESERVIERUNG_ERINNERUNG,
                kind=_benutzer(kind_id),
                daten=_daten(instanz) | {"reserviert_bis": bis.isoformat()},
                schluessel=f"{events.RESERVIERUNG_ERINNERUNG}:{pk}:{bis.isoformat()}",
            )
            zaehler["erinnert"] += 1
    return zaehler


def _benutzer(pk):
    return None if pk is None else get_user_model().objects.get(pk=pk)
