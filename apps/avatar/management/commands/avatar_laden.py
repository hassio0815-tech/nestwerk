from django.core.management.base import BaseCommand

from apps.avatar.bibliothek_db import bibliothek_laden


class Command(BaseCommand):
    help = "Themen, Slots und Baupläne aus apps/avatar/daten in die Datenbank laden."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ueberschreiben",
            action="store_true",
            help="Auch bereits vorhandene Zeilen mit dem Stand der Dateien überschreiben.",
        )

    def handle(self, *args, **opts):
        stand = bibliothek_laden(ueberschreiben=opts["ueberschreiben"])
        self.stdout.write(
            f"Slots: {stand['slots']}, Themen: {stand['themen']}, Mods: {stand['mods']} "
            "(neu/aktualisiert)"
        )
