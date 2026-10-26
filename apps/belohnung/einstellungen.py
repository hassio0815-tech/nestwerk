"""Einstellungen von belohnung (DATA_MODEL 15.2). Startwert per Datenmigration."""

from apps.kern.einstellungen import Typ, definieren

STARTWERTE = {"belohnung.taschengeld_limit_cent": 1000}  # Entscheidung 13: 10 €/Monat/Kind


def einstellungen_definieren():
    definieren(
        "belohnung.taschengeld_limit_cent",
        Typ.GANZZAHL,
        "Taschengeld-Limit pro Monat und Kind",
        beschreibung="Gilt für alle Kinder ohne eigenes Limit. Bestätigte und offene Anträge "
        "des Kalendermonats zählen.",
        einheit="Cent",
        minimum=0,
        maximum=100000,
    )
