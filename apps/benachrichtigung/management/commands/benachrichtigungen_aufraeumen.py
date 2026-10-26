from apps.benachrichtigung import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = (
        "Aufbewahrung (B-15): alte Benachrichtigungen, Zustellungen, verarbeitete Ereignisse und "
        "Job-Läufe löschen (Fristen sind Einstellungen; Ledger und Audit bleiben)."
    )
    job_name = "benachrichtigungen_aufraeumen"

    def job(self, sperre, **optionen):
        return services.aufbewahrung()
