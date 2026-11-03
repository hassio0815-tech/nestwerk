"""Ereignistypen und Texte von lernen (SPEC 21.12, ARCHITECTURE 5.2).

Ereignis-Daten enthalten keine fertigen Sätze, sondern msgid + Parameter (docs/i18n.md); erst
beim Rendern wird in der Sprache des Empfängers übersetzt.
"""

from django.utils.translation import gettext_noop

from apps.benachrichtigung import texte
from apps.ereignisse import registry

LERNZIEL_ERREICHT = "lernen.ziel_erreicht"  # Kind: kleines Pop-up "Tagesziel geschafft"

LINK_KIND = "/kind/lernen/"


def typen_deklarieren():
    registry.typ_deklarieren(
        LERNZIEL_ERREICHT,
        modul="lernen",
        bezeichnung=gettext_noop("Lernziel erreicht"),
        zielgruppe="kind",
        standard_kanaele=["popup"],
        deep_link_muster=LINK_KIND,
    )


def texte_registrieren():
    texte.text_registrieren(
        LERNZIEL_ERREICHT,
        titel=gettext_noop("Tagesziel geschafft!"),
        text="{hinweis}",  # der Satz steckt in hinweis_msgid + hinweis_parameter
    )
