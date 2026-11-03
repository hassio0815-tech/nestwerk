"""Eltern-Seite "Kinder und Leistungsstufen": Klassenstufe, Schulform, Leistungsstufe je Fach und
"Fragen aus Uploads sofort nutzbar" nachträglich ändern, dazu der Knopf "Neues Schuljahr".

Nur Eltern. Alle Änderungen gehen über dieselben Services wie der Einrichtungs-Assistent
(``einrichtung_services``). Ein Formular ändert immer genau ein Kind."""

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.kern import audit
from apps.konten import selectors as konten_selectors
from apps.konten.zugriff import nur_eltern

from . import einrichtung_services as dienste
from . import selectors


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _kontext(*, fehler=None, gespeichert=None, schuljahr=None):
    """``fehler``: (kind_pk, [Texte]); ``gespeichert``: kind_pk; ``schuljahr``: (neu, gleich)."""
    faecher = [(f.schluessel, f.name) for f in selectors.faecher()]
    zeilen = []
    for p in dienste.kinder_profile():
        zeilen.append(
            {
                "kind": p.kind,
                "werte": p,
                "stufen": [(k, n, p.stufen.get(k, "")) for k, n in faecher],
                "fehler": fehler[1] if fehler and fehler[0] == p.kind.pk else [],
                "gespeichert": gespeichert == p.kind.pk,
            }
        )
    return {
        "zeilen": zeilen,
        "stufenwahl": list(dienste.STUFEN.items()),
        "schuljahr": schuljahr,
    }


def _antwort(request, kontext, status=200):
    vorlage = "lernen/_kinder_liste.html" if _htmx(request) else "lernen/eltern_kinder.html"
    return render(request, vorlage, kontext, status=status)


@nur_eltern
@require_GET
def eltern_kinder(request):
    return render(request, "lernen/eltern_kinder.html", _kontext())


@nur_eltern
@require_POST
def eltern_kind_speichern(request, pk):
    kind = get_object_or_404(konten_selectors.aktive_kinder(), pk=pk)
    p = request.POST
    faecher = [f.schluessel for f in selectors.faecher()]
    try:
        klasse, schulform, stufen = dienste.kind_pruefen(
            klassenstufe=p.get("klasse", ""),
            schulform=p.get("schulform", ""),
            stufen={k: p.get(f"stufe-{k}", "") for k in faecher},
        )
        dienste.kind_speichern(
            kind,
            klassenstufe=klasse,
            schulform=schulform,
            stufen=stufen,
            sofort=p.get("freigabe") == "sofort",
            akteur=audit.AKTUELL,
            aktion="lernen.kind_geaendert",
        )
    except ValidationError as exc:
        return _antwort(request, _kontext(fehler=(kind.pk, exc.messages)), status=400)
    return _antwort(request, _kontext(gespeichert=kind.pk))


@nur_eltern
@require_GET
def eltern_schuljahr(request):
    mit_klasse, anhebbar, oben = dienste.schuljahr_vorschau()
    return render(
        request,
        "lernen/eltern_schuljahr.html",
        {
            "mit_klasse": mit_klasse,
            "anhebbar": anhebbar,
            "oben": oben,
            "klasse_max": dienste.KLASSE_MAX,
        },
    )


@nur_eltern
@require_POST
def eltern_schuljahr_bestaetigen(request):
    if request.POST.get("bestaetigt") != "1":
        return HttpResponseBadRequest(_("Bitte das neue Schuljahr bestätigen."))
    ergebnis = dienste.schuljahr_wechsel()
    return _antwort(request, _kontext(schuljahr=ergebnis))
