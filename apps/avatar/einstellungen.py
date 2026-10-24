"""Einstellungen von avatar (AP26). Definition hier, Startwerte per Datenmigration 0003."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {
    # SPEC 11.4 Zeitbremse: höchstens ein neu fertiger Mod je Woche zählt für die Ausbaustufe
    "avatar.max_zaehlende_mods_woche": 1,
}


def einstellungen_definieren():
    definieren(
        "avatar.max_zaehlende_mods_woche",
        Typ.GANZZAHL,
        "Zählende Mods pro Woche",
        beschreibung="So viele neu fertige Mods zählen je Woche für die Ausbaustufe. Weitere "
        "Mods sind sofort nutzbar und zählen ab der nächsten freien Woche (Warteschlange).",
        einheit="Mods",
        minimum=1,
        maximum=6,
    )
