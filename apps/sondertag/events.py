"""Ereignistypen von sondertag (AP27, ARCHITECTURE 5.2). Deutsche Texte registriert ``apps.py``
über ``benachrichtigung.texte``."""

from apps.ereignisse import registry

FREIGESCHALTET = "sondertag.freigeschaltet"  # Kind: festliches Pop-up mit Wunsch-Formular
VERDIENT_ELTERN = "sondertag.verdient"  # Eltern: Info "Anna hat einen Sondertag verdient"
WUNSCH = "sondertag.wunsch"  # Eltern (beide): Wunsch annehmen (Entscheidung)
ANGENOMMEN = "sondertag.angenommen"  # Kind: Bestätigung mit Begleitung
UEBERGEBEN = "sondertag.uebergeben"  # Eltern: Begleitung übergeben
# Review AP31: ein wartender Anspruch wird einlösbar (genau einmal je Anspruch, Job)
EINLOESBAR = "sondertag.einloesbar"  # Kind: "Jetzt darfst du dir etwas wünschen"
EINLOESBAR_ELTERN = "sondertag.einloesbar_eltern"  # Eltern: Wunsch kann angenommen werden

LINK_ELTERN = "/eltern/sondertage/"
LINK_KIND = "/kind/"

MEILENSTEIN_ERREICHT = "meilenstein.erreicht"
BELOHNUNGSART = "sondertag"


def typen_deklarieren():
    def typ(slug, bezeichnung, zielgruppe, kanaele=(), **extra):
        registry.typ_deklarieren(
            slug,
            modul="sondertag",
            bezeichnung=bezeichnung,
            zielgruppe=zielgruppe,
            standard_kanaele=list(kanaele),
            **extra,
        )

    eltern = {"deep_link_muster": LINK_ELTERN}
    kind = {"deep_link_muster": LINK_KIND}
    typ(FREIGESCHALTET, "Sondertag freigeschaltet", "kind", ("popup", "push"), **kind)
    typ(VERDIENT_ELTERN, "Sondertag verdient", "eltern", ("push",), **eltern)
    typ(WUNSCH, "Sondertag-Wunsch", "eltern", ("push", "email"), entscheidung=True, **eltern)
    typ(ANGENOMMEN, "Sondertag-Wunsch angenommen", "kind", ("popup", "push"), **kind)
    typ(UEBERGEBEN, "Sondertag-Begleitung übergeben", "eltern", ("push",), **eltern)
    typ(EINLOESBAR, "Sondertag jetzt einlösbar", "kind", ("popup", "push"), **kind)
    typ(EINLOESBAR_ELTERN, "Sondertag jetzt einlösbar (Eltern)", "eltern", ("push",), **eltern)


TEXTE = {
    FREIGESCHALTET: ("Sondertag verdient!", "{hinweis}"),
    VERDIENT_ELTERN: ("{kind} hat einen Sondertag verdient", "{titel}. {hinweis}"),
    WUNSCH: ("Sondertag-Wunsch von {kind}", "„{wunsch}“ · Begleitung: {begleitung}. {hinweis}"),
    ANGENOMMEN: ("Dein Wunsch wurde angenommen!", "{begleitung} plant deinen Sondertag mit dir."),
    UEBERGEBEN: ("Sondertag von {kind}: {begleitung} übernimmt", "Übergeben von {akteur}."),
    EINLOESBAR: ("Dein Sondertag ist jetzt einlösbar!", "{hinweis}"),
    EINLOESBAR_ELTERN: ("Sondertag von {kind} ist jetzt einlösbar", "{hinweis}"),
}


def texte_registrieren():
    from apps.benachrichtigung import texte

    for slug, (titel, text) in TEXTE.items():
        texte.text_registrieren(slug, titel=titel, text=text)
