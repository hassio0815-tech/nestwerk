from django.conf import settings

from apps.ereignisse import betrieb
from apps.kern import backup
from apps.kern.jobs import JobBefehl


class Command(JobBefehl):
    help = (
        "Wiederherstellungstest: neuestes Backup in Temp-DB entpacken, integrity_check, "
        "Zeilenzahlen (Ledger gegen Live-DB). Fehler -> JobLauf 'fehler' + Ereignis."
    )
    job_name = "backup_pruefen"

    def add_arguments(self, parser):
        parser.add_argument("--db-pfad", default=None, help="Live-DB für den Ledger-Vergleich")
        parser.add_argument("--ziel", default=None, help="Standard: NESTWERK_BACKUP_ZIEL")

    def job(self, sperre, **optionen):
        return backup.pruefen(
            optionen["ziel"] or settings.BACKUP_DIR,
            jetzt=betrieb.lokal_jetzt(),
            live_db=optionen["db_pfad"] or betrieb.db_pfad(),
            ledger_tabellen=betrieb.LEDGER_TABELLEN,
            max_alter_stunden=settings.BACKUP_MAX_ALTER_STUNDEN,
        )

    def handle(self, *args, **optionen):
        try:
            super().handle(*args, **optionen)
        except Exception as exc:
            betrieb.fehler_melden(self.job_name, exc)
            raise
