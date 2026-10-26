"""Dashboard-Kacheln von sondertag (Registry in ``kern``): Kind (Fortschritt), Eltern."""

from apps.kern.registry import ELTERN, KIND, Kachel, kachel_registrieren

MODUL = "sondertag"


def _kind(request):
    from . import selectors

    f = selectors.fortschritt(request.user)
    return {"f": f, "wunsch_erlaubt": selectors.wunsch_erlaubt(f.eintrag)}


def _eltern(request):
    from . import selectors

    return {
        "zeilen": selectors.eltern_uebersicht(),
        "wuensche": selectors.offene_wuensche(),
    }


def kacheln_registrieren():
    kachel_registrieren(
        Kachel(
            "sondertag.kind",
            MODUL,
            "Sondertag",
            "sondertag/kacheln/kind_sondertag.html",
            {KIND},
            _kind,
            reihenfolge=11,
        )
    )
    kachel_registrieren(
        Kachel(
            "sondertag.eltern",
            MODUL,
            "Sondertage",
            "sondertag/kacheln/eltern_sondertag.html",
            {ELTERN},
            _eltern,
            reihenfolge=21,
        )
    )
