"""Warteschlange für KI-Arbeit im Hintergrund (SPEC 21.6, ARCHITECTURE 6).

- ``auftrag_einreihen``: idempotent über den Schlüssel (derselbe Schlüssel = derselbe Auftrag).
- ``verarbeiten``: läuft im Job ``ki_auftraege_verarbeiten`` unter der Job-Sperre aus ``kern``.
  Dadurch läuft höchstens ein Aufruf zur Zeit (Parallelität 1, also auch je Anbieter); zusätzlich
  gilt ein Mindestabstand je Anbieter. Fehler führen zu Wiederholung mit wachsender Wartezeit
  (Basis x 4^n), nach ``lernen.ki_max_versuche`` Versuchen zum Status ``fehler``.
- Jeder Statuswechsel ist ein bedingtes ``UPDATE ... WHERE status = alt``.
- Fachliche Handler meldet das jeweilige Modul mit ``handler_registrieren`` an. Ein Handler
  bekommt den ``KiAuftrag`` und ruft ``ki_services.ki_aufruf`` selbst auf.
- Die Warteschlange speichert nie Inhalte, nur Verweise.
"""

import logging
from collections import Counter
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from apps.kern.einstellungen import wert

from . import ki_selectors
from .ki import KiFehler
from .models import KiAufgabe, KiAuftrag, KiAuftragStatus

log = logging.getLogger("nestwerk.lernen.ki")

LEASE = timedelta(minutes=15)
BACKOFF_MAX = timedelta(hours=6)
# Fehlerarten, die einen Anbieter für den Rest des Laufs ausschließen (er ist offenbar down oder
# abgelehnt): schont GPU, Kosten und die Warteschlange.
_ANBIETER_STOPP = {"auth", "verbindung", "zeitueberschreitung", "konfiguration", "limit"}

_HANDLER = {}


def handler_registrieren(aufgabe, funktion):
    """Meldet den Handler ``funktion(auftrag)`` für eine Aufgabe an (ersetzt einen früheren)."""
    if aufgabe not in KiAufgabe.values:
        raise ValueError(f"Unbekannte KI-Aufgabe '{aufgabe}'")
    _HANDLER[aufgabe] = funktion


def handler_entfernen(aufgabe):
    _HANDLER.pop(aufgabe, None)


def auftrag_einreihen(aufgabe, schluessel, *, kind=None, eingabe_verweis=""):
    """Legt einen Auftrag an. Gibt ``(auftrag, neu)`` zurück; gleicher Schlüssel = kein
    zweiter Auftrag."""
    if aufgabe not in KiAufgabe.values:
        raise ValueError(f"Unbekannte KI-Aufgabe '{aufgabe}'")
    schluessel = (schluessel or "").strip()
    if not schluessel or len(schluessel) > 120:
        raise ValueError("Der Idempotenz-Schlüssel muss 1 bis 120 Zeichen lang sein")
    try:
        with transaction.atomic():
            return KiAuftrag.objects.get_or_create(
                schluessel=schluessel,
                defaults={
                    "aufgabe": aufgabe,
                    "kind": kind,
                    "eingabe_verweis": eingabe_verweis[:200],
                },
            )
    except IntegrityError:  # paralleler Anleger war schneller
        return KiAuftrag.objects.get(schluessel=schluessel), False


def _backoff(versuche):
    sekunden = wert("lernen.ki_backoff_sekunden") * 4 ** max(versuche - 1, 0)
    return min(timedelta(seconds=sekunden), BACKOFF_MAX)


def _fehlschlag(auftrag, art, *, wiederholbar, jetzt):
    """Nach einem Fehlversuch zurück in die Warteschlange (Backoff) oder endgültig ``fehler``."""
    endgueltig = not wiederholbar or auftrag.versuche >= wert("lernen.ki_max_versuche")
    felder = {"fehler_art": art, "beendet_am": jetzt}
    if endgueltig:
        felder.update(status=KiAuftragStatus.FEHLER)
    else:
        felder.update(
            status=KiAuftragStatus.WARTEND, naechster_versuch_am=jetzt + _backoff(auftrag.versuche)
        )
    return KiAuftrag.objects.filter(pk=auftrag.pk, status=KiAuftragStatus.LAEUFT).update(**felder)


def _haengende_zuruecksetzen(jetzt, zaehler):
    """Aufträge, die über ``LEASE`` lang "läuft" zeigen (Absturz), zählen als Fehlversuch."""
    for auftrag in KiAuftrag.objects.filter(
        status=KiAuftragStatus.LAEUFT, gestartet_am__lt=jetzt - LEASE
    ):
        if _fehlschlag(auftrag, "abgebrochen", wiederholbar=True, jetzt=jetzt):
            zaehler["zurueckgesetzt"] += 1


