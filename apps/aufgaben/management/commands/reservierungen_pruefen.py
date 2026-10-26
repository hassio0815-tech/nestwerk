from apps.aufgaben import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Erinnerung ans Kind vor Reservierungsablauf; abgelaufene Reservierungen freigeben."
    job_name = "reservierungen_pruefen"

    def job(self, sperre, **optionen):
        return services.reservierungen_pruefen()
