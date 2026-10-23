"""Einstellungen von spielregeln (AP20). Definition hier, Startwerte per Datenmigration 0002."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    # K1: Wochenabschluss erst nach Puffer (Mo 00:00 + 24 h = Di 00:00)
    "spielregeln.puffer_stunden": 24,
    # K5: Woche ohne Aktivität ist neutral ab so vielen Pausentagen
    "spielregeln.neutral_ab_pausentagen": 1,
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
