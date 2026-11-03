"""Seiten des Tutors (SPEC 21.3, 21.4).

Kind: eigene Gespräche (HTMX-Chat). Fremde Gespräche sind ein 404. Ist der Tutor aus oder hat die
Aufgabe ``tutor`` keinen aktiven Anbieter, zeigen die Seiten einen freundlichen Hinweis und keine
Eingabe. Eltern: Schalter für die ganze Familie, Protokoll je Kind (nur lesen), Löschen.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.kern.einstellungen import wert
from apps.konten import selectors as konten
from apps.konten.zugriff import aktuelles_kind, nur_eltern, nur_kind

from . import material_selectors, tutor_selectors, tutor_services
from .models import GespraechStatus, MaterialStatus, TutorGespraech
from .tutor_services import TutorFehler


def _hx(request):
    return request.headers.get("HX-Request") == "true"


# --- Kind ---------------------------------------------------------------------------------------


def _worum_optionen(kind):
    """Material (bereit) und Themen, zu denen ein Gespräch beginnen kann."""
    from .views import _fach_optionen

    material = [
        m
        for m in material_selectors.materialien(kind).filter(status=MaterialStatus.BEREIT)
        if m.text
    ]
    return material, _fach_optionen(kind)


def _start_kontext(kind, *, fehler=""):
    material, optionen = _worum_optionen(kind)
    status = tutor_selectors.status()
    return {
        "status": status,
        "bereit": status is tutor_selectors.TutorStatus.BEREIT,
        "offene": tutor_selectors.offene_gespraeche(kind),
        "material": material,
        "optionen": optionen,
        "fehler": fehler,
    }


@nur_kind
def start(request):
    return render(request, "lernen/tutor_start.html", _start_kontext(aktuelles_kind(request)))


def _worum_lesen(kind, wert_):
    """``material:<id>`` oder ``thema:<id>`` -> (Material, Thema); leer = ohne Bezug."""
    art, _sep, nr = str(wert_ or "").partition(":")
    if not nr.isdigit():
        return None, None
    if art == "material":
        material = material_selectors.material_von(kind, int(nr))
        return (material, None) if material and material.text else (None, None)
    if art == "thema":
        sichtbar = {t.pk: t for _fach, themen in _worum_optionen(kind)[1] for t in themen}
        return None, sichtbar.get(int(nr))
    return None, None


@nur_kind
@require_POST
def neu(request):
    kind = aktuelles_kind(request)
    material, thema = _worum_lesen(kind, request.POST.get("worum"))
    try:
        g = tutor_services.gespraech_starten(kind, material=material, thema=thema)
    except TutorFehler as fehler:
        return render(
            request, "lernen/tutor_start.html", _start_kontext(kind, fehler=str(fehler)), status=400
        )
    return redirect("lernen:tutor_gespraech", pk=g.pk)


def _eigenes(request, pk):
    kind = aktuelles_kind(request)
    g = tutor_selectors.gespraech(kind, pk)
    if g is None:
        raise Http404
    return g


def _chat(request, g, *, fehler="", eingabe=None):
    nachrichten = list(tutor_selectors.nachrichten(g))
    letzte = nachrichten[-1] if nachrichten else None
    status = tutor_selectors.status()
    offen = g.status == GespraechStatus.OFFEN
    kontext = {
        "g": g,
        "nachrichten": nachrichten,
        "fehler": fehler,
        "eingabe": eingabe or {},  # bei Fehler: das Getippte bleibt stehen
        "status": status,
        "aktiv": offen and status is tutor_selectors.TutorStatus.BEREIT,
        "mehr_hilfe_moeglich": g.hilfestufe < tutor_services.HILFESTUFE_MAX,
        "mehr_hilfe_empfohlen": bool(
            letzte and letzte.empfohlene_stufe and letzte.empfohlene_stufe > g.hilfestufe
        ),
        "versuch_moeglich": tutor_selectors.bewerten_bereit(),
        "max_zeichen": wert("lernen.tutor_laenge_nachricht"),
        "stufen": range(1, tutor_services.HILFESTUFE_MAX + 1),
    }
    vorlage = "lernen/_tutor_chat.html" if _hx(request) else "lernen/tutor.html"
    return render(request, vorlage, kontext)


@nur_kind
def gespraech(request, pk):
    return _chat(request, _eigenes(request, pk))


def _chat_aktion(funktion):
    """Fehler des Tutors (Limit, zu lang, aus ...) zeigen das Gespräch mit freundlichem Hinweis."""

    def umhuellung(request, pk):
        g = _eigenes(request, pk)
        try:
            funktion(request, g)
        except TutorFehler as fehler:
            return _chat(request, g, fehler=str(fehler), eingabe=request.POST)
        g.refresh_from_db()
        return _chat(request, g)

    umhuellung.__name__ = funktion.__name__
    return nur_kind(require_POST(umhuellung))


@_chat_aktion
def senden(request, g):
    tutor_services.nachricht_senden(g, request.POST.get("text", ""))


@_chat_aktion
def mehr_hilfe(request, g):
    tutor_services.mehr_hilfe(g)


@_chat_aktion
def versuch(request, g):
    tutor_services.versuch_pruefen(
        g, request.POST.get("versuch", ""), request.POST.get("aufgabe", "")
    )


@nur_kind
@require_POST
def beenden(request, pk):
    tutor_services.gespraech_beenden(_eigenes(request, pk))
    return redirect("lernen:tutor")


# --- Eltern -------------------------------------------------------------------------------------


def _eltern_kontext(*, fehler=""):
    kinder = list(konten.aktive_kinder())
    zeilen = []
    for kind in kinder:
        gespraeche = list(tutor_selectors.protokoll(kind))
        zeilen.append(
            {
                "kind": kind,
                "gespraeche": gespraeche,
                "zaehler": tutor_selectors.hilfestufen_zaehler(kind),
            }
        )
    return {
        "aktiv": bool(wert("lernen.tutor_aktiv")),
        "status": tutor_selectors.status(),
        "zeilen": zeilen,
        "tage": wert("lernen.tutor_aufbewahrung_tage"),
        "fehler": fehler,
    }


@nur_eltern
def eltern_seite(request):
    return render(request, "lernen/eltern_tutor.html", _eltern_kontext())


@nur_eltern
@require_POST
def eltern_schalter(request):
    tutor_services.tutor_umschalten(request.POST.get("an") == "1")
    return redirect("lernen:eltern_tutor")


@nur_eltern
@require_GET
def eltern_gespraech(request, pk):
    g = tutor_selectors.fuer_eltern(pk)
    if g is None:
        raise Http404
    return render(
        request,
        "lernen/eltern_tutor_gespraech.html",
        {"g": g, "nachrichten": tutor_selectors.nachrichten(g)},
    )


@nur_eltern
@require_POST
def eltern_loeschen(request, pk):
    g = get_object_or_404(TutorGespraech.objects.select_related("kind"), pk=pk)
    tutor_services.gespraech_loeschen(g)
    return redirect("lernen:eltern_tutor")
