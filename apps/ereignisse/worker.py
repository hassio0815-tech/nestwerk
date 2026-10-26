"""Outbox-Worker (ARCHITECTURE 3.1, 5.1, 6).

Ablauf je Runde:
1. ``verteilen``: unverteilte Ereignisse -> je asynchronem Handler eine ``EreignisVerarbeitung``
   (``unique(ereignis, handler)``, Konflikte werden ignoriert) und ``verteilt = True``.
2. ``verarbeiten``: fällige Verarbeitungen einzeln. Statuswechsel (bedingtes UPDATE) und
   Handler laufen in **einer** Transaktion: Erfolg = beides committet; Fehler oder Absturz =
   beides zurückgerollt. Damit ist jeder Handler genau einmal wirksam, auch bei Neustart oder
   zwei Workern (SQLite IMMEDIATE serialisiert, der zweite findet ``status = ok`` vor).
3. Fehler: ``versuche + 1``, Backoff ``min(max, basis * 2^(versuche-1))``; ab
   ``ereignisse.max_versuche`` Status ``aufgegeben`` (Systemstatus).
"""

import logging
import os
import socket
import traceback
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.kern import einstellungen
from apps.kern.registry import UnbekannterEintrag

from . import registry
from .models import Ereignis, EreignisVerarbeitung, Status, WorkerHerzschlag

logger = logging.getLogger("nestwerk.ereignisse")

WORKER_NAME = "ereignisse_worker"
OFFENE_STATUS = (Status.OFFEN, Status.FEHLER)
FEHLER_MAX_ZEICHEN = 4000


def inhaber():
    return f"{socket.gethostname()[:50]}:{os.getpid()}"


def herzschlag(name=WORKER_NAME):
    WorkerHerzschlag.objects.update_or_create(
        name=name, defaults={"inhaber": inhaber(), "zuletzt": timezone.now()}
    )


def verteilen(stapel=100):
    """Legt Verarbeitungen für unverteilte Ereignisse an. Gibt die Anzahl Ereignisse zurück."""
    with transaction.atomic():
        ereignisse = list(
            Ereignis.objects.filter(verteilt=False)
            .order_by("id")
            .values_list("id", "typ_id")[:stapel]
        )
        if not ereignisse:
            return 0
        jetzt = timezone.now()
        neue = [
            EreignisVerarbeitung(ereignis_id=eid, handler=h.name, naechster_versuch=jetzt)
            for eid, typ in ereignisse
            for h in registry.handler_fuer(typ, synchron=False)
        ]
        EreignisVerarbeitung.objects.bulk_create(neue, ignore_conflicts=True)
        Ereignis.objects.filter(id__in=[eid for eid, _ in ereignisse]).update(verteilt=True)
    return len(ereignisse)


def verarbeiten(stapel=50):
    """Arbeitet fällige Verarbeitungen ab. Gibt ``{"ok": n, "fehler": m}`` zurück."""
    faellig = list(
        EreignisVerarbeitung.objects.filter(
            status__in=OFFENE_STATUS, naechster_versuch__lte=timezone.now()
        )
        .order_by("naechster_versuch", "id")
        .values_list("id", flat=True)[:stapel]
    )
    zaehler = {"ok": 0, "fehler": 0}
    for vid in faellig:
        ergebnis = verarbeitung_ausfuehren(vid)
        if ergebnis in zaehler:
            zaehler[ergebnis] += 1
    return zaehler


def verarbeitung_ausfuehren(vid):
    """Führt eine Verarbeitung aus. Rückgabe ``"ok"``, ``"fehler"`` oder ``"uebersprungen"``
    (schon erledigt oder von einem anderen Worker übernommen)."""
    kopf = EreignisVerarbeitung.objects.filter(pk=vid).values("handler", "ereignis__typ_id").first()
    if kopf is None:
        return "uebersprungen"
    try:
        handler = registry.handler(kopf["ereignis__typ_id"], kopf["handler"])
    except UnbekannterEintrag as exc:
        _fehler_vermerken(vid, f"Handler nicht registriert: {exc}")
        return "fehler"
    try:
        with transaction.atomic():
            jetzt = timezone.now()
            geholt = EreignisVerarbeitung.objects.filter(
                pk=vid, status__in=OFFENE_STATUS, naechster_versuch__lte=jetzt
            ).update(
                status=Status.OK, versuche=F("versuche") + 1, erledigt_am=jetzt, letzter_fehler=""
            )
            if not geholt:
                return "uebersprungen"
            ereignis = EreignisVerarbeitung.objects.select_related("ereignis").get(pk=vid).ereignis
            handler.funktion(ereignis)
    except Exception as exc:
        logger.exception("Ereignis-Handler fehlgeschlagen (Verarbeitung %s)", vid)
        _fehler_vermerken(vid, "".join(traceback.format_exception(exc)))
        return "fehler"
    return "ok"


def _fehler_vermerken(vid, text):
    werte = einstellungen.werte(
        "ereignisse.max_versuche",
        "ereignisse.backoff_basis_sekunden",
        "ereignisse.backoff_max_sekunden",
    )
    with transaction.atomic():
        v = EreignisVerarbeitung.objects.filter(pk=vid, status__in=OFFENE_STATUS).first()
        if v is None:
            return
        versuche = v.versuche + 1
        if versuche >= werte["ereignisse.max_versuche"]:
            status, naechster = Status.AUFGEGEBEN, None
        else:
            sekunden = min(
                werte["ereignisse.backoff_max_sekunden"],
                werte["ereignisse.backoff_basis_sekunden"] * 2 ** (versuche - 1),
            )
            status, naechster = Status.FEHLER, timezone.now() + timedelta(seconds=sekunden)
        # Bedingt auf den gelesenen Stand: ein paralleler Worker zählt nicht doppelt
        EreignisVerarbeitung.objects.filter(pk=vid, status=v.status, versuche=v.versuche).update(
            status=status,
            versuche=versuche,
            naechster_versuch=naechster,
            letzter_fehler=text[-FEHLER_MAX_ZEICHEN:],
        )


def nachlaeufe_ausfuehren():
    """Ruft die registrierten Nachläufe auf; gibt die Summe ihrer Rückgaben zurück."""
    summe = 0
    for name, funktion in registry.nachlaeufe():
        try:
            summe += int(funktion() or 0)
        except Exception:
            logger.exception("Worker-Nachlauf '%s' fehlgeschlagen", name)
    return summe


def runde(stapel=50):
    """Eine Worker-Runde: Herzschlag, verteilen, verarbeiten, Nachläufe."""
    herzschlag()
    verteilt = verteilen(stapel=stapel * 2)
    zaehler = verarbeiten(stapel=stapel)
    return {"verteilt": verteilt, **zaehler, "nachlauf": nachlaeufe_ausfuehren()}
