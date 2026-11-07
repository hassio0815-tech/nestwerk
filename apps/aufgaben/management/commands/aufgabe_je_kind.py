"""Bestehende Aufgabe(n) "für alle Kinder" in je eine eigene Aufgabe pro Kind aufteilen."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.aufgaben import services
from apps.aufgaben.models import Aufgabe, AufgabenInstanz


class _Trocken(Exception):
    """Bricht die Transaktion des Probelaufs ab (nichts bleibt gespeichert)."""


class Command(BaseCommand):
    help = (
        "Teilt Aufgaben (IDs) in je eine eigene Aufgabe pro aktivem Kind auf. "
        "Schon geteilte oder nicht aktive Aufgaben werden übersprungen."
    )

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="+", type=int)
        parser.add_argument(
            "--dry-run", action="store_true", help="Nur anzeigen, was passieren würde."
        )

    def handle(self, *args, ids, dry_run=False, **opts):
        fehler = []
        for pk in ids:
            try:
                aufgabe = Aufgabe.objects.get(pk=pk)
            except Aufgabe.DoesNotExist:
                fehler.append(f"Aufgabe {pk} gibt es nicht.")
                continue
            try:
                self._teilen(aufgabe, dry_run=dry_run)
            except ValidationError as exc:
                # Schon geteilt / nicht aktiv / keine Kinder: überspringen, kein Fehler
                self.stderr.write(f"Übersprungen: {aufgabe.titel} ({pk}): {' '.join(exc.messages)}")
        if fehler:
            raise CommandError(" ".join(fehler))

    def _teilen(self, aufgabe, *, dry_run):
        vorher = AufgabenInstanz.objects.filter(aufgabe=aufgabe).count()
        try:
            with transaction.atomic():
                neue = services.je_kind_aufteilen(aufgabe)
                namen = ", ".join(f"{a.pk}→{a.zugewiesen_an.rufname}" for a in neue)
                mitgenommen = AufgabenInstanz.objects.filter(
                    aufgabe__in=[a for a in neue if a.pk != aufgabe.pk]
                ).count()
                if dry_run:
                    raise _Trocken
        except _Trocken:
            self.stdout.write(
                f"[Probelauf] {aufgabe.titel}: {namen} "
                f"({vorher} Instanzen, davon {mitgenommen} wandern zu Kopien)"
            )
            return
        self.stdout.write(f"{aufgabe.titel}: {namen}")
