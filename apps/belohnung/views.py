"""UI von belohnung: Kinder (Katalog, Antrag, eigene Anträge) und Eltern (Anträge, Katalog, Limit).

Alle Kind-Views zeigen nur Daten des angemeldeten Kindes; Eltern-Views nur für Eltern.
"""

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods, require_POST

from apps.kern.sprache import uebersetzt
from apps.konten import selectors as konten_selectors
from apps.konten.zugriff import aktuelles_kind, nur_eltern, nur_kind
from apps.punkte import selectors as punkte

from . import selectors, services
from .forms import BelohnungForm, KindLimitForm, LimitForm
from .models import Belohnung, Einloeseantrag, Status, TaschengeldLimit, euro_text


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def euro(cent):
    return euro_text(cent)


# --- Kind -------------------------------------------------------------------------------------


def _kachel_zustand(kind, belohnung, verfuegbar, frei_cent):
    """(möglich, Grund) für eine Kachel; die endgültige Prüfung macht der Service."""
    if belohnung.preis_punkte > verfuegbar:
        fehlt = belohnung.preis_punkte - verfuegbar
        return False, ngettext("Noch %(punkte)s Punkt", "Noch %(punkte)s Punkte", fehlt) % {
            "punkte": fehlt
        }
    if belohnung.kategorie.ist_taschengeld and (belohnung.geldwert_cent or 0) > frei_cent:
        return False, _("Monatslimit erreicht")
    return True, ""


def _kind_kontext(kind, meldung="", fehler=""):
    verfuegbar = punkte.verfuegbar(kind)
    frei = selectors.taschengeld_frei_cent(kind)
    kacheln = []
    for b in selectors.katalog():
        moeglich, grund = _kachel_zustand(kind, b, verfuegbar, frei)
        kacheln.append({"b": b, "moeglich": moeglich, "grund": grund})
    return {
        "verfuegbar": verfuegbar,
        "kacheln": kacheln,
        "antraege": selectors.antraege_des_kindes(kind)[:20],
        "taschengeld_frei": euro(frei),
        "meldung": meldung,
        "fehler": fehler,
    }


def _kind_antwort(request, kind, meldung="", fehler=""):
    kontext = _kind_kontext(kind, meldung, fehler)
    if _htmx(request) and request.POST.get("ort") == "dashboard":
        return render(request, "belohnung/_einloesen.html", kontext)
    vorlage = "belohnung/_kind_inhalt.html" if _htmx(request) else "belohnung/kind.html"
    return render(request, vorlage, kontext)


@nur_kind
def kind_katalog(request):
    return _kind_antwort(request, aktuelles_kind(request))


@nur_kind
@require_POST
def beantragen(request, pk):
    kind = aktuelles_kind(request)
    belohnung = get_object_or_404(Belohnung, pk=pk)
    try:
        antrag = services.antrag_stellen(kind, belohnung)
    except services.BelohnungFehler as fehler:
        return _kind_antwort(request, kind, fehler=str(fehler))
    meldung = _("Antrag für „%(titel)s“ ist raus. Mama oder Papa schauen drauf.") % {
        "titel": uebersetzt(antrag.titel_snapshot)
    }
    if _htmx(request):
        return _kind_antwort(request, kind, meldung=meldung)
    return redirect("belohnung:kind")


@nur_kind
@require_POST
def zurueckziehen(request, pk):
    kind = aktuelles_kind(request)
    antrag = get_object_or_404(Einloeseantrag, pk=pk, kind=kind)  # fremde Anträge: 404
    try:
        services.zurueckziehen(antrag, kind=kind)
    except services.BelohnungFehler as fehler:
        return _kind_antwort(request, kind, fehler=str(fehler))
    if _htmx(request):
        return _kind_antwort(request, kind, meldung=_("Antrag zurückgezogen."))
    return redirect("belohnung:kind")


# --- Eltern: Anträge --------------------------------------------------------------------------


def _antrag_zeile(request, antrag, fehler=""):
    antrag.kind_verfuegbar = punkte.guthaben(antrag.kind)
    return render(request, "belohnung/_antrag_zeile.html", {"a": antrag, "fehler": fehler})


@nur_eltern
def antraege(request):
    offene = list(selectors.offene_antraege().order_by("erstellt_am"))
    for a in offene:
        a.kind_verfuegbar = punkte.guthaben(a.kind)
    erledigt = (
        Einloeseantrag.objects.exclude(status=Status.OFFEN)
        .select_related("kind", "belohnung")
        .order_by("-entschieden_am", "-id")[:15]
    )
    return render(request, "belohnung/antraege.html", {"offene": offene, "erledigt": erledigt})


