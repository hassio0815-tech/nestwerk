"""Einstellungen von sondertag (AP27, DATA_MODEL 15.2). Startwerte per Datenmigration 0002."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "sondertag.max_pro_appjahr": 2,
    "sondertag.mindestabstand_tage": 150,
    "sondertag.wunsch_vor_einloesbar_erlaubt": True,
    "sondertag.wunsch_max_zeichen": 300,
}


def einstellungen_definieren():
    definieren(
        "sondertag.max_pro_appjahr",
        Typ.GANZZAHL,
        "Sondertage pro App-Jahr",
        beschreibung="Höchstens so viele Sondertage je Kind und App-Jahr (das App-Jahr beginnt "
        "am Go-live-Datum). Früher verdiente Sondertage warten, bis wieder Platz ist.",
        einheit="Sondertage",
        minimum=1,
        maximum=12,
    )
    definieren(
        "sondertag.mindestabstand_tage",
        Typ.GANZZAHL,
        "Mindestabstand zwischen Sondertagen",
        beschreibung="So viele Tage müssen zwischen zwei Sondertagen eines Kindes liegen. "
        "Bezug ist das Datum, an dem ihr den Wunsch angenommen habt (korrigierbar).",
        einheit="Tage",
        minimum=0,
        maximum=365,
    )
    definieren(
        "sondertag.wunsch_vor_einloesbar_erlaubt",
        Typ.BOOL,
        "Wunsch schon vor dem Einlösedatum",
        beschreibung="Ja: Das Kind darf sich sofort nach dem Verdienen etwas wünschen; "
        "annehmen könnt ihr den Wunsch erst ab dem Einlösedatum.",
    )
    definieren(
        "sondertag.wunsch_max_zeichen",
        Typ.GANZZAHL,
        "Länge des Sondertag-Wunschs",
        beschreibung="So viele Zeichen darf der Wunsch des Kindes höchstens haben.",
        einheit="Zeichen",
        minimum=20,
        maximum=1000,
    )
