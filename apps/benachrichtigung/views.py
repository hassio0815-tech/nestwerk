"""Seiten für Eltern (Liste, Präferenzen) und der Pop-up-Abruf für Kinder.

Teilansichten für HTMX-Polling sind mit ``@passiv`` markiert (verlängern keine Sitzung).
"""

import logging
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.konten import selectors as konten_selectors
from apps.konten.zugriff import nur_eltern, nur_kind, passiv

from . import registry, ruhezeit, selectors, services, texte
from .models import Benachrichtigung
from .views_push import push_kontext

logger = logging.getLogger("nestwerk.benachrichtigung")


# --- Liste -----------------------------------------------------------------------------------


def _liste_kontext(request):
    return {
        "eintraege": selectors.liste(request.user),
        "ungelesen": selectors.ungelesen(request.user),
    }


@nur_eltern
@require_GET
def liste(request):
    return render(request, "benachrichtigung/liste.html", _liste_kontext(request))


@passiv
@nur_eltern
@require_GET
def liste_teil(request):
    return render(request, "benachrichtigung/_liste.html", _liste_kontext(request))


@passiv
@nur_eltern
@require_GET
def zaehler(request):
    return render(
        request, "benachrichtigung/_zaehler.html", {"ungelesen": selectors.ungelesen(request.user)}
    )


@nur_eltern
@require_POST
def gelesen(request, pk):
    services.als_gelesen(request.user, pk)
    return render(request, "benachrichtigung/_liste.html", _liste_kontext(request))


@nur_eltern
@require_POST
def alle_gelesen(request):
    services.alle_als_gelesen(request.user)
    return render(request, "benachrichtigung/_liste.html", _liste_kontext(request))


@nur_eltern
@require_GET
def oeffnen(request, pk):
    """Markiert als gelesen und folgt dem Deep-Link (nur interne Pfade)."""
    eintrag = get_object_or_404(Benachrichtigung, pk=pk, empfaenger=request.user)
    services.als_gelesen(request.user, eintrag.pk)
    ziel = eintrag.link if texte.ist_interner_pfad(eintrag.link) else ""
    return HttpResponseRedirect(ziel or "/eltern/benachrichtigungen/")


# --- Präferenzen -----------------------------------------------------------------------------


def _ziel_benutzer(request):
    """Wessen Einstellungen: die eigenen oder die eines aktiven Kindes (``fuer``)."""
    fuer = request.POST.get("fuer") or request.GET.get("fuer") or ""
    if not fuer or fuer == str(request.user.pk):
        return request.user
    kind = konten_selectors.aktive_kinder().filter(pk=fuer).first()
    if kind is None:
        raise PermissionDenied
    return kind


def _einstellungen_kontext(request, ziel, fehler=""):
    matrix, kanaele = selectors.praeferenz_matrix(ziel)
    eigene = ziel.pk == request.user.pk
    rz = selectors.ruhezeiten(ziel)[0] if eigene and selectors.ruhezeiten(ziel) else None
    return {
        "ziel": ziel,
        "fuer": "" if eigene else str(ziel.pk),
        "eigene": eigene,
        "kinder": list(konten_selectors.aktive_kinder()),
        "matrix": matrix,
        "kanaele": kanaele,
        "ruhezeit": rz,
        "tage": [
            {"nr": i, "name": ruhezeit.TAGE[i], "an": bool(rz is None or rz.wochentage & (1 << i))}
            for i in range(7)
        ],
        "nur_entscheidungen": selectors.mail_nur_entscheidungen(ziel) if eigene else False,
        "smtp_da": selectors.smtp_konto() is not None,
        "fehler": fehler,
        **(push_kontext(request) if eigene else {}),
    }


@nur_eltern
@require_GET
def einstellungen(request):
    return render(
        request,
        "benachrichtigung/einstellungen.html",
        _einstellungen_kontext(request, _ziel_benutzer(request)),
    )


@nur_eltern
@require_POST
def praeferenz(request):
    ziel = _ziel_benutzer(request)
    try:
        services.praeferenz_setzen(
            ziel,
            request.POST.get("typ", ""),
            request.POST.get("kanal", ""),
            request.POST.get("aktiv") == "1",
        )
    except (registry.UnbekannterEintrag, ObjectDoesNotExist):
        return HttpResponse(status=400)
    return render(
        request, "benachrichtigung/_einstellungen.html", _einstellungen_kontext(request, ziel)
    )


def _zeit(text):
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


@nur_eltern
@require_POST
def ruhezeit_speichern(request):
    if request.POST.get("aktion") == "entfernen":
        services.ruhezeit_entfernen(request.user)
        fehler = ""
    else:
        von, bis = _zeit(request.POST.get("von", "")), _zeit(request.POST.get("bis", ""))
        maske = 0
        for nr in request.POST.getlist("tage"):
            if nr.isdigit() and 0 <= int(nr) <= 6:
                maske |= 1 << int(nr)
        if von is None or bis is None:
            fehler = "Bitte Uhrzeiten wie 21:00 eingeben."
        elif maske == 0:
            fehler = "Bitte mindestens einen Wochentag wählen."
        else:
            services.ruhezeit_setzen(
                request.user,
                von=von,
                bis=bis,
                wochentage=maske,
                gilt_fuer_email=request.POST.get("email") == "1",
            )
            fehler = ""
    return render(
        request,
        "benachrichtigung/_einstellungen.html",
        _einstellungen_kontext(request, request.user, fehler),
    )


@nur_eltern
@require_POST
def profil(request):
    services.mail_profil_setzen(request.user, request.POST.get("nur_entscheidungen") == "1")
    return render(
        request,
        "benachrichtigung/_einstellungen.html",
        _einstellungen_kontext(request, request.user),
    )


# --- Pop-ups für Kinder ----------------------------------------------------------------------


@passiv
@nur_kind
@require_GET
def popups(request):
    """Ungesehene Pop-ups als Toasts; leer = 204 (HTMX tauscht nichts)."""
    offen = selectors.ungesehene_popups(request.user)
    if not offen:
        return HttpResponse(status=204)
    services.popups_als_gesehen(offen)
    return render(request, "benachrichtigung/_popups.html", {"popups": offen})
