"""Einstellungen von oberflaeche (Startwert per Datenmigration)."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "oberflaeche.tablet_aktualisierung_sekunden": 10,  # ARCHITECTURE 5.4
    "oberflaeche.tablet_neuladen_stunden": 6,
}


RANKING_STARTWERTE = {"oberflaeche.ranking_modus": "schaufenster"}  # AP30
RANKING_MODI = ("schaufenster", "held", "rohpunkte")


def einstellungen_definieren():
    definieren(
        "oberflaeche.ranking_modus",
        Typ.TEXT,
        "Familien-Ranking: Ansicht",
        beschreibung="Schaufenster (Avatare mit Rang, Serie, Abzeichen), Held der Woche oder "
        "Rohpunkte. Gilt für Tablet und Kinder-Seite.",
        auswahl=RANKING_MODI,
    )
    definieren(
        "oberflaeche.tablet_aktualisierung_sekunden",
        Typ.GANZZAHL,
        "Tablet: Aktualisierung",
        beschreibung="Abstand, in dem die Tablet-Startseite sich selbst aktualisiert. "
        "Das verlängert keine Sitzung.",
        einheit="Sekunden",
        minimum=5,
        maximum=300,
    )
    definieren(
        "oberflaeche.tablet_neuladen_stunden",
        Typ.GANZZAHL,
        "Tablet: vollständiges Neuladen",
        beschreibung="Die Tablet-Startseite lädt sich in diesem Abstand komplett neu "
        "(gegen Speicherlecks im Kiosk-Browser).",
        einheit="Stunden",
        minimum=1,
        maximum=48,
    )
