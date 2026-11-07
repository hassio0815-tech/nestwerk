from datetime import timedelta

from apps.kern import zeit
from apps.kern.jobs import JobBefehl
from apps.lernen import digest


class Command(JobBefehl):
    help = (
        "Sendet den Wochen-Digest an die Eltern, wenn der eingestellte Wochentag und die Uhrzeit "
        "erreicht sind. Pro Woche nur einmal (idempotent), Läufe davor und danach tun nichts."
    )
    job_name = "lernen_digest"
    lease = timedelta(minutes=5)

    def job(self, sperre, **optionen):
        jetzt = zeit.jetzt()
        return {"gesendet": int(digest.faellig(jetzt) and digest.senden(jetzt))}
