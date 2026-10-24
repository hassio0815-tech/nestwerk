"""Catch-up (AP27, Review AP31): Sondertag-Ansprüche zu erreichten Meilensteinen ohne Anspruch
anlegen, Einlösedaten aller Kinder neu berechnen und "jetzt einlösbar" genau einmal melden.
Idempotent; läuft stündlich (deploy/crontab)."""

from apps.kern.jobs import JobBefehl
from apps.konten import selectors as konten
from apps.sondertag import services


class Command(JobBefehl):
    help = "Sondertag-Ansprüche nachholen, Einlösedaten neu berechnen, einlösbar melden."
    job_name = "sondertag_sicherstellen"

    def job(self, sperre, **optionen):
        neu = services.nachholen()
        for kind in konten.aktive_kinder():
            services.neu_berechnen(kind)
        return {"nachgeholt": neu, "einloesbar_gemeldet": services.einloesbar_melden()}
