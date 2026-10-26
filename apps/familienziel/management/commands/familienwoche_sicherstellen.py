"""Familienwochen, Abstimmung und Großziel auf den Soll-Stand bringen (AP29, ARCHITECTURE 6).

Idempotent mit Catch-up. Takt: alle 15 Minuten (deploy/crontab)."""

from apps.familienziel import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Familienwoche anlegen, Abstimmung schließen, Wochen auswerten, Großziel prüfen"
    job_name = "familienwoche_sicherstellen"

    def job(self, sperre, **optionen):
        return services.sicherstellen()
