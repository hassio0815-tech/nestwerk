"""Bestehende Aufgabe(n) "für alle Kinder" in je eine eigene Aufgabe pro Kind aufteilen."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.aufgaben import services
from apps.aufgaben.models import Aufgabe


class Command(BaseCommand):
    help = "Teilt Aufgaben (IDs) in je eine eigene Aufgabe pro aktivem Kind auf."

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="+", type=int)

    def handle(self, *args, ids, **opts):
        for pk in ids:
            try:
                aufgabe = Aufgabe.objects.get(pk=pk)
                neue = services.je_kind_aufteilen(aufgabe)
            except Aufgabe.DoesNotExist as exc:
                raise CommandError(f"Aufgabe {pk} gibt es nicht.") from exc
            except ValidationError as exc:
                raise CommandError(f"Aufgabe {pk}: {' '.join(exc.messages)}") from exc
            namen = ", ".join(f"{a.pk}→{a.zugewiesen_an.rufname}" for a in neue)
            self.stdout.write(f"{aufgabe.titel}: {namen}")
