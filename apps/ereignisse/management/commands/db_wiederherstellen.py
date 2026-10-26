from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ereignisse import betrieb
from apps.kern import backup


class Command(BaseCommand):
    help = (
        "Spielt ein Backup als Live-DB ein (Rollback/Restore). Nur mit gestoppten Diensten! "
        "Die alte DB bleibt als *.vor-restore-<zeit> erhalten."
    )

    def add_arguments(self, parser):
        parser.add_argument("datei", help="Backup-Datei (*.sqlite3.gz) oder 'neuestes'")
        parser.add_argument("--db-pfad", default=None)
        parser.add_argument("--ziel", default=None, help="Backup-Ordner für 'neuestes'")
        parser.add_argument("--grund", choices=backup.GRUENDE, default=None)

    def handle(self, *args, **optionen):
        datei = optionen["datei"]
        if datei == "neuestes":
            from django.conf import settings

            kandidaten = [
                b
                for b in backup.auflisten(optionen["ziel"] or settings.BACKUP_DIR)
                if optionen["grund"] in (None, b.grund)
            ]
            if not kandidaten:
                raise CommandError("Kein passendes Backup gefunden")
            datei = kandidaten[0].pfad
        try:
            beiseite = backup.live_wiederherstellen(
                Path(datei), optionen["db_pfad"] or betrieb.db_pfad(), jetzt=betrieb.lokal_jetzt()
            )
        except backup.BackupFehler as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Wiederhergestellt aus {Path(datei).name}; alte DB: {beiseite or '-'}")
