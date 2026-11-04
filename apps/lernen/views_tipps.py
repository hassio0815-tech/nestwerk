"""Rechen-Tipps (SPEC 21.13, Etappe 10b): die Erklärkarten der Rechenarten, nur lesend.

Kinder sehen die Karten in der Sprachstufe ihrer Klassenstufe, Eltern in einer wählbaren Stufe
(damit sie mithelfen können). Die Karten enthalten Regeln und feste Beispiele, nie die Lösung einer
echten Aufgabe.
"""

from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.konten.zugriff import aktuelles_kind, nur_eltern, nur_kind

from . import selectors
from .mathe import registry
from .mathe.hilfe import alle_karten, karte_text
from .mathe.hilfe.karten import GENERATOR_KARTE
from .texte import STUFE_AELTER, STUFE_JUENGER, STUFE_MITTE


def _karten(sprachstufe):
    """Karten, gruppiert nach Inhaltsband (Klasse 3, 6, 8), mit Text in der Sprachstufe."""
    band_je_karte = {}
    for gen, karte in GENERATOR_KARTE.items():
        band_je_karte.setdefault(karte, registry.holen(gen).klassenstufe)
    gruppen = {3: [], 6: [], 8: []}
    for karte in alle_karten():
        gruppen[band_je_karte[karte.schluessel]].append(karte_text(karte, sprachstufe))
    return [(b, gruppen[b]) for b in (3, 6, 8) if gruppen[b]]


@nur_kind
def kind_tipps(request):
    kind = aktuelles_kind(request)
    stufe = selectors.sprachstufe(kind)
    return render(request, "lernen/tipps.html", {"gruppen": _karten(stufe), "sprachstufe": stufe})


@nur_eltern
def eltern_tipps(request):
    try:
        stufe = int(request.GET.get("stufe", STUFE_MITTE))
    except ValueError:
        stufe = STUFE_MITTE
    if stufe not in (STUFE_JUENGER, STUFE_MITTE, STUFE_AELTER):
        stufe = STUFE_MITTE
    return render(
        request,
        "lernen/eltern_tipps.html",
        {
            "gruppen": _karten(stufe),
            "sprachstufe": stufe,
            "stufen": (
                (STUFE_JUENGER, _("bis Klasse 4")),
                (STUFE_MITTE, _("Klasse 5 bis 7")),
                (STUFE_AELTER, _("ab Klasse 8")),
            ),
        },
    )
