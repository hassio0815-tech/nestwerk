from django.conf import settings
from django.core.management.base import CommandError

from apps.ereignisse import betrieb
from apps.kern import backup
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = (
        "Konsistente SQLite-Sicherung (Backup-API, integrity_check, gzip) mit Rotation. "
        "Ohne --grund: täglicher Job (Sperre, JobLauf, Fehler-Ereignis)."
    )
    job_name = "db_sichern"

    def add_arguments(self, parser):
        parser.add_argument("--grund", choices=backup.GRUENDE, default="taeglich")
        parser.add_argument("--db-pfad", default=None, help="Standard: aktuelle Django-DB")
        parser.add_argument("--ziel", default=None, help="Standard: NESTWERK_BACKUP_ZIEL")

    def job(self, sperre, **optionen):
        grund = optionen["grund"]
        ziel = optionen["ziel"] or settings.BACKUP_DIR
        datei = backup.sichern(
            optionen["db_pfad"] or betrieb.db_pfad(),
            ziel,
            jetzt=betrieb.lokal_jetzt(),
            grund=grund,
        )
        geloescht = backup.rotieren(ziel, betrieb.regeln())
        if datei is None:
            return {"datei": "", "uebersprungen": "heute schon gesichert", "rotiert": geloescht}
        return {"datei": datei.name, "bytes": datei.stat().st_size, "rotiert": geloescht}

    def handle(self, *args, **optionen):
        if optionen["grund"] != "taeglich":
            # Update-/Handsicherung: kein Job. Funktioniert auch, wenn die Job-Tabellen
            # (noch) fehlen, z. B. vor einer Migration.
            try:
                info = self.job(None, **optionen)
            except backup.BackupFehler as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"db_sichern: {info}")
            return
        try:
            super().handle(*args, **optionen)
        except Exception as exc:
            betrieb.fehler_melden(self.job_name, exc)
            raise
