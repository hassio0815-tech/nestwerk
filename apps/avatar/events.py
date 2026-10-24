"""Ereignistypen und Texte von avatar (AP26, ARCHITECTURE 5.2)."""

from apps.benachrichtigung import texte
from apps.ereignisse import registry

MOD_GEKAUFT = "mod.gekauft"  # Eltern (Info)
MOD_FERTIG = "mod.fertig"  # Kind: Pop-up + Push "Mod fertig" (E17); intern: Abzeichen/Sondertag
THEMA_GEWECHSELT = "thema.gewechselt"  # Eltern (Info), intern: AP27

LINK_KIND = "/kind/mods/"
LINK_ELTERN = "/eltern/mods/"


def typen_deklarieren():
    registry.typ_deklarieren(
        MOD_GEKAUFT,
        modul="avatar",
        bezeichnung="Mod gekauft",
        zielgruppe="eltern",
        standard_kanaele=["push"],
        deep_link_muster=LINK_ELTERN,
    )
    registry.typ_deklarieren(
        MOD_FERTIG,
        modul="avatar",
        bezeichnung="Mod fertig",
        zielgruppe="kind",
        standard_kanaele=["push", "popup"],
        deep_link_muster=LINK_KIND,
    )
    registry.typ_deklarieren(
        THEMA_GEWECHSELT,
        modul="avatar",
        bezeichnung="Thema gewechselt",
        zielgruppe="eltern",
        standard_kanaele=["push"],
        deep_link_muster=LINK_ELTERN,
    )


def texte_registrieren():
    texte.text_registrieren(
        MOD_GEKAUFT,
        titel="{kind} hat einen Mod gekauft",
        text="„{mod}“ für {preis} Punkte, fertig in {bauzeit}.",
    )
    texte.text_registrieren(
        MOD_FERTIG,
        titel="Dein Mod ist fertig!",
        text="„{mod}“ ist aus der {werkstatt} gekommen.",
    )
    texte.text_registrieren(
        THEMA_GEWECHSELT,
        titel="{kind} hat das Thema gewechselt",
        text="Neu: {thema}. {verloren} Mods ({wert} Punkte) sind verfallen.",
    )
