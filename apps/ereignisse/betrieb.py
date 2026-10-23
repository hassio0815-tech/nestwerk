"""Verdrahtung der Backup-Commands (AP18): Einstellungen, Fehler-Ereignis."""

import logging
from datetime import datetime

from django.conf import settings
from django.db import transaction

from apps.kern import backup

from . import events, services

logger = logging.getLogger(__name__)

LEDGER_TABELLEN = ("punkte_buchung",)


def db_pfad():
    return settings.DATABASES["default"]["NAME"]


def regeln():
    return backup.Rotation(
        taeglich=settings.BACKUP_TAEGLICH,
        woechentlich=settings.BACKUP_WOECHENTLICH,
        monatlich=settings.BACKUP_MONATLICH,
        update_behalten=settings.BACKUP_UPDATE_BEHALTEN,
    )


def lokal_jetzt():
    """Aktuelle Serverzeit, naiv (Container-TZ = Europa/Berlin). Bewusst ohne DB-Einstellung:
    Backups müssen auch laufen, wenn die Datenbank selbst das Problem ist."""
    return datetime.now()


def fehler_melden(job, exc):
    """Ereignis für die Eltern, höchstens eines je Job und Tag (Schlüssel)."""
    try:
        with transaction.atomic():
            services.veroeffentlichen(
                events.BACKUP_FEHLER,
                daten={"job": job, "fehler": f"{type(exc).__name__}: {exc}"[:300]},
                schluessel=f"{events.BACKUP_FEHLER}:{job}:{lokal_jetzt():%Y-%m-%d}",
            )
    except Exception:  # noqa: BLE001 - der Original-Fehler bleibt maßgeblich
        logger.exception("Backup-Fehler-Ereignis konnte nicht veröffentlicht werden")
