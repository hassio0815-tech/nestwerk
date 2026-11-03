"""Eltern-Seite für die KI-Anbindung (SPEC 21.6): Anbieter, Zuordnung, Verbindungstest.

Nur Eltern. Der API-Schlüssel wird nie in eine Antwort geschrieben: das Formular zeigt nur
"gesetzt" und lässt das Feld leer (leer = Schlüssel behalten).
"""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.konten.zugriff import nur_eltern

from . import ki_selectors, ki_services
from .ki import KiEinwilligungFehlt
from .ki_texte import fehlertext
from .models import KiAnbieter, KiAufgabe, KiTyp


def _kontext(*, fehler=""):
    anbieter = list(ki_selectors.anbieter_liste())
    zugeordnet = ki_selectors.zuordnungen()
    return {
        "anbieter": anbieter,
        "typen": KiTyp.choices,
        "aufgaben": [
            (wert, text, zugeordnet[wert], ki_selectors.status_von(zugeordnet[wert]).value)
            for wert, text in KiAufgabe.choices
        ],
        "fehler": fehler,
    }


def _seite(request, *, fehler="", status=200):
    return render(request, "lernen/ki.html", _kontext(fehler=fehler), status=status)


def _anbieter(pk):
    return get_object_or_404(KiAnbieter, pk=pk)


@nur_eltern
def ki_seite(request):
    return _seite(request)


@nur_eltern
@require_POST
def anbieter_speichern(request, pk=None):
    p = request.POST
    try:
        ki_services.anbieter_speichern(
            anbieter=_anbieter(pk) if pk else None,
            name=p.get("name", ""),
            typ=p.get("typ", ""),
            basis_url=p.get("basis_url", ""),
            modell=p.get("modell", ""),
            api_key=p.get("api_key", ""),
        )
    except ValidationError as exc:
        return _seite(request, fehler=" ".join(exc.messages), status=400)
    return redirect("lernen:ki")


@nur_eltern
@require_POST
def anbieter_aktivieren(request, pk):
    try:
        ki_services.anbieter_aktivieren(
            _anbieter(pk), einwilligung=request.POST.get("einwilligung") == "1"
        )
    except KiEinwilligungFehlt:
        return _seite(
            request,
            fehler=_("Für einen Cloud-Anbieter braucht es zuerst eure Einwilligung (Häkchen)."),
            status=400,
        )
    return redirect("lernen:ki")


@nur_eltern
@require_POST
def anbieter_deaktivieren(request, pk):
    ki_services.anbieter_deaktivieren(_anbieter(pk))
    return redirect("lernen:ki")


@nur_eltern
@require_POST
def anbieter_testen(request, pk):
    anbieter = _anbieter(pk)
    ergebnis = ki_services.verbindung_testen(anbieter)
    return render(
        request,
        "lernen/_ki_test.html",
        {
            "a": anbieter,
            "ergebnis": ergebnis,
            "fehlertext": fehlertext(ergebnis.art) if ergebnis.art else "",
        },
    )


@nur_eltern
@require_POST
def zuordnung_setzen(request):
    p = request.POST
    anbieter = None
    if p.get("anbieter"):
        anbieter = get_object_or_404(KiAnbieter, pk=p["anbieter"])
    try:
        ki_services.zuordnung_setzen(p.get("aufgabe", ""), anbieter)
    except ValidationError as exc:
        return _seite(request, fehler=" ".join(exc.messages), status=400)
    return redirect("lernen:ki")
