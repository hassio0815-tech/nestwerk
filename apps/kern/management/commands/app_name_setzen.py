from django.core.management.base import BaseCommand, CommandError

from apps.kern import einstellungen


class Command(BaseCommand):
    help = "Setzt den Anzeigenamen der App (Einstellung allgemein.anzeigename, mit Audit-Eintrag)."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Neuer Name, z. B. Nestwerk (max. 40 Zeichen)")

    def handle(self, *args, name, **optionen):
        name = name.strip()
        if not name:
            raise CommandError("Der Name darf nicht leer sein.")
        try:
            einstellungen.setzen("allgemein.anzeigename", name, akteur=None)
        except einstellungen.EinstellungFehler as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"App-Name gesetzt: {name}")
