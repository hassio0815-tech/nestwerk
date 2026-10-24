"""Fällige Bauaufträge fertigstellen (ARCHITECTURE 6, AP26).

Idempotent und mit Catch-up: bedingtes Update ``im_bau -> fertig`` je Mod, ``fertig_am`` =
geplanter Zeitpunkt (ein ausgefallener Lauf ändert die Wertungswoche nicht), Ereignis
``mod.fertig`` mit Schlüssel je Mod. Takt: alle 5 Minuten (deploy/crontab).
"""

from apps.avatar import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Fällige Mod-Bauaufträge fertigstellen (idempotent, Catch-up)"
    job_name = "mods_fertigstellen"

    def job(self, sperre, **optionen):
        return services.mods_fertigstellen()
