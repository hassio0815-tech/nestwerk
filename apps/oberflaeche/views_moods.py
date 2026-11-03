"""Moods verwalten (Eltern): Vorschläge der Kinder entscheiden, Katalog-Moods ausblenden,
eigene Moods ergänzen. Zugelassene und eigene Moods gelten für alle Kinder."""

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST

from apps.konten import moods
from apps.konten import selectors as konten_selectors
from apps.konten import services as konten_services
from apps.konten.zugriff import nur_eltern

from . import mood

MELDUNGEN = {
    "zugelassen": gettext_lazy("Vorschlag zugelassen. Der Mood gilt jetzt für alle Kinder."),
    "abgelehnt": gettext_lazy("Vorschlag abgelehnt."),
    "neu": gettext_lazy("Mood ergänzt."),
    "entfernt": gettext_lazy("Mood entfernt."),
    "katalog": gettext_lazy("Auswahl gespeichert."),
}


def _meldung(exc):
    return " ".join(exc.messages)


def _seite(request, *, fehler="", vorgabe="", status=200):
    aus = konten_selectors.moods_ausgeblendet()
    gruppen = [
        {"name": name, "moods": [m for m in moods.KATALOG if m.gruppe == schluessel]}
        for schluessel, name in moods.GRUPPEN
    ]
    kontext = {
        "vorschlaege": list(konten_selectors.mood_vorschlaege()),
        "eigene": list(konten_selectors.moods_eigene()),
        "gruppen": gruppen,
        "ausgeblendet": aus,
        "fehler": fehler,
        "vorgabe": vorgabe,
        "ok": MELDUNGEN.get(request.GET.get("ok", ""), ""),
        "text_max": moods.TEXT_MAX,
    }
    return render(request, "oberflaeche/eltern_moods.html", kontext, status=status)


def _fertig(code):
    return redirect(f"{reverse('oberflaeche:eltern_moods')}?ok={code}")


@nur_eltern
@require_GET
def uebersicht(request):
    return _seite(request)


def _entscheiden(request, pk, zulassen):
    vorschlag = get_object_or_404(konten_selectors.mood_vorschlaege(), pk=pk)
    try:
        mood.entscheiden(vorschlag, zulassen, von=request.user)
    except ValidationError as exc:
        return _seite(request, fehler=_meldung(exc), status=422)
    return _fertig("zugelassen" if zulassen else "abgelehnt")


@nur_eltern
@require_POST
def zulassen(request, pk):
    return _entscheiden(request, pk, True)


@nur_eltern
@require_POST
def ablehnen(request, pk):
    return _entscheiden(request, pk, False)


@nur_eltern
@require_POST
def neu(request):
    try:
        konten_services.mood_eigen_anlegen(request.POST.get("text", ""), von=request.user)
    except ValidationError as exc:
        return _seite(
            request, fehler=_meldung(exc), vorgabe=request.POST.get("text", ""), status=422
        )
    return _fertig("neu")


@nur_eltern
@require_POST
def entfernen(request, pk):
    eigen = get_object_or_404(konten_selectors.moods_eigene(), pk=pk)
    konten_services.mood_eigen_entfernen(eigen, von=request.user)
    return _fertig("entfernt")


@nur_eltern
@require_POST
def katalog(request, schluessel):
    """``ausblenden=1`` blendet den Katalog-Mood aus, sonst wieder ein."""
    try:
        konten_services.mood_katalog_ausblenden(
            schluessel, request.POST.get("ausblenden") == "1", von=request.user
        )
    except ValidationError:
        return redirect(reverse("oberflaeche:eltern_moods"))
    return _fertig("katalog")
