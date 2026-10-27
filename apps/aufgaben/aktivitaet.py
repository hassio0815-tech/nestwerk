"""Anbindung an spielregeln (AP20/AP21): Bestätigte Aufgabe = Aktivität + Serienbonus,
Korrektur = Storno (der Bonus wird in ``ablauf.korrigieren`` mit gegengebucht).

Läuft über die Hooks des Kinderablaufs (``ablauf.erledigung_hook_registrieren`` /
``storno_hook_registrieren``) in der Transaktion der Bestätigung bzw. Korrektur. aufgaben ruft
die tiefere Schicht spielregeln auf (erlaubt); spielregeln kennt aufgaben nicht.
"""

from apps.spielregeln import services as spielregeln

from . import ablauf, schluessel

MODUL = "aufgaben"


def serienbonus_schluessel(instanz_pk, anzahl=0) -> str:
    return schluessel.buchung(instanz_pk, "serienbonus", anzahl)


def erfassen(erledigung):
    """K1: Bezugsdatum = Meldedatum; nach Wochenabschluss zählt der Tag der Bestätigung."""
    spielregeln.aktivitaet_erfassen(
        erledigung.kind,
        erledigung.bezugsdatum,
        modul=MODUL,
        referenz=schluessel.aktivitaet(
            erledigung.instanz.pk, erledigung.instanz.nachbessern_anzahl
        ),
        erfasst_am=erledigung.bestaetigt_am,
    )


def serienbonus(erledigung):
    """AP21: Bonus nur auf die Aufgabenpunkte (Sonderpunkte nie), gleiche Transaktion."""
    spielregeln.serienbonus_buchen(
        erledigung.kind,
        basispunkte=erledigung.punkte,
        meldedatum=erledigung.bezugsdatum,
        erfasst_am=erledigung.bestaetigt_am,
        schluessel=serienbonus_schluessel(
            erledigung.instanz.pk, erledigung.instanz.nachbessern_anzahl
        ),
        quelle_modul=MODUL,
        referenz=erledigung.instanz,
        von=erledigung.von,
    )


def stornieren(instanz, kind, von):
    spielregeln.aktivitaet_stornieren(
        modul=MODUL, referenz=schluessel.aktivitaet(instanz.pk, instanz.nachbessern_anzahl)
    )


def registrieren():
    ablauf.erledigung_hook_registrieren(erfassen)
    ablauf.erledigung_hook_registrieren(serienbonus)
    ablauf.storno_hook_registrieren(stornieren)
