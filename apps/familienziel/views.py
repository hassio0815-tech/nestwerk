"""Eltern-Seite (Belohnungsliste, Wochenziel, Gleichstand, Historie) und Abstimmung der Kinder."""

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.kern import zeit
from apps.kern.zeit import IsoWoche
from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind, nur_eltern, nur_kind

from . import selectors, services
from .forms import BelohnungForm, WocheForm
from .models import Familienbelohnung, Familienwoche, Grossziel


def _wochen_fuer_eltern():
    """Aktuelle und nächste Woche (Zeilen werden bei Bedarf angelegt)."""
    iso = IsoWoche.von(zeit.jetzt())
    zeilen = []
    for w in (iso, iso.naechste()):
        zeile, _ = services.woche_sicherstellen(w)
        zeilen.append(zeile)
    return zeilen


@nur_eltern
def eltern_seite(request, *, belohnung_form=None, fehler="", status=200):
    wochen = [
        {
            "zeile": z,
            "form": WocheForm(initial={"ziel_punkte": z.ziel_punkte}),
            "iso": str(IsoWoche(z.iso_jahr, z.iso_woche)),
        }
        for z in _wochen_fuer_eltern()
    ]
    return render(
        request,
        "familienziel/eltern.html",
        {
            "a": selectors.ansicht(),
            "wochen": wochen,
            "belohnungen": selectors.belohnungen(),
            "belohnung_form": belohnung_form or BelohnungForm(initial={"symbol": "geschenk"}),
            "historie": selectors.historie(),
            "grossziele": selectors.grossziele(),
            "fehler": fehler,
        },
        status=status,
    )


@nur_eltern
@require_POST
def belohnung_neu(request):
    form = BelohnungForm(request.POST)
    if not form.is_valid():
        return eltern_seite(request, belohnung_form=form)
    try:
        services.belohnung_speichern(
            von=aktueller_elternteil(request),
            titel=form.cleaned_data["titel"],
            symbol=form.cleaned_data["symbol"],
            ist_grossziel=form.cleaned_data["ist_grossziel"],
        )
    except services.FamilienzielFehler as fehler:
        return eltern_seite(request, fehler=str(fehler), status=400)
    return redirect("familienziel:eltern")


@nur_eltern
@require_POST
def belohnung_aktion(request, pk, aktion):
    belohnung = get_object_or_404(Familienbelohnung, pk=pk)
    eltern = aktueller_elternteil(request)
    try:
        if aktion == "aktiv":
            services.belohnung_aktiv_setzen(belohnung, True, von=eltern)
        elif aktion == "inaktiv":
            services.belohnung_aktiv_setzen(belohnung, False, von=eltern)
        elif aktion == "loeschen":
            services.belohnung_loeschen(belohnung, von=eltern)
        else:
            return redirect("familienziel:eltern")
    except services.FamilienzielFehler as fehler:
        return eltern_seite(request, fehler=str(fehler), status=400)
    return redirect("familienziel:eltern")


@nur_eltern
@require_POST
def woche_setzen(request, pk):
    zeile = get_object_or_404(Familienwoche, pk=pk)
    form = WocheForm(request.POST)
    if form.is_valid():
        try:
            services.woche_festlegen(
                zeile,
                von=aktueller_elternteil(request),
                ziel_punkte=form.cleaned_data["ziel_punkte"],
                belohnung=form.cleaned_data["belohnung"],
            )
        except services.FamilienzielFehler as fehler:
            return eltern_seite(request, fehler=str(fehler), status=400)
    else:
        return eltern_seite(request, fehler="Bitte Ziel und Belohnung prüfen.", status=400)
    return redirect("familienziel:eltern")


@nur_eltern
@require_POST
def woche_eingeloest(request, pk):
    zeile = get_object_or_404(Familienwoche, pk=pk)
    try:
        services.woche_einloesen(zeile, von=aktueller_elternteil(request))
    except services.FamilienzielFehler as fehler:
        return eltern_seite(request, fehler=str(fehler), status=400)
    return redirect("familienziel:eltern")


@nur_eltern
@require_POST
def grossziel_eingeloest(request, pk):
    services.grossziel_einloesen(
        get_object_or_404(Grossziel, pk=pk), von=aktueller_elternteil(request)
    )
    return redirect("familienziel:eltern")


@nur_kind
@require_POST
def abstimmen(request):
    try:
        services.stimme_abgeben(aktuelles_kind(request), request.POST.get("belohnung"))
    except (services.FamilienzielFehler, ValueError):
        pass  # Fenster zu oder Auswahl ungültig: die Kachel zeigt den aktuellen Stand
    return redirect("konten:kind_heim")
