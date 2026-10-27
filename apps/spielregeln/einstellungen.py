"""Einstellungen von spielregeln (AP20). Definition hier, Startwerte per Datenmigration 0002."""

from django.utils.translation import gettext_lazy as _

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    # K1: Wochenabschluss erst nach Puffer (Mo 00:00 + 24 h = Di 00:00)
    "spielregeln.puffer_stunden": 24,
    # K5: Woche ohne Aktivität ist neutral ab so vielen Pausentagen
    "spielregeln.neutral_ab_pausentagen": 1,
    # AP21, Entscheidung 4 / SPEC 18.2: Serie 1 = 0 %, ab Serie 2 +5 % je Woche, Deckel 25 %
    "spielregeln.serienbonus_start": 2,
    "spielregeln.serienbonus_schritt_prozent": 5,
    "spielregeln.serienbonus_deckel_prozent": 25,
}


# AP30: Held der Woche (ARCHITECTURE 7.8)
HELD_STARTWERTE = {
    "spielregeln.held_basis_wochen": 4,
    "spielregeln.held_min_wochen": 2,
    "spielregeln.held_mindestbasis_punkte": 50,
}

# AP32: Prognose und Kalibrierung (ARCHITECTURE 7.9)
PROGNOSE_STARTWERTE = {
    "spielregeln.prognose_wochen": 6,
    "spielregeln.prognose_min_wochen": 3,
    "spielregeln.prognose_ziel_sondertage": 2,
    "spielregeln.prognose_kind_zeigen": True,
}


def einstellungen_definieren():
    definieren(
        "spielregeln.prognose_wochen",
        Typ.GANZZAHL,
        _("Prognose: Basis in Wochen"),
        beschreibung=_(
            "Die Prognose rechnet mit dem Durchschnitt der letzten so vielen "
            "abgeschlossenen Wochen (Pausenwochen zählen nicht)."
        ),
        einheit=_("Wochen"),
        minimum=2,
        maximum=26,
    )
    definieren(
        "spielregeln.prognose_min_wochen",
        Typ.GANZZAHL,
        _("Prognose: Mindestzahl an Wochen"),
        beschreibung=_(
            "Mit weniger abgeschlossenen Wochen gibt es keine Prognose, nur einen Hinweis."
        ),
        einheit=_("Wochen"),
        minimum=1,
        maximum=26,
    )
    definieren(
        "spielregeln.prognose_ziel_sondertage",
        Typ.GANZZAHL,
        _("Prognose: Ziel Sondertage je App-Jahr"),
        beschreibung=_("Daran misst die Eltern-Ansicht die Abweichung (Ampel)."),
        einheit=_("Sondertage"),
        minimum=1,
        maximum=12,
    )
    definieren(
        "spielregeln.prognose_kind_zeigen",
        Typ.BOOL,
        _("Kind sieht Rang-Prognose"),
        beschreibung=_(
            "Ja: Die Rang-Kachel zeigt „Nächster Rang voraussichtlich in ca. X "
            "Wochen“. Nein: keine Prognose beim Kind."
        ),
    )
    definieren(
        "spielregeln.held_basis_wochen",
        Typ.GANZZAHL,
        _("Held der Woche: Vergleich mit den letzten Wochen"),
        beschreibung=_(
            "Das eigene Wochen-Mittel aus so vielen letzten aktiven Wochen dient als "
            "Vergleich. Wer in der Woche am meisten über seinem eigenen Mittel liegt, ist Held."
        ),
        einheit=_("Wochen"),
        minimum=1,
        maximum=26,
    )
    definieren(
        "spielregeln.held_min_wochen",
        Typ.GANZZAHL,
        _("Held der Woche: Mindestwochen Historie"),
        beschreibung=_(
            "Ab so vielen aktiven Wochen zählt das echte eigene Mittel. Davor gilt die "
            "einfache Regel: Vergleich mit dem Mindestwert unten."
        ),
        einheit=_("Wochen"),
        minimum=1,
        maximum=26,
    )
    definieren(
        "spielregeln.held_mindestbasis_punkte",
        Typ.GANZZAHL,
        _("Held der Woche: Mindestwert als Vergleich"),
        beschreibung=_(
            "Das Mittel wird nach unten auf diesen Wert begrenzt, damit sehr kleine "
            "Mittelwerte keine riesigen Zuwächse ergeben."
        ),
        einheit=_("Punkte"),
        minimum=1,
        maximum=10000,
    )
    definieren(
        "spielregeln.puffer_stunden",
        Typ.GANZZAHL,
        _("Wochenabschluss wartet nach Wochenende"),
        beschreibung=_(
            "So lange nach Sonntag 24 Uhr zählen noch bestätigte Aufgaben, die in der "
            "alten Woche gemeldet wurden. Danach ist die Woche abgeschlossen; spätere "
            "Bestätigungen zählen für die Woche der Bestätigung."
        ),
        einheit=_("Stunden"),
        minimum=0,
        maximum=168,
    )
    definieren(
        "spielregeln.neutral_ab_pausentagen",
        Typ.GANZZAHL,
        _("Woche ohne Aufgabe ist neutral ab"),
        beschreibung=_(
            "Pausentage in der Woche, ab denen eine Woche ohne Aufgabe die Serie nicht "
            "bricht. Gilt rückwirkend für alle Wochen (Ränge und Abzeichen bleiben)."
        ),
        einheit=_("Pausentage"),
        minimum=1,
        maximum=7,
    )
    definieren(
        "spielregeln.serienbonus_start",
        Typ.GANZZAHL,
        _("Serienbonus ab Serie"),
        beschreibung=_(
            "Ab so vielen aktiven Wochen in Folge gibt es Bonus auf Aufgabenpunkte "
            "(Sonderpunkte bekommen keinen Bonus)."
        ),
        einheit=_("Wochen"),
        minimum=1,
        maximum=52,
    )
    definieren(
        "spielregeln.serienbonus_schritt_prozent",
        Typ.GANZZAHL,
        _("Serienbonus je Serienwoche"),
        beschreibung=_("So viel Prozent mehr gibt es mit jeder weiteren Woche der Serie."),
        einheit="%",
        minimum=0,
        maximum=100,
    )
    definieren(
        "spielregeln.serienbonus_deckel_prozent",
        Typ.GANZZAHL,
        _("Serienbonus höchstens"),
        beschreibung=_("Obergrenze des Serienbonus. Der Bonus wird auf ganze Punkte aufgerundet."),
        einheit="%",
        minimum=0,
        maximum=100,
    )
