"""Einstellungen von lernen (SPEC 21.12). Startwerte per Datenmigration 0002, generisch."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "lernen.tagesziel_minuten": 20,
    "lernen.mindesttag_minuten": 5,
    "lernen.lernpunkte_tageslimit": 10,
    "lernen.freigabe_durch_eltern": True,
    "lernen.speicher_limit_mb": 500,
    "lernen.tutor_aktiv": False,
}


def einstellungen_definieren():
    definieren(
        "lernen.tagesziel_minuten",
        Typ.GANZZAHL,
        _("Tagesziel Lernzeit"),
        beschreibung=_("So viele Minuten pro Tag gelten als Ziel."),
        einheit=_("Minuten"),
        minimum=1,
        maximum=240,
    )
    definieren(
        "lernen.mindesttag_minuten",
        Typ.GANZZAHL,
        _("Mindesttag Lernzeit"),
        beschreibung=_("Ab so vielen Minuten zählt ein Tag als geübt."),
        einheit=_("Minuten"),
        minimum=1,
        maximum=120,
    )
    definieren(
        "lernen.lernpunkte_tageslimit",
        Typ.GANZZAHL,
        _("Lernpunkte pro Tag (Obergrenze)"),
        beschreibung=_("Mehr Punkte als dieser Wert gibt das Lernen pro Kind und Tag nicht."),
        einheit=_("Punkte"),
        minimum=0,
        maximum=1000,
    )
    definieren(
        "lernen.freigabe_durch_eltern",
        Typ.BOOL,
        _("Eltern geben Fragen frei"),
        beschreibung=_(
            "Ja: Fragen aus Uploads sind erst nach der Freigabe durch die Eltern nutzbar. "
            "Nein: sie sind sofort nutzbar."
        ),
    )
    definieren(
        "lernen.speicher_limit_mb",
        Typ.GANZZAHL,
        _("Speicherplatz pro Kind"),
        beschreibung=_("So viel Platz darf die Lernmappe eines Kindes höchstens belegen."),
        einheit=_("MB"),
        minimum=10,
        maximum=1_000_000,
    )
    definieren(
        "lernen.tutor_aktiv",
        Typ.BOOL,
        _("KI-Tutor aktiv"),
        beschreibung=_("Gilt für die ganze Familie. Standardmäßig aus."),
    )
