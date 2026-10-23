from apps.aufgaben import services
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = "Vorwarnung an Eltern vor Fensterende; nicht übernommene Instanzen verfallen still."
    job_name = "verfall_pruefen"

    def job(self, sperre, **optionen):
        return services.verfall_pruefen()
