"""Ereignistypen von spielregeln (AP20). Deutsche Texte liefert ``benachrichtigung.texte``
(Standardtexte; spielregeln und benachrichtigung sind unabhängige Schwestern, kein Import)."""

from django.utils.translation import gettext_lazy as _

from apps.ereignisse import registry

AKTIVITAET_ERFASST = "aktivitaet.erfasst"  # intern: Abzeichen (AP23), Familienziel (AP29)
WOCHE_AUSGEWERTET = "woche.ausgewertet"  # intern: Rang (AP22), Abzeichen (AP23), AP29/30
SERIE_GESTIEGEN = "serie.gestiegen"
SERIE_GERISSEN = "serie.gerissen"
PAUSE_GESTARTET = "pause.gestartet"
PAUSE_BEENDET = "pause.beendet"
SERIENBONUS_GEBUCHT = "serienbonus.gebucht"  # Kind: Pop-up "Serienbonus +5 %" (AP21)
RANG_AUFGESTIEGEN = "rang.aufgestiegen"  # Kind (festliches Pop-up) + Eltern (AP22)
ABZEICHEN_VERLIEHEN = "abzeichen.verliehen"  # Kind (Pop-up) + Eltern (AP23)
MEILENSTEIN_ERREICHT = "meilenstein.erreicht"  # intern: sondertag (AP27), weitere Module

HELD = "spielregeln.held"  # Eltern-Info (AP30)
HELD_KIND = "spielregeln.held_kind"  # Kind: Pop-up "Du bist Held der Woche!"

LINK_KIND = "/kind/"


def typen_deklarieren():
    def typ(slug, bezeichnung, zielgruppe, kanaele=(), **extra):
        registry.typ_deklarieren(
            slug,
            modul="spielregeln",
            bezeichnung=bezeichnung,
            zielgruppe=zielgruppe,
            standard_kanaele=list(kanaele),
            **extra,
        )

    typ(AKTIVITAET_ERFASST, _("Aktivität erfasst"), "intern")
    typ(WOCHE_AUSGEWERTET, _("Woche ausgewertet"), "intern")
    kind = {"deep_link_muster": LINK_KIND}
    typ(SERIE_GESTIEGEN, _("Wochenserie gestiegen"), "kind", ("push", "popup"), **kind)
    typ(SERIE_GERISSEN, _("Wochenserie beendet"), "kind", ("push",), **kind)
    typ(PAUSE_GESTARTET, _("Pause eingetragen"), "kind", ("push", "popup"), **kind)
    typ(PAUSE_BEENDET, _("Pause beendet"), "kind", ("push",), **kind)
    typ(SERIENBONUS_GEBUCHT, _("Serienbonus gebucht"), "kind", ("popup",), **kind)
    typ(RANG_AUFGESTIEGEN, _("Rangaufstieg"), "beide", ("push", "popup", "email"))
    typ(ABZEICHEN_VERLIEHEN, _("Neues Abzeichen"), "beide", ("push", "popup"))
    typ(MEILENSTEIN_ERREICHT, _("Meilenstein erreicht"), "intern")
    typ(HELD, _("Held der Woche"), "eltern", ("push",), deep_link_muster="/eltern/")
    typ(HELD_KIND, _("Held der Woche (Kind)"), "kind", ("popup",), **kind)
