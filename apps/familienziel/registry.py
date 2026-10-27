"""Dashboard-Kacheln von familienziel (Registry in ``kern``): Tablet-Leiste, Kinder, Eltern."""

from django.utils.translation import gettext_lazy as _

from apps.kern import zeit
from apps.kern.registry import ELTERN, KIND, TABLET, Kachel, kachel_registrieren

MODUL = "familienziel"


def _ansicht():
    from . import selectors

    return selectors.ansicht(zeit.jetzt())


def _tablet(request):
    return {"a": _ansicht(), "zeitpunkt": zeit.jetzt()}


def _kind(request):
    from . import selectors

    a = _ansicht()
    return {
        "a": a,
        "stimme": selectors.eigene_stimme(request.user, a.abstimmung),
    }


def _eltern(request):
    from . import selectors

    return {"a": _ansicht(), "gleichstand": selectors.gleichstand_wochen()}


def kacheln_registrieren():
    kachel_registrieren(
        Kachel(
            "familienziel.leiste",
            MODUL,
            _("Familienziel"),
            "familienziel/kacheln/tablet_leiste.html",
            {TABLET},
            _tablet,
            reihenfolge=10,
        )
    )
    kachel_registrieren(
        Kachel(
            "familienziel.kind",
            MODUL,
            _("Familienziel"),
            "familienziel/kacheln/kind_familienziel.html",
            {KIND},
            _kind,
            reihenfolge=12,
        )
    )
    kachel_registrieren(
        Kachel(
            "familienziel.eltern",
            MODUL,
            _("Familienziel"),
            "familienziel/kacheln/eltern_familienziel.html",
            {ELTERN},
            _eltern,
            reihenfolge=22,
        )
    )
