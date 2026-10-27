"""Wochenplan für Eltern (AP14): Ansicht, Verschieben per Ziehen oder Formular."""

from datetime import date

from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.kern.sprache import uebersetzt
from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import wochenplan


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _antwort(request, woche, *, meldung="", fehler="", status=200):
    kontext = wochenplan.woche_daten(woche)
    kontext.update(meldung=meldung, fehler=fehler)
    vorlage = "aufgaben/_wochenplan.html" if _htmx(request) else "aufgaben/wochenplan.html"
    return render(request, vorlage, kontext, status=status)


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
    return _antwort(
        request,
        woche,
        meldung=_("„%(titel)s“ verschoben.") % {"titel": uebersetzt(inst.titel_snapshot)},
    )
