from apps.aufgaben import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Erzeugt fehlende Aufgaben-Instanzen bis zum Vorlauf-Horizont (idempotent, Catch-up)."
    job_name = "aufgaben_erzeugen"

    def job(self, sperre, **optionen):
        return services.instanzen_erzeugen()
