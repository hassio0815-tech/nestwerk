from apps.kern.jobs import JobBefehl
from apps.konten import services


class Command(JobBefehl):
    help = "Löscht Anmeldeversuche nach 30 Tagen und abgelaufene Sitzungen."
    job_name = "konten_aufraeumen"

    def job(self, sperre, **optionen):
        versuche = services.alte_versuche_loeschen()
        services.abgelaufene_sitzungen_loeschen()
        return {"versuche_geloescht": versuche}
