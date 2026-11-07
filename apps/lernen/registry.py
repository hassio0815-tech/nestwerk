"""Registrierungen von lernen in ``kern.registry``: Dashboard-Kacheln und die Metrik
"Tage geübt" (Beteiligung, nicht Menge; SPEC 21.9)."""

from django.utils.translation import gettext_lazy as _

from apps.kern import zeit
from apps.kern.registry import (
    ELTERN,
    KIND,
    TABLET,
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

    from . import material_selectors, selectors

    heute = zeit.heute()
    kinder = list(konten.aktive_kinder())
    return {
        "zeilen": [(k, selectors.tagesbild(k, heute)) for k in kinder],
        # Badge (E-2): genau die Zahl der Einträge, die ``warten_auf_eltern()`` liefert
        "warten": material_selectors.warten_auf_eltern().filter(kind__in=kinder).count(),
    }


def _woche(request):
    """Übungswoche für die Familien-/Tablet-Ansicht und das Kind: Beteiligung, Familienziel,
    Titel der Vorwoche (wenn die Eltern die Anzeige nicht abgeschaltet haben)."""
    from apps.konten import selectors as konten

    from . import woche_selectors, woche_texte

    heute = zeit.heute()
    kinder = list(konten.aktive_kinder())
    titel = [
        {
            "name": woche_texte.titel_name(t.schluessel),
            "beschreibung": woche_texte.titel_beschreibung(t.schluessel),
            "namen": sorted(k.anzeigename for k in t.kinder),
        }
        for t in woche_selectors.titel_vorwoche(kinder, heute)
    ]
    return {
        "beteiligung": woche_selectors.uebungswoche(kinder, heute),
        "ziel": woche_selectors.familienziel(kinder, heute),
        "titel": titel,
    }


def kacheln_registrieren():
    kachel_registrieren(
        Kachel(
            "lernen.woche",
            MODUL,
            _("Übungswoche"),
            "lernen/kacheln/familie_woche.html",
            {KIND, TABLET},
            _woche,
            reihenfolge=16,
        )
    )
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
    metrik_registrieren(
        Metrik(
            "lern_beteiligung",
            MODUL,
            "Lern-Beteiligung",
            beschreibung=(
                "Tage, an denen das Kind sein eigenes Tagesziel erreicht hat "
                "(relativ zum persönlichen Ziel, nie die Menge)"
            ),
            einheit="Tage",
        )
    )
    provider_registrieren(
        Provider("metrik.lern_beteiligung", MODUL, "Lern-Beteiligung", selectors.lern_beteiligung)
    )
