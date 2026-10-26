"""Ereignistypen und Texte von avatar (AP26, ARCHITECTURE 5.2)."""

from apps.benachrichtigung import texte
from apps.ereignisse import registry

MOD_GEKAUFT = "mod.gekauft"  # Eltern (Info)
MOD_FERTIG = "mod.fertig"  # Kind: Pop-up + Push "Mod fertig" (E17); intern: Abzeichen/Sondertag
THEMA_GEWECHSELT = "thema.gewechselt"  # Eltern (Info), intern: AP27
RUHMESHALLE_HELD = "ruhmeshalle.held"  # Kind: Pop-up "Dein Held steht in der Ruhmeshalle"
RUHMESHALLE_ELTERN = "ruhmeshalle.eltern"  # Eltern (Info), Widmung schreiben

LINK_KIND_HALLE = "/kind/ruhmeshalle/"
LINK_ELTERN_HALLE = "/eltern/ruhmeshalle/"
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
    registry.typ_deklarieren(
        RUHMESHALLE_HELD,
        modul="avatar",
        bezeichnung="Held in der Ruhmeshalle",
        zielgruppe="kind",
        standard_kanaele=["popup"],
        deep_link_muster=LINK_KIND_HALLE,
    )
    registry.typ_deklarieren(
        RUHMESHALLE_ELTERN,
        modul="avatar",
        bezeichnung="Neuer Held in der Ruhmeshalle",
        zielgruppe="eltern",
        standard_kanaele=["push"],
        deep_link_muster=LINK_ELTERN_HALLE,
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
    texte.text_registrieren(
        RUHMESHALLE_HELD,
        titel="Dein Held steht in der Ruhmeshalle!",
        text="{thema} im Rang {rang} ist jetzt für immer dort. Auf zu einem neuen Abenteuer!",
    )
    texte.text_registrieren(
        RUHMESHALLE_ELTERN,
        titel="{kind} hat einen Helden in die Ruhmeshalle gestellt",
        text="{thema} im Rang {rang}. Du kannst eine Widmung dazuschreiben.",
    )
