from datetime import timedelta

from apps.kern.jobs import JobBefehl
from apps.lernen import tutor_services


class Command(JobBefehl):
    help = (
        "Löscht Tutor-Gespräche ohne Aktivität seit der eingestellten Aufbewahrungsfrist "
        "(lernen.tutor_aufbewahrung_tage). Ohne alte Gespräche passiert nichts."
    )
    job_name = "tutor_aufraeumen"
    lease = timedelta(minutes=10)

    def job(self, sperre, **optionen):
        return tutor_services.aufraeumen()
