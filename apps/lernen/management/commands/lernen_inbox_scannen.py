from datetime import timedelta

from apps.kern.jobs import JobBefehl
from apps.lernen import material_services


class Command(JobBefehl):
    help = (
        "Übernimmt neue, stabile Dateien aus dem Ordner inbox der Kinder (z. B. vom NAS) in die "
        "Lernmappe und gleicht Material mit der KI-Warteschlange ab. Ohne neue Dateien passiert "
        "nichts."
    )
    job_name = "lernen_inbox_scannen"
    lease = timedelta(minutes=10)

    def job(self, sperre, **optionen):
        ergebnis = material_services.inbox_scannen()
        ergebnis.update({f"ki_{k}": v for k, v in material_services.wartende_einreihen().items()})
        return ergebnis
