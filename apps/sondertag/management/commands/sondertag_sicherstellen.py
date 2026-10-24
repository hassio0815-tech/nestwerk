"""Catch-up (AP27): Sondertag-Ansprüche zu erreichten Meilensteinen ohne Anspruch anlegen und
Einlösedaten aller Kinder neu berechnen. Idempotent."""

from django.core.management.base import BaseCommand

from apps.konten import selectors as konten
from apps.sondertag import services


class Command(BaseCommand):
    help = "Sondertag-Ansprüche nachholen und Einlösedaten neu berechnen (idempotent)."

    def handle(self, *args, **options):
        neu = services.nachholen()
        for kind in konten.aktive_kinder():
            services.neu_berechnen(kind)
        self.stdout.write(f"sondertag: {neu} Ansprüche nachgeholt")
