"""Registrierungen von lernen in ``kern.registry``: Dashboard-Kacheln und die Metrik
"Tage geübt" (Beteiligung, nicht Menge; SPEC 21.9)."""

from django.utils.translation import gettext_lazy as _

from apps.kern import zeit
from apps.kern.registry import (
    ELTERN,
    KIND,
    Kachel,
    Metrik,
    Provider,
    kachel_registrieren,
    metrik_registrieren,
    provider_registrieren,
)

MODUL = "lernen"


def _kind(request):
    from . import selectors

    benutzer = request.user
    if getattr(benutzer, "rolle", None) != "kind":
        return {}
    return {"bild": selectors.tagesbild(benutzer, zeit.heute())}


def _eltern(request):
    """Je Kind eine Zeile: Minuten heute, Ziel, Serie. Keine Vergleiche zwischen Kindern."""
    from apps.konten import selectors as konten

    from . import selectors

    heute = zeit.heute()
    return {"zeilen": [(k, selectors.tagesbild(k, heute)) for k in konten.aktive_kinder()]}


def kacheln_registrieren():
    kachel_registrieren(
        Kachel(
            "lernen.kind",
            MODUL,
            _("Lernen"),
            "lernen/kacheln/kind_lernen.html",
            {KIND},
            _kind,
            reihenfolge=14,
        )
    )
    kachel_registrieren(
        Kachel(
            "lernen.eltern",
            MODUL,
            _("Lernen"),
            "lernen/kacheln/eltern_lernen.html",
            {ELTERN},
            _eltern,
            reihenfolge=24,
        )
    )


def metriken_registrieren():
    from . import selectors

    metrik_registrieren(
        Metrik(
            "tage_geuebt",
            MODUL,
            "Tage geübt",
            beschreibung="Tage, an denen mindestens der Mindesttag gelernt wurde",
            einheit="Tage",
        )
    )
    provider_registrieren(
        Provider("metrik.tage_geuebt", MODUL, "Tage geübt", selectors.tage_geuebt)
    )
