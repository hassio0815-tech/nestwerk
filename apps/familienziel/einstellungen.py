"""Einstellungen von familienziel (AP29, Entscheidung 26). Startwerte per Datenmigration 0002."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "familienziel.wochenziel_punkte": 450,
    "familienziel.grossziel_serie": 4,
    "familienziel.grossziel_name": gettext_noop("Ausflug"),  # msgid, Anzeige übersetzt
    "familienziel.abstimmung_tag": 7,  # ISO-Wochentag, 7 = Sonntag
    "familienziel.abstimmung_beginn": "00:00",
    "familienziel.abstimmung_ende": "23:59",
}

WOCHENTAGE = (1, 2, 3, 4, 5, 6, 7)


def einstellungen_definieren():
    definieren(
        "familienziel.wochenziel_punkte",
        Typ.GANZZAHL,
        _("Wochenziel der Familie"),
        beschreibung=_(
            "Verdiente XP aller Kinder in einer Woche (Montag bis Sonntag). Gilt für neue "
            "Wochen; die Eltern können das Ziel einer Woche einzeln überschreiben."
        ),
        einheit=_("Punkte"),
        minimum=1,
        maximum=100000,
    )
    definieren(
        "familienziel.grossziel_serie",
        Typ.GANZZAHL,
        _("Großziel nach Wochenzielen in Folge"),
        beschreibung=_(
            "So viele erreichte Wochenziele in Folge schalten das große Ziel frei. "
            "Wochen, in denen die ganze Familie pausiert, zählen weder noch brechen sie die Folge."
        ),
        einheit=_("Wochen"),
        minimum=1,
        maximum=52,
    )
    definieren(
        "familienziel.grossziel_name",
        Typ.TEXT,
        _("Name des großen Ziels"),
        beschreibung=_(
            "Zum Beispiel Ausflug. Wird angezeigt, wenn das Großziel freigeschaltet ist."
        ),
        max_laenge=60,
    )
    definieren(
        "familienziel.abstimmung_tag",
        Typ.GANZZAHL,
        _("Abstimmung: Wochentag"),
        beschreibung=_(
            "Tag der Woche, an dem die Kinder über das Ziel der nächsten Woche abstimmen "
            "(1 = Montag … 7 = Sonntag)."
        ),
        minimum=1,
        maximum=7,
        auswahl=WOCHENTAGE,
    )
    definieren(
        "familienziel.abstimmung_beginn",
        Typ.UHRZEIT,
        _("Abstimmung: Beginn"),
        beschreibung=_("Uhrzeit, ab der die Kinder abstimmen dürfen."),
    )
    definieren(
        "familienziel.abstimmung_ende",
        Typ.UHRZEIT,
        _("Abstimmung: Ende"),
        beschreibung=_(
            "Uhrzeit, bis zu der abgestimmt werden darf (23:59 = bis Tagesende). "
            "Danach zählt das Ergebnis; bei Gleichstand entscheiden die Eltern."
        ),
    )
