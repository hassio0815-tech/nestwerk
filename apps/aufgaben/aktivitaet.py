"""Anbindung an spielregeln (AP20): Bestätigte Aufgabe = Aktivität, Korrektur = Storno.

Läuft über die Hooks des Kinderablaufs (``ablauf.erledigung_hook_registrieren`` /
``storno_hook_registrieren``) in der Transaktion der Bestätigung bzw. Korrektur. aufgaben ruft
die tiefere Schicht spielregeln auf (erlaubt); spielregeln kennt aufgaben nicht.
"""

from apps.spielregeln import services as spielregeln

from . import ablauf

MODUL = "aufgaben"


def erfassen(erledigung):
    """K1: Bezugsdatum = Meldedatum; nach Wochenabschluss zählt der Tag der Bestätigung."""
    spielregeln.aktivitaet_erfassen(
        erledigung.kind,
        erledigung.bezugsdatum,
        modul=MODUL,
        referenz=erledigung.instanz.pk,
        erfasst_am=erledigung.bestaetigt_am,
    )


def stornieren(instanz, kind, von):
    spielregeln.aktivitaet_stornieren(modul=MODUL, referenz=instanz.pk)


def registrieren():
    ablauf.erledigung_hook_registrieren(erfassen)
    ablauf.storno_hook_registrieren(stornieren)
