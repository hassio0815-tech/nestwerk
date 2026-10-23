"""Einstellungen von aufgaben (DATA_MODEL 15.2). Definition hier, Startwerte per Datenmigration."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    "aufgaben.instanz_horizont_tage": 14,
    "aufgaben.vorwarnung_stunden_vorher": 3,
    "aufgaben.reservierung_stunden": 48,
    "aufgaben.erinnerung_kind_stunden_vorher": 6,
}


def einstellungen_definieren():
    definieren(
        "aufgaben.instanz_horizont_tage",
        Typ.GANZZAHL,
        "Vorlauf für Aufgaben mit Zeitfenster",
        beschreibung="So viele Tage im Voraus werden Termine mit Zeitfenster angelegt.",
        einheit="Tage",
        minimum=1,
        maximum=90,
    )
    definieren(
        "aufgaben.vorwarnung_stunden_vorher",
        Typ.GANZZAHL,
        "Vorwarnung an Eltern vor 'nicht übernommen'",
        beschreibung="Stunden vor Fensterende, wenn noch kein Kind die Aufgabe übernommen hat. "
        "0 = keine Vorwarnung.",
        einheit="Stunden",
        minimum=0,
        maximum=72,
    )
    definieren(
        "aufgaben.reservierung_stunden",
        Typ.GANZZAHL,
        "Reservierung ohne Frist läuft ab nach",
        beschreibung="Gilt für Aufgaben ohne Zeitfenster. Mit Zeitfenster endet die "
        "Reservierung mit der Frist.",
        einheit="Stunden",
        minimum=1,
        maximum=720,
    )
    definieren(
        "aufgaben.erinnerung_kind_stunden_vorher",
        Typ.GANZZAHL,
        "Erinnerung an das Kind vor Reservierungsablauf",
        einheit="Stunden",
        minimum=0,
        maximum=72,
    )