@nur_eltern
@require_POST
def bestaetigen(request, pk):
    antrag = get_object_or_404(Einloeseantrag, pk=pk)
    try:
        antrag = services.bestaetigen(antrag, von=request.user)
    except services.BelohnungFehler as fehler:
        antrag.refresh_from_db()
        return _antrag_zeile(request, antrag, fehler=str(fehler))
    if _htmx(request):
        return _antrag_zeile(request, antrag)
    return redirect("belohnung:antraege")


@nur_eltern
@require_POST
def ablehnen(request, pk):
    antrag = get_object_or_404(Einloeseantrag, pk=pk)
    try:
        antrag = services.ablehnen(antrag, von=request.user, grund=request.POST.get("grund", ""))
    except services.BelohnungFehler as fehler:
        antrag.refresh_from_db()
        return _antrag_zeile(request, antrag, fehler=str(fehler))
    if _htmx(request):
        return _antrag_zeile(request, antrag)
    return redirect("belohnung:antraege")


# --- Eltern: Katalog und Limit ----------------------------------------------------------------


def _weiter(request, url_name):
    url = reverse(url_name)
    if _htmx(request):
        antwort = HttpResponse(status=204)
        antwort["HX-Redirect"] = url
        return antwort
    return redirect(url)


def _formular(request, form, *, titel, aktion):
    kontext = {
        "form": form,
        "titel": titel,
        "aktion": aktion,
        "zurueck": reverse("belohnung:katalog"),
    }
    vorlage = "belohnung/_formular.html" if _htmx(request) else "belohnung/formular.html"
    return render(request, vorlage, kontext)


@nur_eltern
def katalog(request):
    kinder = list(konten_selectors.aktive_kinder())
    for k in kinder:
        eigenes = TaschengeldLimit.objects.filter(kind=k).first()
        k.limit_form = KindLimitForm(
            prefix=f"k{k.pk.hex[:8]}",
            initial={"betrag": eigenes.monatslimit_cent if eigenes else None},
        )
        k.limit_prefix = k.limit_form.prefix
        k.limit_text = euro(selectors.limit_cent(k))
    return render(
        request,
        "belohnung/katalog.html",
        {
            "belohnungen": selectors.katalog(nur_aktive=False),
            "limit_form": LimitForm(initial={"betrag": selectors.standard_limit_cent()}),
            "kinder": kinder,
        },
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def belohnung_neu(request):
    form = BelohnungForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.belohnung_speichern(form, von=request.user)
        return _weiter(request, "belohnung:katalog")
    return _formular(request, form, titel=_("Neue Belohnung"), aktion=reverse("belohnung:neu"))


@nur_eltern
@require_http_methods(["GET", "POST"])
def belohnung_bearbeiten(request, pk):
    belohnung = get_object_or_404(Belohnung, pk=pk)
    form = BelohnungForm(request.POST or None, instance=belohnung)
    if request.method == "POST" and form.is_valid():
        services.belohnung_speichern(form, von=request.user)
        return _weiter(request, "belohnung:katalog")
    return _formular(
        request,
        form,
        titel=_("Belohnung bearbeiten"),
        aktion=reverse("belohnung:bearbeiten", args=[pk]),
    )


@nur_eltern
@require_POST
def belohnung_aktiv(request, pk):
    belohnung = get_object_or_404(Belohnung, pk=pk)
    services.belohnung_aktiv_setzen(belohnung, request.POST.get("aktiv") == "1", von=request.user)
    if _htmx(request):
        return render(request, "belohnung/_zeile.html", {"b": belohnung})
    return redirect("belohnung:katalog")


@nur_eltern
@require_POST
def standard_limit(request):
    form = LimitForm(request.POST)
    if not form.is_valid():
        return redirect("belohnung:katalog")
    services.standard_limit_setzen(form.cleaned_data["betrag"], von=request.user)
    return redirect("belohnung:katalog")


@nur_eltern
@require_POST
def kind_limit(request, kind_id):
    kind = next((k for k in konten_selectors.aktive_kinder() if str(k.pk) == str(kind_id)), None)
    if kind is None:
        raise Http404
    form = KindLimitForm(request.POST, prefix=f"k{kind.pk.hex[:8]}")
    if form.is_valid():
        services.limit_setzen(kind, form.cleaned_data["betrag"], von=request.user)
    return redirect("belohnung:katalog")
