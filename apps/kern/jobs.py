"""Job-Sperren und Job-Läufe für Scheduler-Jobs (ARCHITECTURE 6).

- ``sperre_holen(name)``: Lease (Standard 10 min). Abgelaufene Sperren dürfen übernommen werden.
- ``ausfuehren(name, funktion)``: Sperre holen, ``JobLauf`` protokollieren, Sperre freigeben.
  Läuft der Job schon, entsteht ein Lauf mit Status ``uebersprungen``.
- ``JobBefehl``: Basis für Management-Commands (``manage.py <job>``).

Die Sperre verhindert Parallel-Läufe; Idempotenz der Fachlogik (Unique-Constraints,
bedingte Updates) bleibt trotzdem Pflicht.
"""

import os
import socket
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import JobLauf, JobSperre, JobStatus

LEASE_STANDARD = timedelta(minutes=10)


def _inhaber():
    """Host + PID + Zufallsteil (eindeutig je Sperr-Erwerb), max. 80 Zeichen."""
    return f"{socket.gethostname()[:50]}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class Sperre:
    """Gehaltene Job-Sperre."""

    def __init__(self, name, inhaber):
        self.name = name
        self.inhaber = inhaber

    def _eigene(self):
        return JobSperre.objects.filter(name=self.name, inhaber=self.inhaber)

    def verlaengern(self, lease=LEASE_STANDARD):
        """Verlängert die Lease. ``False`` = Sperre gehört nicht mehr uns (übernommen)."""
        return self._eigene().update(gehalten_bis=timezone.now() + lease) == 1

    def freigeben(self):
        """Gibt die Sperre frei, falls sie noch uns gehört."""
        self._eigene().delete()

    def __repr__(self):
        return f"<Sperre {self.name} {self.inhaber}>"


def sperre_holen(name, *, lease=LEASE_STANDARD):
    """Versucht die Sperre ``name`` zu holen. ``None`` = von jemand anderem gehalten."""
    jetzt = timezone.now()
    inhaber = _inhaber()
    with transaction.atomic():
        uebernommen = JobSperre.objects.filter(name=name, gehalten_bis__lte=jetzt).update(
            inhaber=inhaber, gehalten_bis=jetzt + lease
        )
        if not uebernommen:
            try:
                with transaction.atomic():
                    JobSperre.objects.create(name=name, inhaber=inhaber, gehalten_bis=jetzt + lease)
            except IntegrityError:
                return None
    return Sperre(name, inhaber)


@contextmanager
def sperre(name, *, lease=LEASE_STANDARD):
    """``with sperre("x") as s:`` – ``s`` ist ``None``, wenn die Sperre belegt ist."""
    s = sperre_holen(name, lease=lease)
    try:
        yield s
    finally:
        if s is not None:
            s.freigeben()


def ausfuehren(name, funktion, *, lease=LEASE_STANDARD):
    """Führt ``funktion(sperre) -> dict | None`` unter Sperre aus und gibt den ``JobLauf`` zurück.

    Das zurückgegebene dict (Zähler o. Ä.) landet in ``JobLauf.info``. Fehler werden als
    Status ``fehler`` protokolliert und weitergereicht (Exit-Code != 0 für den Scheduler).
    """
    s = sperre_holen(name, lease=lease)
    if s is None:
        halter = JobSperre.objects.filter(name=name).values_list("inhaber", flat=True).first()
        return JobLauf.objects.create(
            name=name,
            status=JobStatus.UEBERSPRUNGEN,
            beendet_am=timezone.now(),
            info={"grund": "gesperrt", "inhaber": halter or ""},
        )
    lauf = JobLauf.objects.create(name=name, status=JobStatus.LAEUFT)
    try:
        info = funktion(s) or {}
        if not isinstance(info, dict):
            raise TypeError(f"Job {name} muss ein dict oder None liefern")
    except Exception as exc:
        lauf.status = JobStatus.FEHLER
        lauf.info = {"fehler": f"{type(exc).__name__}: {exc}"[:500]}
        raise
    else:
        lauf.status = JobStatus.OK
        lauf.info = info
    finally:
        lauf.beendet_am = timezone.now()
        lauf.save(update_fields=["status", "info", "beendet_am"])
        s.freigeben()
    return lauf


def letzter_lauf(name):
    """Jüngster ``JobLauf`` eines Jobs oder ``None`` (Systemstatus im Dashboard)."""
    return JobLauf.objects.filter(name=name).order_by("-gestartet_am", "-id").first()


class JobBefehl(BaseCommand):
    """Basis für Scheduler-Commands. Unterklasse setzt ``job_name`` und implementiert ``job``."""

    job_name = None
    lease = LEASE_STANDARD

    def job(self, sperre, **optionen):
        raise NotImplementedError

    def handle(self, *args, **optionen):
        lauf = ausfuehren(self.job_name, lambda s: self.job(s, **optionen), lease=self.lease)
        self.stdout.write(f"{self.job_name}: {lauf.status} {lauf.info}")


def laeufe_aufraeumen(tage, *, jetzt=None) -> int:
    """Aufbewahrung (B-15): beendete Job-Läufe älter als ``tage`` löschen (laufende bleiben)."""
    grenze = (jetzt or timezone.now()) - timedelta(days=tage)
    anzahl, _ = (
        JobLauf.objects.filter(gestartet_am__lt=grenze).exclude(status=JobStatus.LAEUFT).delete()
    )
    return anzahl
