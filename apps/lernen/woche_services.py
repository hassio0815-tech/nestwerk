"""Schreiben für die Wochenansichten: nur der Eltern-Schalter für die Wochen-Titel (SPEC 21.9).
Titel werden nie gespeichert, vergeben oder gemeldet; sie sind eine Anzeige."""

from apps.kern import audit, einstellungen


def titel_umschalten(an, *, akteur=audit.AKTUELL):
    """Wochen-Titel für die ganze Familie ein- oder ausschalten."""
    einstellungen.setzen("lernen.titel_anzeigen", bool(an), akteur=akteur)
