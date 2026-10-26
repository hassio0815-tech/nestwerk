"""Ereignistypen von punkte (ARCHITECTURE 5.2)."""

from apps.ereignisse import registry

GEBUCHT = "punkte.gebucht"


def typen_deklarieren():
    registry.typ_deklarieren(
        GEBUCHT,
        modul="punkte",
        bezeichnung="Punkte gebucht",
        zielgruppe="intern",  # Familienziel, Live-Aktualisierung
    )
