"""Einstellungen von oberflaeche (Startwert per Datenmigration)."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "oberflaeche.tablet_aktualisierung_sekunden": 10,  # ARCHITECTURE 5.4
    "oberflaeche.tablet_neuladen_stunden": 6,
}


RANKING_STARTWERTE = {"oberflaeche.ranking_modus": "schaufenster"}  # AP30
RANKING_MODI = ("schaufenster", "held", "rohpunkte")

EIGENE_SPRUECHE_STARTWERTE = {"oberflaeche.eigene_sprueche": []}  # Wechseltext der Startseite
EIGENER_SPRUCH_MAX = 120


def einstellungen_definieren():
    definieren(
        "oberflaeche.eigene_sprueche",
        Typ.LISTE,
        _("Eigene Sprüche für die Startseite"),
        beschreibung=_(
            "Ein Spruch pro Zeile. Sie wechseln auf der Startseite mit den eingebauten "
            "Sprüchen, Weisheiten und Fakten ab (in jeder Sprache gleich)."
        ),
        element_typ=Typ.TEXT,
        max_laenge=EIGENER_SPRUCH_MAX,
    )
    definieren(
        "oberflaeche.ranking_modus",
        Typ.TEXT,
        _("Familien-Ranking: Ansicht"),
        beschreibung=_(
            "Schaufenster (Avatare mit Rang, Serie, Abzeichen), Held der Woche oder "
            "Rohpunkte. Gilt für Tablet und Kinder-Seite."
        ),
        auswahl=RANKING_MODI,
    )
    definieren(
        "oberflaeche.tablet_aktualisierung_sekunden",
        Typ.GANZZAHL,
        _("Tablet: Aktualisierung"),
        beschreibung=_(
            "Abstand, in dem die Tablet-Startseite sich selbst aktualisiert. "
            "Das verlängert keine Sitzung."
        ),
        einheit=_("Sekunden"),
        minimum=5,
        maximum=300,
    )
    definieren(
        "oberflaeche.tablet_neuladen_stunden",
        Typ.GANZZAHL,
        _("Tablet: vollständiges Neuladen"),
        beschreibung=_(
            "Die Tablet-Startseite lädt sich in diesem Abstand komplett neu "
            "(gegen Speicherlecks im Kiosk-Browser)."
        ),
        einheit=_("Stunden"),
        minimum=1,
        maximum=48,
    )
