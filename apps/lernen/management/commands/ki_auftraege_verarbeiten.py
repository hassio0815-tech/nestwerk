from apps.kern.jobs import JobBefehl
from apps.lernen import ki_warteschlange


class Command(JobBefehl):
    help = (
        "Arbeitet die KI-Warteschlange von lernen ab (ein Aufruf zur Zeit, Mindestabstand je "
        "Anbieter, Wiederholung mit Wartezeit). Ohne konfigurierte KI passiert nichts."
    )
    job_name = "ki_auftraege_verarbeiten"
    lease = ki_warteschlange.LEASE

    def job(self, sperre, **optionen):
        return ki_warteschlange.verarbeiten(sperre)
