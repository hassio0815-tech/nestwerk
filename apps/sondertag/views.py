"""Wunsch-Formular (Kind, auch im festlichen Pop-up) und Eltern-Seite Sondertage (AP27)."""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.kern import einstellungen
from apps.konten import selectors as konten
from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind, nur_eltern, nur_kind
from apps.spielregeln import services as spielregeln

from . import prognose, selectors, services
from .models import SondertagAnspruch


def _wunsch_kontext(kind, *, fehler="", werte=None, gesendet=False, teil=False):
    eintrag = selectors.aktueller(kind)
    werte = werte or {}
    if eintrag is not None and not werte:
        werte = {
            "wunsch": eintrag.anspruch.wunsch,
            "begleitung": eintrag.anspruch.begleitung_wunsch or "egal",
        }
    return {
        "eintrag": eintrag,
        "erlaubt": selectors.wunsch_erlaubt(eintrag),
        "optionen": selectors.begleitung_optionen(),
        "werte": werte,
        "fehler": fehler,
        "gesendet": gesendet,
        "teil": teil,
        "max_zeichen": einstellungen.wert("sondertag.wunsch_max_zeichen"),
        "einloesbar_ab": services.datum_text(eintrag.einloesbar_ab) if eintrag else "",
    }


@nur_kind
@require_http_methods(["GET", "POST"])
def wunsch(request):
    """GET: Formular (HTMX: nur der Teil fürs Pop-up). POST: Wunsch senden."""
    kind = aktuelles_kind(request)
    teil = request.headers.get("HX-Request") == "true"
    vorlage = "sondertag/_wunsch_form.html" if teil else "sondertag/wunsch.html"
    if request.method == "GET":
        return render(request, vorlage, _wunsch_kontext(kind, teil=teil))
    eintrag = selectors.aktueller(kind)
    werte = {
        "wunsch": request.POST.get("wunsch", ""),
        "begleitung": request.POST.get("begleitung", ""),
    }
    if eintrag is None:
        raise Http404("Kein Sondertag offen")
    try:
        services.wunsch_senden(
            kind, eintrag.anspruch, wunsch=werte["wunsch"], begleitung=werte["begleitung"]
        )
    except services.SondertagFehler as fehler:
        # HTMX tauscht Fehlerantworten nicht: im Pop-up mit 200 neu zeigen
        return render(
            request,
            vorlage,
            _wunsch_kontext(kind, fehler=str(fehler), werte=werte, teil=teil),
            status=200 if teil else 400,
        )
    if teil:
        return render(request, vorlage, _wunsch_kontext(kind, gesendet=True, teil=True))
    return redirect("konten:kind_heim")


# --- Eltern -----------------------------------------------------------------------------------


def _seite(request, *, fehler="", status=200):
    return render(
        request,
        "sondertag/eltern.html",
        {
            "zeilen": selectors.eltern_uebersicht(),
            "wuensche": selectors.offene_wuensche(),
            "angenommen": list(selectors.angenommen_offen()),
            "eltern": list(konten.aktive_eltern()),
            "kinder": list(konten.aktive_kinder()),
            "regeln": services.regeln(),
            "fehler": fehler,
        },
        status=status,
    )


@nur_eltern
def eltern_seite(request):
    return _seite(request)


def _aktion(request, funktion):
    try:
        funktion()
    except services.SondertagFehler as fehler:
        return _seite(request, fehler=str(fehler), status=400)
    return redirect("sondertag:eltern")


@nur_eltern
@require_POST
def annehmen(request, pk):
    anspruch = get_object_or_404(SondertagAnspruch, pk=pk)
    return _aktion(request, lambda: services.annehmen(anspruch, von=aktueller_elternteil(request)))


@nur_eltern
@require_POST
def uebergeben(request, pk):
    anspruch = get_object_or_404(SondertagAnspruch, pk=pk)
    return _aktion(
        request,
        lambda: services.uebergeben(
            anspruch, von=aktueller_elternteil(request), an=request.POST.get("an", "")
        ),
    )


@nur_eltern
@require_POST
def stattgefunden(request, pk):
    anspruch = get_object_or_404(SondertagAnspruch, pk=pk)
    return _aktion(
        request,
        lambda: services.stattgefunden(
            anspruch, von=aktueller_elternteil(request), datum=request.POST.get("datum") or None
        ),
    )


@nur_eltern
@require_POST
def aendern(request, pk):
    anspruch = get_object_or_404(SondertagAnspruch, pk=pk)
    p = request.POST
    return _aktion(
        request,
        lambda: services.eintrag_aendern(
            anspruch,
            von=aktueller_elternteil(request),
            annahme_datum=p.get("annahme_datum") or None,
            begleitung=p.get("begleitung", ""),
            stattgefunden_am=p.get("stattgefunden_am", ""),
            notiz=p.get("notiz", ""),
        ),
    )


@nur_eltern
@require_POST
def loeschen(request, pk):
    anspruch = get_object_or_404(SondertagAnspruch, pk=pk)
    return _aktion(
        request, lambda: services.manuell_loeschen(anspruch, von=aktueller_elternteil(request))
    )


@nur_eltern
@require_POST
def manuell(request):
    p = request.POST
    kind = next((k for k in konten.aktive_kinder() if str(k.pk) == p.get("kind", "")), None)
    if kind is None:
        return _seite(request, fehler=_("Bitte ein Kind wählen."), status=400)
    return _aktion(
        request,
        lambda: services.manuell_erfassen(
            kind,
            von=aktueller_elternteil(request),
            datum=p.get("datum", ""),
            begleitung=p.get("begleitung", ""),
            notiz=p.get("notiz", ""),
        ),
    )


# --- Prognose und Kalibrierung (AP32) -----------------------------------------------------------


def _prognose_seite(request, *, fehler="", status=200):
    return render(
        request,
        "sondertag/prognose.html",
        {"zeilen": prognose.uebersicht(), "fehler": fehler},
        status=status,
    )


@nur_eltern
def prognose_seite(request):
    return _prognose_seite(request)


@nur_eltern
@require_POST
def prognose_uebernehmen(request):
    """Faktor für Schwellen oder Mindestwochen eines Kindes setzen (Audit im Service)."""
    kind = next(
        (k for k in konten.aktive_kinder() if str(k.pk) == request.POST.get("kind", "")), None
    )
    if kind is None:
        raise Http404
    knopf = request.POST.get("knopf", "")
    faktor = request.POST.get("faktor", "").strip() or None
    notiz = request.POST.get("notiz", "") or "Prognose"
    von = aktueller_elternteil(request)
    try:
        if knopf == prognose.WOCHEN:
            spielregeln.wochen_faktor_setzen(kind, faktor, von=von, notiz=notiz)
        elif knopf == "mods":
            spielregeln.mod_faktoren_setzen(
                kind=kind,
                von=von,
                faktor_preis=request.POST.get("faktor_preis", "") or "1",
                faktor_bauzeit=request.POST.get("faktor_bauzeit", "") or "1",
            )
        elif knopf == prognose.SCHWELLE:
            spielregeln.kalibrierung_setzen(kind, faktor, von=von, notiz=notiz)
        else:
            raise Http404
    except spielregeln.RangFehler as fehler:
        return _prognose_seite(request, fehler=str(fehler), status=400)
    return redirect("sondertag:prognose")
