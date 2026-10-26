"""Einstellungen von familienziel (AP29, Entscheidung 26). Startwerte per Datenmigration 0002."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "familienziel.wochenziel_punkte": 450,
    "familienziel.grossziel_serie": 4,
    "familienziel.grossziel_name": "Ausflug",
    "familienziel.abstimmung_tag": 7,  # ISO-Wochentag, 7 = Sonntag
    "familienziel.abstimmung_beginn": "00:00",
    "familienziel.abstimmung_ende": "23:59",
}

WOCHENTAGE = (1, 2, 3, 4, 5, 6, 7)


def einstellungen_definieren():
    definieren(
        "familienziel.wochenziel_punkte",
        Typ.GANZZAHL,
        "Wochenziel der Familie",
        beschreibung="Verdiente XP aller Kinder in einer Woche (Montag bis Sonntag). Gilt für neue "
        "Wochen; die Eltern können das Ziel einer Woche einzeln überschreiben.",
        einheit="Punkte",
        minimum=1,
        maximum=100000,
    )
    definieren(
        "familienziel.grossziel_serie",
        Typ.GANZZAHL,
        "Großziel nach Wochenzielen in Folge",
        beschreibung="So viele erreichte Wochenziele in Folge schalten das große Ziel frei. "
        "Wochen, in denen die ganze Familie pausiert, zählen weder noch brechen sie die Folge.",
        einheit="Wochen",
        minimum=1,
        maximum=52,
    )
    definieren(
        "familienziel.grossziel_name",
        Typ.TEXT,
        "Name des großen Ziels",
        beschreibung="Zum Beispiel Ausflug. Wird angezeigt, wenn das Großziel freigeschaltet ist.",
        max_laenge=60,
    )
    definieren(
        "familienziel.abstimmung_tag",
        Typ.GANZZAHL,
        "Abstimmung: Wochentag",
        beschreibung="Tag der Woche, an dem die Kinder über das Ziel der nächsten Woche abstimmen "
        "(1 = Montag … 7 = Sonntag).",
        minimum=1,
        maximum=7,
        auswahl=WOCHENTAGE,
    )
    definieren(
        "familienziel.abstimmung_beginn",
        Typ.UHRZEIT,
        "Abstimmung: Beginn",
        beschreibung="Uhrzeit, ab der die Kinder abstimmen dürfen.",
    )
    definieren(
        "familienziel.abstimmung_ende",
        Typ.UHRZEIT,
        "Abstimmung: Ende",
        beschreibung="Uhrzeit, bis zu der abgestimmt werden darf (23:59 = bis Tagesende). "
        "Danach zählt das Ergebnis; bei Gleichstand entscheiden die Eltern.",
    )