def _letzter_abschluss(anbieter):
    return KiAuftrag.objects.filter(anbieter=anbieter).aggregate(m=Max("beendet_am"))["m"]


def _zu_frueh(anbieter, letzte, jetzt):
    abstand = timedelta(seconds=wert("lernen.ki_mindestabstand_sekunden"))
    if anbieter.pk not in letzte:
        letzte[anbieter.pk] = _letzter_abschluss(anbieter)
    zuletzt = letzte[anbieter.pk]
    return zuletzt is not None and jetzt < zuletzt + abstand


def verarbeiten(sperre=None, *, jetzt=None):
    """Bearbeitet fällige Aufträge nacheinander. ``sperre`` (Job-Sperre) wird vor jedem Auftrag
    verlängert; ist sie verloren, endet der Lauf. Gibt Zähler für ``JobLauf.info`` zurück."""

    def uhr():
        return jetzt or timezone.now()

    zaehler = Counter()
    _haengende_zuruecksetzen(uhr(), zaehler)
    faellig = list(
        KiAuftrag.objects.filter(status=KiAuftragStatus.WARTEND)
        .filter(Q(naechster_versuch_am__isnull=True) | Q(naechster_versuch_am__lte=uhr()))
        .values_list("pk", flat=True)
    )
    grenze = wert("lernen.ki_auftraege_pro_lauf")
    gestoppt, letzte = set(), {}
    for pk in faellig:
        if zaehler["bearbeitet"] >= grenze:
            break
        if sperre is not None and not sperre.verlaengern(LEASE):
            zaehler["sperre_verloren"] += 1
            break
        auftrag = KiAuftrag.objects.filter(pk=pk, status=KiAuftragStatus.WARTEND).first()
        if auftrag is None:
            continue
        anbieter = ki_selectors.zuordnung_fuer(auftrag.aufgabe)
        if anbieter is not None and anbieter.pk in gestoppt:
            zaehler["uebersprungen"] += 1
            continue
        bereit = ki_selectors.status_von(anbieter) is ki_selectors.KiStatus.BEREIT
        if bereit and _zu_frueh(anbieter, letzte, uhr()):
            zaehler["uebersprungen"] += 1
            continue
        if not _beanspruchen(auftrag, anbieter if bereit else None, uhr()):
            continue  # ein anderer Lauf war schneller
        zaehler["bearbeitet"] += 1
        if not bereit:  # KI für diese Aufgabe aus: kein Aufruf, kein Wiederholen
            _fehlschlag(auftrag, "aus", wiederholbar=False, jetzt=uhr())
            zaehler["fehler"] += 1
            continue
        _ausfuehren(auftrag, anbieter, gestoppt, letzte, zaehler, uhr)
    return dict(zaehler)


def _beanspruchen(auftrag, anbieter, jetzt):
    """wartend -> läuft (bedingt); ``False``, wenn der Auftrag nicht mehr wartend ist."""
    gezaehlt = KiAuftrag.objects.filter(pk=auftrag.pk, status=KiAuftragStatus.WARTEND).update(
        status=KiAuftragStatus.LAEUFT,
        versuche=F("versuche") + 1,
        gestartet_am=jetzt,
        naechster_versuch_am=None,
        anbieter=anbieter,
    )
    if gezaehlt:
        auftrag.refresh_from_db()
    return bool(gezaehlt)


def _ausfuehren(auftrag, anbieter, gestoppt, letzte, zaehler, uhr):
    handler = _HANDLER.get(auftrag.aufgabe)
    fehler_art, wiederholbar = "", False
    if handler is None:
        fehler_art = "kein_handler"
    else:
        try:
            handler(auftrag)
        except KiFehler as exc:
            fehler_art, wiederholbar = exc.art, exc.wiederholbar
        except Exception as exc:
            # Nur der Typname ins Log: Meldungen könnten Inhalte der Kinder enthalten.
            log.warning("ki_auftrag %s handler_fehler %s", auftrag.pk, type(exc).__name__)
            fehler_art = "intern"
    letzte[anbieter.pk] = uhr()
    if not fehler_art:
        KiAuftrag.objects.filter(pk=auftrag.pk, status=KiAuftragStatus.LAEUFT).update(
            status=KiAuftragStatus.FERTIG, fehler_art="", beendet_am=uhr()
        )
        zaehler["fertig"] += 1
        return
    _fehlschlag(auftrag, fehler_art, wiederholbar=wiederholbar, jetzt=uhr())
    zaehler[
        "wiederholt"
        if wiederholbar and auftrag.versuche < wert("lernen.ki_max_versuche")
        else "fehler"
    ] += 1
    if fehler_art in _ANBIETER_STOPP:
        gestoppt.add(anbieter.pk)
