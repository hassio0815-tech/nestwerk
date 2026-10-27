"""Eltern-UI für Pausen (SPEC 7): Seite mit Formular (Kind/Familie, Zeitraum) und Schnell-Schalter
aus der Dashboard-Kachel. Ränge-Verwaltung (AP22): Namen, Schwellen, Mindestwochen,
Kalibrierungsfaktor global/je Kind (K3). Abzeichen (AP23): anlegen, ändern, (de)aktivieren,
Übersicht je Kind. Nur Eltern."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.kern import registry as kern_registry
from apps.kern import zeit
from apps.kern.sprache import uebersetzt
from apps.konten import selectors as konten
from apps.konten.zugriff import aktueller_elternteil, nur_eltern

from . import abzeichen as engine
from . import selectors, services
from .forms import FAMILIE, PauseForm
from .models import AbzeichenDefinition, Pause, Rang, Vergleich, Wiederholbar
from .raenge_start import RAENGE
from .registry import hat_bereiche

ZIELE = {"heim": "konten:eltern_heim", "pausen": "spielregeln:pausen"}


def _zurueck(request):
    return redirect(ZIELE.get(request.POST.get("zurueck"), "spielregeln:pausen"))


def pausen_kachel_kontext():
    """Zeilen für die Eltern-Kachel: Familie + je Kind die laufende Pause."""
    heute = zeit.heute()
    familie = selectors.laufende_pause_von(None, heute)
    zeilen = []
    for kind in konten.aktive_kinder():
        zeilen.append(
            {
                "kind": kind,
                "eigene": selectors.laufende_pause_von(kind, heute),
                "stand": selectors.stand(kind),
            }
        )
    return {"familie": familie, "zeilen": zeilen, "familie_wert": FAMILIE}


@nur_eltern
def pausen(request):
    form = PauseForm()
    return _seite(request, form)


def _seite(request, form, status=200, fehler=""):
    uebersicht = selectors.pausen_uebersicht()
    kontext = {
        "form": form,
        "fehler": fehler,
        "pausen_kachel": {**pausen_kachel_kontext(), "zurueck": "pausen"},
        "abschnitte": [
            (_("Laufend"), uebersicht.laufend, "laufend"),
            (_("Geplant"), uebersicht.geplant, "geplant"),
            (_("Vorbei"), uebersicht.vergangen, "vorbei"),
        ],
    }
    return render(request, "spielregeln/pausen.html", kontext, status=status)


@nur_eltern
@require_POST
def pause_neu(request):
    form = PauseForm(request.POST)
    if not form.is_valid():
        return _seite(request, form, status=400)
    try:
        services.pause_setzen(
            form.ziel_kind(),
            von=aktueller_elternteil(request),
            ab=form.cleaned_data["von"],
            bis=form.cleaned_data["bis"],
            grund=form.cleaned_data["grund"],
        )
    except services.SpielregelnFehler as fehler:
        form.add_error(None, str(fehler))
        return _seite(request, form, status=400)
    return redirect("spielregeln:pausen")


def _ziel(request):
    ziel = request.POST.get("ziel", "")
    if ziel == FAMILIE:
        return None
    kind = next((k for k in konten.aktive_kinder() if str(k.pk) == ziel), None)
    if kind is None:
        raise Http404
    return kind


@nur_eltern
@require_POST
def schalter(request):
    """Schnell-Schalter: ``aktion=an`` (Pause ab heute, offen) oder ``aus`` (laufende beenden)."""
    ziel = _ziel(request)
    eltern = aktueller_elternteil(request)
    try:
        if request.POST.get("aktion") == "an":
            services.pause_setzen(ziel, von=eltern)
        else:
            services.pausen_beenden_fuer(ziel, von=eltern)
    except services.SpielregelnFehler as fehler:
        return _seite(request, PauseForm(), status=400, fehler=str(fehler))
    return _zurueck(request)


@nur_eltern
@require_POST
def pause_beenden(request, pk):
    pause = get_object_or_404(Pause, pk=pk)
    try:
        services.pause_beenden(pause, von=aktueller_elternteil(request))
    except services.SpielregelnFehler as fehler:
        return _seite(request, PauseForm(), status=400, fehler=str(fehler))
    return _zurueck(request)


@nur_eltern
@require_POST
def pause_loeschen(request, pk):
    pause = get_object_or_404(Pause, pk=pk)
    try:
        services.pause_loeschen(pause, von=aktueller_elternteil(request))
    except services.SpielregelnFehler as fehler:
        return _seite(request, PauseForm(), status=400, fehler=str(fehler))
    return _zurueck(request)


# --- Ränge (AP22) ---------------------------------------------------------------------------


def raenge_kachel_kontext():
    return {
        "zeilen": [
            {
                "kind": kind,
                "f": selectors.rang_fortschritt(kind),
                "faktor": selectors.kind_faktor(kind),
            }
            for kind in konten.aktive_kinder()
        ]
    }


def _raenge_seite(request, status=200, fehler=""):
    faktor = selectors.globaler_faktor()
    kontext = {
        "fehler": fehler,
        "raenge": [
            {"rang": r, "schwelle": selectors.wirksame_schwelle(r, faktor)}
            for r in selectors.raenge()
        ],
        "globaler_faktor": faktor,
        "raenge_kachel": raenge_kachel_kontext(),
    }
    return render(request, "spielregeln/raenge.html", kontext, status=status)


@nur_eltern
def raenge(request):
    return _raenge_seite(request)


@nur_eltern
@require_POST
def rang_aendern(request, pk):
    rang = get_object_or_404(Rang, pk=pk)
    try:
        services.rang_aendern(
            rang,
            von=aktueller_elternteil(request),
            name=request.POST.get("name", ""),
            xp_schwelle=request.POST.get("xp_schwelle", ""),
            min_aktive_wochen=request.POST.get("min_aktive_wochen", ""),
        )
    except services.RangFehler as fehler:
        return _raenge_seite(request, status=400, fehler=f"{uebersetzt(rang.name)}: {fehler}")
    return redirect("spielregeln:raenge")


@nur_eltern
@require_POST
def kalibrierung(request):
    ziel = request.POST.get("ziel", "")
    kind = None
    if ziel != "global":
        kind = next((k for k in konten.aktive_kinder() if str(k.pk) == ziel), None)
        if kind is None:
            raise Http404
    faktor = request.POST.get("faktor", "").strip()
    try:
        services.kalibrierung_setzen(
            kind,
            faktor or None,
            von=aktueller_elternteil(request),
            notiz=request.POST.get("notiz", ""),
        )
    except services.RangFehler as fehler:
        return _raenge_seite(request, status=400, fehler=str(fehler))
    return redirect("spielregeln:raenge")


# --- Abzeichen (AP23) -----------------------------------------------------------------------


def _abzeichen_seite(request, status=200, fehler=""):
    kontext = {
        "fehler": fehler,
        "zeilen": engine.eltern_uebersicht(),
        "definitionen": [
            {"d": d, "symbol": selectors.symbol(d), "anzahl": d.verleihungen.count()}
            for d in selectors.definitionen()
        ],
        "metriken": [
            {"m": m, "bereiche": hat_bereiche(m.schluessel)} for m in kern_registry.metriken()
        ],
        "vergleiche": Vergleich.choices,
        "wiederholungen": Wiederholbar.choices,
    }
    return render(request, "spielregeln/abzeichen.html", kontext, status=status)


@nur_eltern
def abzeichen(request):
    return _abzeichen_seite(request)


def _abzeichen_daten(request):
    p = request.POST
    return {
        "name": p.get("name", ""),
        "beschreibung": p.get("beschreibung", ""),
        "metrik": p.get("metrik", ""),
        "vergleich": p.get("vergleich", ">="),
        "schwelle": p.get("schwelle", ""),
        "wiederholbar": p.get("wiederholbar", "einmalig"),
        "reihenfolge": p.get("reihenfolge") or None,
    }


@nur_eltern
@require_POST
def abzeichen_neu(request):
    try:
        services.abzeichen_speichern(
            None, von=aktueller_elternteil(request), **_abzeichen_daten(request)
        )
    except services.AbzeichenFehler as fehler:
        return _abzeichen_seite(request, status=400, fehler=str(fehler))
    return redirect("spielregeln:abzeichen")


@nur_eltern
@require_POST
def abzeichen_aendern(request, pk):
    definition = get_object_or_404(AbzeichenDefinition, pk=pk)
    try:
        services.abzeichen_speichern(
            definition,
            von=aktueller_elternteil(request),
            aktiv=definition.aktiv,
            **_abzeichen_daten(request),
        )
    except services.AbzeichenFehler as fehler:
        return _abzeichen_seite(
            request, status=400, fehler=f"{uebersetzt(definition.name)}: {fehler}"
        )
    return redirect("spielregeln:abzeichen")


@nur_eltern
@require_POST
def abzeichen_aktiv(request, pk):
    definition = get_object_or_404(AbzeichenDefinition, pk=pk)
    services.abzeichen_aktiv_setzen(
        definition, request.POST.get("aktiv") == "1", von=aktueller_elternteil(request)
    )
    return redirect("spielregeln:abzeichen")


@require_GET
def abzeichen_galerie(request):
    """Entwickler-Galerie (AP28, nur DEBUG): alle Abzeichen-Grafiken, je Rang ab 2 eine Variante.
    Zeigt keine Kinderdaten, daher ohne Anmeldung wie ``avatar/galerie``."""
    if not settings.DEBUG:
        raise Http404
    stufen = [stufe for stufe, *_ in RAENGE if stufe >= 2]
    zeilen = []
    for d in selectors.definitionen():
        varianten = [("", selectors.symbol(d))]  # Grundgrafik (auch Vorschau "Als Nächstes")
        if d.gruppe == "rang":
            varianten += [
                (_("Rang %(n)s") % {"n": n}, selectors.symbol(d, f"rang-{n}")) for n in stufen
            ]
        zeilen.append({"d": d, "varianten": varianten})
    return render(request, "spielregeln/abzeichen_galerie.html", {"zeilen": zeilen})
