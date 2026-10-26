from apps.aufgaben import nachweise
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Nachweis-Fotos: Dateien abgeschlossener Meldungen und verwaiste Dateien löschen."
    job_name = "nachweise_aufraeumen"

    def job(self, sperre, **optionen):
        return nachweise.aufraeumen()
