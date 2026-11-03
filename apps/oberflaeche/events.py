"""Ereignistypen der Mood-Vorschläge (Kind -> Eltern, Eltern -> Kind) und ihre Texte.

Die Vorschläge selbst gehören zu ``konten`` (Schicht darunter, kennt keine Ereignisse); die
Oberfläche verbindet beides in einer Transaktion (``mood.py``).
"""

from django.utils.translation import gettext_noop

from apps.ereignisse import registry

MOOD_VORGESCHLAGEN = "mood.vorgeschlagen"
MOOD_ZUGELASSEN = "mood.zugelassen"
MOOD_ABGELEHNT = "mood.abgelehnt"

TEXTE = {
    MOOD_VORGESCHLAGEN: (
        gettext_noop("{kind} schlägt einen Mood vor"),
        gettext_noop("„{vorschlag}“ wartet auf deine Entscheidung."),
    ),
    MOOD_ZUGELASSEN: (
        gettext_noop("Dein Mood ist dabei!"),
        gettext_noop("„{vorschlag}“ gibt es jetzt für alle."),
    ),
    MOOD_ABGELEHNT: (
        gettext_noop("Mood nicht übernommen"),
        gettext_noop("„{vorschlag}“ nehmen wir diesmal nicht auf."),
    ),
}


def typen_deklarieren():
    def typ(slug, bezeichnung, zielgruppe, **extra):
        registry.typ_deklarieren(
            slug,
            modul="oberflaeche",
            bezeichnung=bezeichnung,
            zielgruppe=zielgruppe,
            standard_kanaele=["push"],
            **extra,
        )

    typ(
        MOOD_VORGESCHLAGEN,
        gettext_noop("Kind schlägt einen Mood vor"),
        "eltern",
        entscheidung=True,
        deep_link_muster="/eltern/moods/",
    )
    typ(
        MOOD_ZUGELASSEN,
        gettext_noop("Mood-Vorschlag zugelassen"),
        "kind",
        deep_link_muster="/kind/einstellungen/",
    )
    typ(
        MOOD_ABGELEHNT,
        gettext_noop("Mood-Vorschlag abgelehnt"),
        "kind",
        deep_link_muster="/kind/einstellungen/",
    )


def texte_registrieren():
    from apps.benachrichtigung import texte

    for slug, (titel, text) in TEXTE.items():
        texte.text_registrieren(slug, titel=titel, text=text)
