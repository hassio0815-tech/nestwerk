"""Lesende Schnittstelle von ereignisse (Live-Version, Systemstatus)."""

from datetime import timedelta

from django.db.models import Count, Max, Min
from django.utils import timezone

from .models import Ereignis, EreignisTyp, EreignisVerarbeitung, Status, WorkerHerzschlag
from .worker import WORKER_NAME

HERZSCHLAG_MAX_ALTER = timedelta(seconds=60)


def aktuelle_version():
    """Höchste Ereignis-ID (Live-Polling, ARCHITECTURE 5.4). 0 = noch keine Ereignisse."""
    return Ereignis.objects.aggregate(v=Max("id"))["v"] or 0


def ereignistyp(slug):
    """DB-Zeile eines Ereignistyps. Unbekannt -> ``EreignisTyp.DoesNotExist``."""
    return EreignisTyp.objects.get(pk=slug)


def ereignistypen(*, nur_aktive=True):
    """Ereignistypen (ohne interne) sortiert nach Modul und Bezeichnung, für Einstellungsseiten."""
    qs = EreignisTyp.objects.exclude(zielgruppe="intern").order_by("modul", "bezeichnung")
    return list(qs.filter(aktiv=True) if nur_aktive else qs)


def ereignisse_vom_typ(typ):
    """Ereignisse eines Typs in Reihenfolge (z. B. Fakten nachtragen, spielregeln AP20)."""
    return Ereignis.objects.filter(typ_id=typ).order_by("id").iterator()


def worker_herzschlag():
    """Zeitpunkt des letzten Worker-Herzschlags oder ``None``."""
    return (
        WorkerHerzschlag.objects.filter(name=WORKER_NAME).values_list("zuletzt", flat=True).first()
    )


def worker_lebt(max_alter=HERZSCHLAG_MAX_ALTER):
    zuletzt = worker_herzschlag()
    return zuletzt is not None and timezone.now() - zuletzt <= max_alter


def systemstatus():
    """Kennzahlen für Eltern-Dashboard (Systemstatus) und Healthcheck.

    ``gesund`` = Worker lebt und nichts ist aufgegeben.
    """
    nach_status = dict(
        EreignisVerarbeitung.objects.values_list("status").annotate(n=Count("id")).order_by()
    )
    offen = EreignisVerarbeitung.objects.filter(status__in=[Status.OFFEN, Status.FEHLER])
    unverteilt = Ereignis.objects.filter(verteilt=False).aggregate(n=Count("id"), alt=Min("zeit"))
    zuletzt = worker_herzschlag()
    lebt = zuletzt is not None and timezone.now() - zuletzt <= HERZSCHLAG_MAX_ALTER
    status = {
        "unverteilt": unverteilt["n"],
        "aeltestes_unverteilt": unverteilt["alt"],
        "offen": nach_status.get(Status.OFFEN, 0),
        "fehler": nach_status.get(Status.FEHLER, 0),
        "aufgegeben": nach_status.get(Status.AUFGEGEBEN, 0),
        "ok": nach_status.get(Status.OK, 0),
        "aeltestes_offen": offen.aggregate(alt=Min("ereignis__zeit"))["alt"],
        "worker_herzschlag": zuletzt,
        "worker_lebt": lebt,
    }
    status["gesund"] = lebt and status["aufgegeben"] == 0
    return status


def fehlerhafte(limit=50):
    """Fehlerhafte und aufgegebene Verarbeitungen (neueste zuerst) für die Systemstatus-Liste."""
    return list(
        EreignisVerarbeitung.objects.filter(status__in=[Status.FEHLER, Status.AUFGEGEBEN])
        .order_by("-id")
        .values(
            "id",
            "handler",
            "status",
            "versuche",
            "naechster_versuch",
            "letzter_fehler",
            "ereignis_id",
            "ereignis__typ_id",
            "ereignis__zeit",
        )[:limit]
    )
