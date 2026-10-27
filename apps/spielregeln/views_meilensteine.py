"""Eltern-Verwaltung der Meilensteine (AP23 offen, umgesetzt mit AP27): Liste, ein/aus,
Bedingungen ansehen und anpassen. Regeln legen Module an (z. B. ``sondertag``)."""

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.kern import registry as kern_registry
from apps.kern.sprache import uebersetzt
from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import abzeichen as engine
from .models import MeilensteinRegel, Vergleich
from .registry import hat_bereiche


def _seite(request, status=200, fehler=""):
    return render(
        request,
        "spielregeln/meilensteine.html",
        {
            "fehler": fehler,
            "zeilen": engine.meilenstein_uebersicht(),
            "metriken": [
                {"m": m, "bereiche": hat_bereiche(m.schluessel)} for m in kern_registry.metriken()
            ],
            "vergleiche": Vergleich.choices,
        },
        status=status,
    )


@nur_eltern
def meilensteine(request):
    return _seite(request)


def _bedingungen(request) -> list[dict]:
    """Zeilen des Formulars; Zeilen ohne Metrik fallen weg (leere Zeile = "neue Bedingung")."""
    p = request.POST
    ergebnis = []
    for metrik, vergleich, wert in zip(
        p.getlist("metrik"), p.getlist("vergleich"), p.getlist("wert"), strict=False
    ):
        if metrik.strip():
            ergebnis.append({"metrik": metrik.strip(), "vergleich": vergleich, "wert": wert})
    return ergebnis


@nur_eltern
@require_POST
def meilenstein_aendern(request, pk):
    regel = get_object_or_404(MeilensteinRegel, pk=pk)
    try:
        engine.meilenstein_speichern(
            regel,
            von=aktueller_elternteil(request),
            name=request.POST.get("name", ""),
            beschreibung=request.POST.get("beschreibung", ""),
            bedingungen=_bedingungen(request),
        )
    except engine.AbzeichenFehler as fehler:
        return _seite(request, status=400, fehler=f"{uebersetzt(regel.name)}: {fehler}")
    return redirect("spielregeln:meilensteine")


@nur_eltern
@require_POST
def meilenstein_aktiv(request, pk):
    regel = get_object_or_404(MeilensteinRegel, pk=pk)
    engine.meilenstein_aktiv_setzen(
        regel, request.POST.get("aktiv") == "1", von=aktueller_elternteil(request)
    )
    return redirect("spielregeln:meilensteine")
