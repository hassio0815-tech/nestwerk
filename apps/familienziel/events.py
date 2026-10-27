"""Ereignistypen von familienziel (AP29). Deutsche Texte liefert ``benachrichtigung.texte``.

Ereignisse ohne Kind erreichen nur die Eltern. Für die Kinder (Konfetti-Pop-up) entsteht je Kind
ein eigenes Ereignis mit Zusatz ``_kind`` (Router: ein Kind je Ereignis)."""

from django.utils.translation import gettext_noop

from apps.ereignisse import registry

ERREICHT = "familienziel.erreicht"  # Eltern: Push "Pizza-Abend freigeschaltet!"
ERREICHT_KIND = "familienziel.erreicht_kind"  # je Kind: Konfetti-Pop-up
ABSTIMMUNG_OFFEN = "familienziel.abstimmung_offen"  # je Kind
ABSTIMMUNG_GLEICHSTAND = "familienziel.abstimmung_gleichstand"  # Eltern (Entscheidung)
GROSSZIEL = "familienziel.grossziel"  # Eltern
GROSSZIEL_KIND = "familienziel.grossziel_kind"  # je Kind: Pop-up

LINK_ELTERN = "/eltern/familienziel/"
LINK_KIND = "/kind/"


def typen_deklarieren():
    def typ(slug, bezeichnung, zielgruppe, kanaele=(), **extra):
        registry.typ_deklarieren(
            slug,
            modul="familienziel",
            bezeichnung=bezeichnung,
            zielgruppe=zielgruppe,
            standard_kanaele=list(kanaele),
            **extra,
        )

    eltern = {"deep_link_muster": LINK_ELTERN}
    kind = {"deep_link_muster": LINK_KIND}
    typ(ERREICHT, gettext_noop("Familienziel erreicht"), "eltern", ("push",), **eltern)
    typ(ERREICHT_KIND, gettext_noop("Familienziel erreicht (Kind)"), "kind", ("popup",), **kind)
    typ(
        ABSTIMMUNG_OFFEN,
        gettext_noop("Abstimmung über das Familienziel"),
        "kind",
        ("popup",),
        **kind,
    )
    typ(
        ABSTIMMUNG_GLEICHSTAND,
        gettext_noop("Gleichstand bei der Abstimmung"),
        "eltern",
        ("push",),
        entscheidung=True,
        **eltern,
    )
    typ(
        GROSSZIEL, gettext_noop("Großes Familienziel freigeschaltet"), "eltern", ("push",), **eltern
    )
    typ(GROSSZIEL_KIND, gettext_noop("Großes Familienziel (Kind)"), "kind", ("popup",), **kind)
