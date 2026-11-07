from datetime import timedelta

from apps.kern.jobs import JobBefehl
from apps.lernen import eltern_hinweise


class Command(JobBefehl):
    help = (
        "Prüft die Ausnahmen für die Eltern: Material wartet, Kind länger still, Fehlerhäufung, "
        "Prüfung bald. Jedes Ereignis entsteht je Zeitraum nur einmal (idempotent)."
    )
    job_name = "lernen_eltern_hinweise"
    lease = timedelta(minutes=10)

    def job(self, sperre, **optionen):
        return {"neu": eltern_hinweise.hinweise_pruefen()}
