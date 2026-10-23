from apps.benachrichtigung import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Löscht gelesene Benachrichtigungen nach der Aufbewahrungszeit (Einstellung)."
    job_name = "benachrichtigungen_aufraeumen"

    def job(self, sperre, **optionen):
        return {"geloescht": services.aufraeumen()}
