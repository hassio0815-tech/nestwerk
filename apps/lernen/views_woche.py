"""Eltern-Wochenbild und Titel-Schalter (SPEC 21.9, 21.10). Nur Eltern; ein Kind öffnet diese
Seiten nie (403). Pro Kind ein Bild, ohne Vergleich zwischen Geschwistern."""

from datetime import timedelta

from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.kern import zeit
from apps.kern.einstellungen import wert
from apps.konten import selectors as konten
from apps.konten.zugriff import nur_eltern

from . import tagesziel, woche_selectors, woche_services


@nur_eltern
@require_GET
def eltern_woche(request):
    heute = zeit.heute()
    montag = tagesziel.montag(heute)
    vorwoche = request.GET.get("woche") == "vor"
    if vorwoche:
        montag = montag - timedelta(days=7)
    bilder = [woche_selectors.wochenbild(k, heute, montag) for k in konten.aktive_kinder()]
    return render(
        request,
        "lernen/eltern_woche.html",
        {
            "bilder": bilder,
            "montag": montag,
            "vorwoche": vorwoche,
            "titel_an": bool(wert("lernen.titel_anzeigen")),
        },
    )


@nur_eltern
@require_POST
def eltern_titel_schalter(request):
    woche_services.titel_umschalten(request.POST.get("an") == "1")
    return redirect("lernen:eltern_woche")
