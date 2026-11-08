"""Wochenplan für Eltern (AP14): Ansicht, Verschieben per Ziehen oder Formular."""

from datetime import date

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.kern.sprache import uebersetzt
from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import wochenplan
from .models import AufgabenInstanz


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _antwort(request, woche, *, meldung="", fehler="", status=200):
    kontext = wochenplan.woche_daten(woche)
    kontext.update(meldung=meldung, fehler=fehler)
    vorlage = "aufgaben/_wochenplan.html" if _htmx(request) else "aufgaben/wochenplan.html"
    return render(request, vorlage, kontext, status=status)


def _erfolg(request, woche, meldung):
    """Erfolg: HTMX bekommt den Wochenplan samt Meldung, ein Formular ohne JavaScript einen
    Redirect auf die Woche (POST/Redirect/GET: Neuladen schickt nichts ein zweites Mal)."""
    if _htmx(request):
        return _antwort(request, woche, meldung=meldung)
    return redirect(f"{reverse('aufgaben:wochenplan')}?datum={woche.montag.isoformat()}")


@nur_eltern
def wochenplan_ansicht(request):
    return _antwort(request, wochenplan.woche_aus_datum(request.GET.get("datum")))


@nur_eltern
@require_POST
def instanz_verschieben(request, pk):
    woche = wochenplan.woche_aus_datum(request.POST.get("woche"))
    try:
        datum = date.fromisoformat(request.POST.get("datum", ""))
    except ValueError:
        return _antwort(request, woche, fehler=_("Bitte ein gültiges Datum wählen."), status=400)
    try:
        reihenfolge = wochenplan.reihenfolge_lesen(request.POST.get("reihenfolge"))
        inst = wochenplan.verschieben(
            pk, datum, von=aktueller_elternteil(request), reihenfolge=reihenfolge
        )
    except ValueError as exc:
        return _antwort(request, woche, fehler=str(exc), status=409)
    # Gezielte Woche = Woche des neuen Tages, falls aus dem Formular verschoben wurde
    return _erfolg(
        request, woche, _("„%(titel)s“ verschoben.") % {"titel": uebersetzt(inst.titel_snapshot)}
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def instanz_loeschen(request, pk):
    """Löschen per ⓧ. POST: ``modus`` = ``tag`` (nur diese Karte) oder ``serie`` (ganze Aufgabe).
    GET: Bestätigungsseite für den Fall ohne JavaScript (mit JS öffnet das ⓧ ein Popup)."""
    daten = request.POST if request.method == "POST" else request.GET
    woche = wochenplan.woche_aus_datum(daten.get("woche"))
    if request.method == "GET":
        inst = get_object_or_404(AufgabenInstanz.objects.select_related("aufgabe"), pk=pk)
        if not wochenplan.loeschen_moeglich(inst):
            return _antwort(
                request,
                woche,
                fehler=_("Diese Aufgabe kann nicht mehr gelöscht werden."),
                status=409,
            )
        kontext = {
            "instanz": inst,
            "serie": wochenplan.ist_serie(inst.aufgabe),
            "vorgang": wochenplan.vorgang_loeschbar(inst),
            "woche_montag": woche.montag,
        }
        return render(request, "aufgaben/wochenplan_loeschen.html", kontext)
    modus = daten.get("modus", "tag")
    try:
        inst = wochenplan.loeschen(pk, modus, von=aktueller_elternteil(request))
    except ValueError as exc:
        return _antwort(request, woche, fehler=str(exc), status=409)
    meldung = (
        _("„%(titel)s“ gelöscht, die ganze Serie ist beendet.")
        if modus == "serie" and wochenplan.ist_serie(inst.aufgabe)
        else _("„%(titel)s“ gelöscht.")
    ) % {"titel": uebersetzt(inst.titel_snapshot)}
    return _erfolg(request, woche, meldung)
