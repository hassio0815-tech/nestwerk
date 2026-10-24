"""Einstellungen von spielregeln (AP20). Definition hier, Startwerte per Datenmigration 0002."""

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


def einstellungen_definieren():
    definieren(
        "spielregeln.puffer_stunden",
        Typ.GANZZAHL,
        "Wochenabschluss wartet nach Wochenende",
        beschreibung="So lange nach Sonntag 24 Uhr zählen noch bestätigte Aufgaben, die in der "
        "alten Woche gemeldet wurden. Danach ist die Woche abgeschlossen; spätere Bestätigungen "
        "zählen für die Woche der Bestätigung.",
        einheit="Stunden",
        minimum=0,
        maximum=168,
    )
    definieren(
        "spielregeln.neutral_ab_pausentagen",
        Typ.GANZZAHL,
        "Woche ohne Aufgabe ist neutral ab",
        beschreibung="Pausentage in der Woche, ab denen eine Woche ohne Aufgabe die Serie nicht "
        "bricht. Gilt rückwirkend für alle Wochen (Ränge und Abzeichen bleiben).",
        einheit="Pausentage",
        minimum=1,
        maximum=7,
    )
    definieren(
        "spielregeln.serienbonus_start",
        Typ.GANZZAHL,
        "Serienbonus ab Serie",
        beschreibung="Ab so vielen aktiven Wochen in Folge gibt es Bonus auf Aufgabenpunkte "
        "(Sonderpunkte bekommen keinen Bonus).",
        einheit="Wochen",
        minimum=1,
        maximum=52,
    )
    definieren(
        "spielregeln.serienbonus_schritt_prozent",
        Typ.GANZZAHL,
        "Serienbonus je Serienwoche",
        beschreibung="So viel Prozent mehr gibt es mit jeder weiteren Woche der Serie.",
        einheit="%",
        minimum=0,
        maximum=100,
    )
    definieren(
        "spielregeln.serienbonus_deckel_prozent",
        Typ.GANZZAHL,
        "Serienbonus höchstens",
        beschreibung="Obergrenze des Serienbonus. Der Bonus wird auf ganze Punkte aufgerundet.",
        einheit="%",
        minimum=0,
        maximum=100,
    )
