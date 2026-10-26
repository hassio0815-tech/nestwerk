"""Wochenauswertung und Spielstand je Kind auf den Soll-Stand bringen (ARCHITECTURE 6, AP20).

Idempotent und mit Catch-up: rechnet alle vergangenen Wochen seit Go-live aus der Historie,
schließt Wochen nach dem Puffer ab (``spielregeln.puffer_stunden``) und meldet jeden Abschluss
genau einmal (Ereignis-Schlüssel). Takt: stündlich (deploy/crontab), Haupttermin Di 00:10.
"""

from apps.kern.jobs import JobBefehl
from apps.spielregeln import services


class Command(JobBefehl):
    help = "Wochenauswertungen, Serien und Spielstände sicherstellen (idempotent, Catch-up)"
    job_name = "wochen_sicherstellen"

    def job(self, sperre, **optionen):
        return services.wochen_sicherstellen()
