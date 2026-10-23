"""Eltern-UI der Aufgaben-Stammdaten (HTMX). Alle Views: nur Eltern."""

from datetime import date

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import services
from .forms import AufgabeForm, AufgabenFilterForm, KategorieForm, VorlageForm
from .models import Aufgabe, Kategorie, Status, Vorlage


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
    kontext = {"form": form, "titel": titel, "aktion": aktion, "zurueck": zurueck}
    vorlage = "aufgaben/_formular.html" if _htmx(request) else "aufgaben/formular.html"
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
    """Wochenplan (AP14): ``?datum=JJJJ-MM-TT`` füllt das Startdatum der neuen Aufgabe vor."""
    try:
        return {"start_datum": date.fromisoformat(request.GET.get("datum", ""))}
    except ValueError:
        return {}


@nur_eltern
@require_http_methods(["GET", "POST"])
def aufgabe_neu(request):
    form = AufgabeForm(request.POST or None, initial=_start_vorgabe(request))
    if request.method == "POST" and form.is_valid():
        services.aufgabe_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:liste")
    return _formular(
        request,
        form,
        titel="Neue Aufgabe",
        aktion=reverse("aufgaben:neu"),
        zurueck=reverse("aufgaben:liste"),
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
        titel="Aufgabe bearbeiten",
        aktion=reverse("aufgaben:bearbeiten", args=[pk]),
        zurueck=reverse("aufgaben:liste"),
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


# --- Vorlagen (Bibliothek) --------------------------------------------------------------------


@nur_eltern
def vorlagen_liste(request):
    return render(
        request,
        "aufgaben/vorlagen.html",
        {"vorlagen": Vorlage.objects.select_related("kategorie")},
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def vorlage_neu(request):
    form = VorlageForm(request.POST or None, initial={"aktiv": True})
    if request.method == "POST" and form.is_valid():
        services.vorlage_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:vorlagen")
    return _formular(
        request,
        form,
        titel="Neue Vorlage",
        aktion=reverse("aufgaben:vorlage_neu"),
        zurueck=reverse("aufgaben:vorlagen"),
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def vorlage_bearbeiten(request, pk):
    vorlage = get_object_or_404(Vorlage, pk=pk)
    form = VorlageForm(request.POST or None, instance=vorlage)
    if request.method == "POST" and form.is_valid():
        services.vorlage_speichern(form, von=aktueller_elternteil(request))
        return _weiter(request, "aufgaben:vorlagen")
    return _formular(
        request,
        form,
        titel="Vorlage bearbeiten",
        aktion=reverse("aufgaben:vorlage_bearbeiten", args=[pk]),
        zurueck=reverse("aufgaben:vorlagen"),
    )


@nur_eltern
@require_POST
def vorlage_loeschen(request, pk):
    vorlage = get_object_or_404(Vorlage, pk=pk)
    services.vorlage_loeschen(vorlage, von=aktueller_elternteil(request))
    if _htmx(request):
        return HttpResponse("")
    return redirect("aufgaben:vorlagen")


@nur_eltern
def vorlage_als_aufgabe(request, pk):
    """Vorlage -> Aufgabe: Formular mit Werten der Vorlage vorausgefüllt (Speichern legt an)."""
    vorlage = get_object_or_404(Vorlage, pk=pk)
    plan = vorlage.plan
    start = {
        "titel": vorlage.titel,
        "punkte": vorlage.punkte,
        "beschreibung": vorlage.beschreibung,
        "freigabeart": vorlage.freigabeart,
        "kategorie": vorlage.kategorie_id,
        "vorlage": vorlage.pk,
        "wiederholungsart": plan.art,
        "wochentage": [str(t) for t in plan.wochentage_liste],
        "intervall_tage": plan.intervall_tage,
        "fenster_von": plan.fenster_von,
        "fenster_bis": plan.fenster_bis,
        "fenster_tage": plan.fenster_tage,
        "limit_anzahl": plan.limit_anzahl,
        "limit_zeitraum": plan.limit_zeitraum,
    }
    form = AufgabeForm(initial=start)
    return _formular(
        request,
        form,
        titel=f"Aufgabe aus Vorlage „{vorlage.titel}“",
        aktion=reverse("aufgaben:neu"),
        zurueck=reverse("aufgaben:vorlagen"),
    )


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
        titel="Neue Kategorie",
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
        titel="Kategorie bearbeiten",
        aktion=reverse("aufgaben:kategorie_bearbeiten", args=[pk]),
        zurueck=reverse("aufgaben:kategorien"),
    )
