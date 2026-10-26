"""Dauerprozess des worker-Containers: ``manage.py ereignisse_worker`` (ARCHITECTURE 3.1).

Endlosschleife mit Polling (Standard 2 s). Fehler einer Runde (z. B. ``database is locked``)
werden geloggt, die Schleife läuft weiter. SIGTERM/SIGINT beenden nach der laufenden Runde.
"""

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

from apps.ereignisse import worker

logger = logging.getLogger("nestwerk.ereignisse")


def _arbeit(ergebnis):
    return any(ergebnis.get(k) for k in ("verteilt", "ok", "fehler", "nachlauf"))


class Command(BaseCommand):
    help = "Outbox-Worker: verteilt Ereignisse und führt Handler mit Retries aus."

    def add_arguments(self, parser):
        parser.add_argument("--takt", type=float, default=2.0, help="Sekunden zwischen Runden")
        parser.add_argument("--stapel", type=int, default=50, help="Verarbeitungen je Runde")
        parser.add_argument(
            "--einmal",
            action="store_true",
            help="Abarbeiten, bis nichts Fälliges mehr da ist, dann beenden",
        )

    def handle(self, *args, takt, stapel, einmal, **optionen):
        self._stopp = False
        if not einmal:
            signal.signal(signal.SIGTERM, self._beenden)
            signal.signal(signal.SIGINT, self._beenden)
            self.stdout.write(f"ereignisse_worker gestartet ({worker.inhaber()}, Takt {takt} s)")
        while not self._stopp:
            if not connection.in_atomic_block:  # in Tests läuft alles in einer Transaktion
                close_old_connections()
            try:
                ergebnis = worker.runde(stapel=stapel)
            except Exception:
                logger.exception("ereignisse_worker: Runde fehlgeschlagen")
                if einmal:
                    raise
                ergebnis = None
            if einmal:
                if not _arbeit(ergebnis):
                    break
                continue
            if ergebnis and _arbeit(ergebnis):
                logger.info("ereignisse_worker: %s", ergebnis)
                continue  # Rückstand sofort weiter abarbeiten
            self._schlafen(takt)
        self.stdout.write("ereignisse_worker beendet")

    def _beenden(self, signum, frame):
        self._stopp = True

    def _schlafen(self, sekunden):
        ende = time.monotonic() + sekunden
        while not self._stopp and time.monotonic() < ende:
            time.sleep(min(0.2, sekunden))
