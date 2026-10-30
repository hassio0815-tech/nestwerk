"""Start-Schnell-Knöpfe (Restmüll, Biomüll, Altglas) einmalig als Aufgaben anlegen.

Idempotent; läuft stündlich (deploy/crontab). Tut nichts, solange es keinen aktiven Elternteil
gibt oder wenn der Einmal-Merker schon gesetzt ist."""

from apps.aufgaben import schnellknopf
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Start-Schnell-Knöpfe einmalig als Aufgaben anlegen"
    job_name = "schnellknoepfe_sicherstellen"

    def job(self, sperre, **optionen):
        return {"angelegt": schnellknopf.schnellknoepfe_sicherstellen()}
