"""Anbindung an spielregeln (AP20/AP21): Bestätigte Aufgabe = Aktivität + Serienbonus,
Korrektur = Storno (der Bonus wird in ``ablauf.korrigieren`` mit gegengebucht).

Läuft über die Hooks des Kinderablaufs (``ablauf.erledigung_hook_registrieren`` /
``storno_hook_registrieren``) in der Transaktion der Bestätigung bzw. Korrektur. aufgaben ruft
die tiefere Schicht spielregeln auf (erlaubt); spielregeln kennt aufgaben nicht.
"""

from apps.spielregeln import services as spielregeln

from . import ablauf

MODUL = "aufgaben"


def serienbonus_schluessel(instanz_pk) -> str:
    return f"aufgabe:{instanz_pk}:serienbonus"


def erfassen(erledigung):
    """K1: Bezugsdatum = Meldedatum; nach Wochenabschluss zählt der Tag der Bestätigung."""
    spielregeln.aktivitaet_erfassen(
        erledigung.kind,
        erledigung.bezugsdatum,
        modul=MODUL,
        referenz=erledigung.instanz.pk,
        erfasst_am=erledigung.bestaetigt_am,
    )


def serienbonus(erledigung):
    """AP21: Bonus nur auf die Aufgabenpunkte (Sonderpunkte nie), gleiche Transaktion."""
    spielregeln.serienbonus_buchen(
        erledigung.kind,
        basispunkte=erledigung.punkte,
        meldedatum=erledigung.bezugsdatum,
        erfasst_am=erledigung.bestaetigt_am,
        schluessel=serienbonus_schluessel(erledigung.instanz.pk),
        quelle_modul=MODUL,
        referenz=erledigung.instanz,
        von=erledigung.von,
    )


def stornieren(instanz, kind, von):
    spielregeln.aktivitaet_stornieren(modul=MODUL, referenz=instanz.pk)


def registrieren():
    ablauf.erledigung_hook_registrieren(erfassen)
    ablauf.erledigung_hook_registrieren(serienbonus)
    ablauf.storno_hook_registrieren(stornieren)
