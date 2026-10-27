"""Einstellungen von sondertag (AP27, DATA_MODEL 15.2). Startwerte per Datenmigration 0002."""

from django.utils.translation import gettext_lazy as _

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
        _("Sondertage pro App-Jahr"),
        beschreibung=_(
            "Höchstens so viele Sondertage je Kind und App-Jahr (das App-Jahr beginnt "
            "am Go-live-Datum). Früher verdiente Sondertage warten, bis wieder Platz ist."
        ),
        einheit=_("Sondertage"),
        minimum=1,
        maximum=12,
    )
    definieren(
        "sondertag.mindestabstand_tage",
        Typ.GANZZAHL,
        _("Mindestabstand zwischen Sondertagen"),
        beschreibung=_(
            "So viele Tage müssen zwischen zwei Sondertagen eines Kindes liegen. "
            "Bezug ist das Datum, an dem ihr den Wunsch angenommen habt (korrigierbar)."
        ),
        einheit=_("Tage"),
        minimum=0,
        maximum=365,
    )
    definieren(
        "sondertag.wunsch_vor_einloesbar_erlaubt",
        Typ.BOOL,
        _("Wunsch schon vor dem Einlösedatum"),
        beschreibung=_(
            "Ja: Das Kind darf sich sofort nach dem Verdienen etwas wünschen; "
            "annehmen könnt ihr den Wunsch erst ab dem Einlösedatum."
        ),
    )
    definieren(
        "sondertag.wunsch_max_zeichen",
        Typ.GANZZAHL,
        _("Länge des Sondertag-Wunschs"),
        beschreibung=_("So viele Zeichen darf der Wunsch des Kindes höchstens haben."),
        einheit=_("Zeichen"),
        minimum=20,
        maximum=1000,
    )
