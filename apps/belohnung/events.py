"""Ereignistypen und Texte von belohnung (ARCHITECTURE 5.2)."""

from django.utils.translation import gettext_noop

from apps.benachrichtigung import texte
from apps.ereignisse import registry

ANTRAG = "belohnung.antrag"
BESTAETIGT = "belohnung.bestaetigt"
ABGELEHNT = "belohnung.abgelehnt"


def typen_deklarieren():
    registry.typ_deklarieren(
        ANTRAG,
        modul="belohnung",
        bezeichnung=gettext_noop("Belohnung beantragt"),
        zielgruppe="eltern",
        standard_kanaele=["push", "email"],
        deep_link_muster="/eltern/belohnungen/",
        entscheidung=True,
    )
    registry.typ_deklarieren(
        BESTAETIGT,
        modul="belohnung",
        bezeichnung=gettext_noop("Belohnung bestätigt"),
        zielgruppe="kind",
        standard_kanaele=["push"],
        deep_link_muster="/kind/belohnungen/",
    )
    registry.typ_deklarieren(
        ABGELEHNT,
        modul="belohnung",
        bezeichnung=gettext_noop("Belohnung abgelehnt"),
        zielgruppe="kind",
        standard_kanaele=["push"],
        deep_link_muster="/kind/belohnungen/",
    )


def texte_registrieren():
    # Text für ANTRAG: Standardtext aus benachrichtigung.texte
    texte.text_registrieren(
        BESTAETIGT,
        titel=gettext_noop("Belohnung bestätigt!"),
        text=gettext_noop("„{belohnung}“ wurde bestätigt. Viel Spaß!"),
    )
    texte.text_registrieren(
        ABGELEHNT,
        titel=gettext_noop("Belohnung nicht bewilligt"),
        text=gettext_noop("„{belohnung}“ wurde diesmal abgelehnt. Deine Punkte bleiben."),
    )
