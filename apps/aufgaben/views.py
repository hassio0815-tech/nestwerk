"""Eltern-UI der Aufgaben-Stammdaten (HTMX). Alle Views: nur Eltern."""

from datetime import date

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import services, wiederholung
from .forms import AufgabeForm, AufgabenFilterForm, KategorieForm
from .models import Aufgabe, Kategorie, Status


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _weiter(request, url_name):
    """Nach erfolgreichem Speichern zur Liste (HTMX: HX-Redirect, sonst normaler Redirect)."""
    url = reverse(url_name)
    if _htmx(request):
        antwort = HttpResponse(status=204)
        antwort["HX-Redirect"] = url
        return antwort
    return redirect(url)


def _formular(request, form, *, titel, aktion, zurueck):
    """Formular als Teilseite (HTMX) oder als volle Seite."""
    inline = _htmx(request)  # Teilseite in Liste/Katalog: eigene Überschrift + „Abbrechen“
    kontext = {"form": form, "titel": titel, "aktion": aktion, "zurueck": zurueck, "inline": inline}
    vorlage = "aufgaben/_formular.html" if inline else "aufgaben/formular.html"
    return render(request, vorlage, kontext)


# --- Aufgaben ---------------------------------------------------------------------------------


def _gefilterte_aufgaben(request):
    filter_form = AufgabenFilterForm(request.GET)
    qs = Aufgabe.objects.select_related("kategorie", "zugewiesen_an")
    kategorie = status = ""
    if filter_form.is_valid():
        kategorie = filter_form.cleaned_data["kategorie"]
        status = filter_form.cleaned_data["status"]
    if kategorie:
        qs = qs.filter(kategorie=kategorie)
    qs = qs.filter(status=status) if status else qs.exclude(status=Status.BEENDET)
    return filter_form, qs


@nur_eltern
def aufgaben_liste(request):
    filter_form, qs = _gefilterte_aufgaben(request)
    kontext = {"aufgaben": qs, "filter": filter_form}
    vorlage = "aufgaben/_liste.html" if _htmx(request) else "aufgaben/liste.html"
    return render(request, vorlage, kontext)


def _start_vorgabe(request):
    """Vorbelegung der neuen Aufgabe: ``?datum=JJJJ-MM-TT`` (Wochenplan, AP14) setzt das
    Startdatum, ``?art=bei_bedarf`` (Schnell-Knöpfe) die Wiederholung."""
    vorgabe = {}
    if request.GET.get("art") == wiederholung.BEI_BEDARF:
        vorgabe["wiederholungsart"] = wiederholung.BEI_BEDARF
    try:
        vorgabe["start_datum"] = date.fromisoformat(request.GET.get("datum", ""))
    except ValueError:
        pass
    return vorgabe


@nur_eltern
@require_http_methods(["GET", "POST"])
def aufgabe_neu(request):
    form = AufgabeForm(request.POST or None, initial=_start_vorgabe(request))
    if request.method == "POST" and form.is_valid():
        try:
            services.aufgabe_speichern(form, von=aktueller_elternteil(request))
        except ValidationError as fehler:  # z. B. Doppel-Schutz (zwei Formulare gleichzeitig)
            form.add_error(None, fehler)
        else:
            return _weiter(request, "aufgaben:liste")
    knopf = form["wiederholungsart"].value() == wiederholung.BEI_BEDARF
    return _formular(
        request,
        form,
        titel=_("Neue Aufgabe"),
        aktion=reverse("aufgaben:neu"),
        zurueck=reverse("aufgaben:schnellknoepfe" if knopf else "aufgaben:liste"),
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def aufgabe_bearbeiten(request, pk):
    aufgabe = get_object_or_404(Aufgabe, pk=pk)
    form = AufgabeForm(request.POST or None, instance=aufgabe)
    if request.method == "POST" and form.is_valid():
        services.aufgabe_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:liste")
    return _formular(
        request,
        form,
        titel=_("Aufgabe bearbeiten"),
        aktion=reverse("aufgaben:bearbeiten", args=[pk]),
        zurueck=reverse(
            "aufgaben:schnellknoepfe"
            if aufgabe.wiederholungsart == wiederholung.BEI_BEDARF
            else "aufgaben:liste"
        ),
    )


@nur_eltern
@require_POST
def aufgabe_status(request, pk, status):
    aufgabe = get_object_or_404(Aufgabe, pk=pk)
    if status not in Status.values:
        raise Http404
    try:
        services.aufgabe_status_setzen(aufgabe, status, von=aktueller_elternteil(request))
    except ValidationError:
        pass  # beendet bleibt beendet; die Zeile zeigt den tatsächlichen Stand
    if _htmx(request):
        return render(request, "aufgaben/_zeile.html", {"a": aufgabe})
    return redirect("aufgaben:liste")


# --- Kategorien -------------------------------------------------------------------------------


@nur_eltern
def kategorien_liste(request):
    return render(request, "aufgaben/kategorien.html", {"kategorien": Kategorie.objects.all()})


@nur_eltern
@require_http_methods(["GET", "POST"])
def kategorie_neu(request):
    form = KategorieForm(request.POST or None, initial={"aktiv": True, "symbol": "liste"})
    if request.method == "POST" and form.is_valid():
        services.kategorie_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:kategorien")
    return _formular(
        request,
        form,
        titel=_("Neue Kategorie"),
        aktion=reverse("aufgaben:kategorie_neu"),
        zurueck=reverse("aufgaben:kategorien"),
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def kategorie_bearbeiten(request, pk):
    kategorie = get_object_or_404(Kategorie, pk=pk)
    form = KategorieForm(request.POST or None, instance=kategorie)
    if request.method == "POST" and form.is_valid():
        services.kategorie_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:kategorien")
    return _formular(
        request,
        form,
        titel=_("Kategorie bearbeiten"),
        aktion=reverse("aufgaben:kategorie_bearbeiten", args=[pk]),
        zurueck=reverse("aufgaben:kategorien"),
    )
