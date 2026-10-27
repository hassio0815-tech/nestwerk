"""Ereignistypen des Betriebs (AP18)."""

from django.utils.translation import gettext_noop

from . import registry

BACKUP_FEHLER = "system.backup_fehler"


def typen_deklarieren():
    registry.typ_deklarieren(
        BACKUP_FEHLER,
        modul="ereignisse",
        bezeichnung=gettext_noop("Datensicherung fehlgeschlagen"),
        zielgruppe="eltern",
        standard_kanaele=["push", "email"],
    )
