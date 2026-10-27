"""Ereignistypen von punkte (ARCHITECTURE 5.2)."""

from django.utils.translation import gettext_noop

from apps.ereignisse import registry

GEBUCHT = "punkte.gebucht"


def typen_deklarieren():
    registry.typ_deklarieren(
        GEBUCHT,
        modul="punkte",
        bezeichnung=gettext_noop("Punkte gebucht"),
        zielgruppe="intern",  # Familienziel, Live-Aktualisierung
    )
