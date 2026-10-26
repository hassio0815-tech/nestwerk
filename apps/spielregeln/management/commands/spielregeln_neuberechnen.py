"""Alle Stände aus der Historie neu berechnen und mit dem gespeicherten Stand vergleichen
(ARCHITECTURE 7.1). Ohne Optionen nur prüfen: Exit-Code 1 bei Abweichungen.

- ``--schreiben``: Abweichungen beheben (Soll-Stand speichern, ohne Ereignisse).
- ``--nachtragen``: vorher Aktivitäten aus ``aufgabe.erledigt``/``aufgabe.korrigiert``
  nachtragen (Bestand aus Phase 1, idempotent).
"""

from django.core.management.base import BaseCommand, CommandError

from apps.spielregeln import services


class Command(BaseCommand):
    help = "Spielregeln-Stände aus der Historie neu berechnen und abgleichen"

    def add_arguments(self, parser):
        parser.add_argument("--schreiben", action="store_true", help="Abweichungen beheben")
        parser.add_argument(
            "--nachtragen", action="store_true", help="Aktivitäten aus Ereignissen nachtragen"
        )

    def handle(self, *args, schreiben=False, nachtragen=False, **optionen):
        if nachtragen:
            ergebnis = services.aktivitaeten_nachtragen()
            self.stdout.write(f"Nachgetragen: {ergebnis}")
        abweichungen = services.neu_berechnen(schreiben=schreiben)
        for a in abweichungen:
            self.stdout.write(str(a))
        if not abweichungen:
            self.stdout.write("Neuberechnung = gespeicherter Stand (keine Abweichung).")
        elif schreiben:
            self.stdout.write(f"{len(abweichungen)} Abweichung(en) behoben.")
        else:
            raise CommandError(f"{len(abweichungen)} Abweichung(en); --schreiben behebt sie.")
