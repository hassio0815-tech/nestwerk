"""Meine Einstellungen (Kind): Name, Spitzname, Code, Mood und Mood-Vorschläge.

Nur das angemeldete Kind ändert sich selbst (``request.user``; es gibt keine Kind-ID in den URLs).
Der Code wird nur mit dem alten Code geändert; Fehlversuche zählen wie bei der Anmeldung."""

from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_GET, require_POST

from apps.konten import moods
from apps.konten import selectors as konten_selectors
from apps.konten import services as konten_services
from apps.konten.zugriff import nur_kind

from . import mood

MELDUNGEN = {
    "profil": gettext_lazy("Gespeichert."),
    "code": gettext_lazy("Dein Code ist geändert."),
    "mood": gettext_lazy("Mood gespeichert."),
    "vorschlag": gettext_lazy("Danke! Die Eltern schauen sich deinen Vorschlag an."),
}


def _meldung(exc):
    return " ".join(exc.messages)


def _seite(request, *, fehler=None, vorgaben=None, status=200):
    kind = request.user
    auswahl = konten_selectors.mood_auswahl(moods.KIND)
    gruppen = konten_selectors.mood_gruppen(moods.KIND)
    kontext = {
        "gruppen": gruppen,
        "mood_aktuell": kind.mood if kind.mood in {s for s, _t, _g in auswahl} else "",
        "offene": list(konten_selectors.mood_vorschlaege_von(kind)),
        "fehler": fehler or {},
        "vorgaben": vorgaben or {},
        "ok": MELDUNGEN.get(request.GET.get("ok", ""), ""),
        "spitzname_max": konten_services.SPITZNAME_MAX,
        "vorschlag_max": moods.TEXT_MAX,
    }
    return render(request, "oberflaeche/kind_einstellungen.html", kontext, status=status)


def _fertig(code):
    return redirect(f"{reverse('oberflaeche:kind_einstellungen')}?ok={code}")


@nur_kind
@require_GET
def einstellungen(request):
    return _seite(request)


@nur_kind
@require_POST
def profil(request):
    try:
        konten_services.kind_selbst_aendern(
            request.user, request.POST.get("anzeigename", ""), request.POST.get("spitzname", "")
        )
    except ValidationError as exc:
        return _seite(
            request,
            fehler={"profil": _meldung(exc)},
            vorgaben={
                "anzeigename": request.POST.get("anzeigename", ""),
                "spitzname": request.POST.get("spitzname", ""),
            },
            status=422,
        )
    return _fertig("profil")


@nur_kind
@require_POST
def code(request):
    try:
        konten_services.pin_aendern(
            request.user,
            request.POST.get("alt", ""),
            request.POST.get("neu", ""),
            neue_pin2=request.POST.get("neu2", ""),
        )
    except konten_services.PinGesperrt as exc:
        return _seite(request, fehler={"code": _meldung(exc)}, status=429)
    except ValidationError as exc:
        return _seite(request, fehler={"code": _meldung(exc)}, status=422)
    return _fertig("code")


@nur_kind
@require_POST
def mood_waehlen(request):
    try:
        konten_services.mood_setzen(request.user, request.POST.get("mood", ""))
    except ValidationError as exc:
        return _seite(request, fehler={"mood": _meldung(exc)}, status=422)
    return _fertig("mood")


@nur_kind
@require_POST
def mood_vorschlagen(request):
    try:
        mood.vorschlagen(request.user, request.POST.get("text", ""))
    except ValidationError as exc:
        return _seite(
            request,
            fehler={"vorschlag": _meldung(exc)},
            vorgaben={"vorschlag": request.POST.get("text", "")},
            status=422,
        )
    return _fertig("vorschlag")
