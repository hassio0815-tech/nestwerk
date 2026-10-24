"""Startseite-Weiche, Kinder-/Eltern-Dashboard und Tablet-Startseite (SPEC 12).

Routing: ``/`` leitet je Rolle/Gerät weiter (Anmeldung bleibt bei ``konten``), ``/kind/`` und
``/eltern/`` sind die Dashboards, ``/tablet/`` die Live-Startseite des Flur-Tablets."""

from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.kern import einstellungen, zeit
from apps.kern.registry import ELTERN, KIND, TABLET
from apps.konten import akzent, netz, sperre
from apps.konten import selectors as konten_selectors
from apps.konten import services as konten_services
from apps.konten import views as konten_views
from apps.konten.geraet import ist_kiosk
from apps.konten.models import Rolle
from apps.konten.zugriff import nur_eltern, nur_kind, passiv

from . import kacheln, ranking, selectors


@require_GET
def styleguide(request):
    """Entwicklungsansicht aller Komponenten. Ohne DEBUG nicht erreichbar."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "oberflaeche/styleguide.html")


@require_GET
def startseite(request):
    """``/``: angemeldet -> eigenes Dashboard, Kiosk-Gerät -> Tablet-Startseite, sonst die
    Anmeldeauswahl von ``konten``."""
    if request.user.is_authenticated:
        return redirect(
            "oberflaeche:eltern_heim"
            if request.user.rolle == Rolle.ELTERN
            else "oberflaeche:kind_heim"
        )
    if ist_kiosk(request):
        return redirect("oberflaeche:tablet")
    return konten_views.start(request)


@nur_kind
@require_GET
def kind_heim(request):
    return render(
        request,
        "oberflaeche/kind_heim.html",
        {"kacheln": kacheln.fuer(KIND, request)},
    )


@nur_kind
@require_POST
def akzent_setzen(request):
    name = request.POST.get("akzent", "")
    if name in akzent.PALETTE:
        konten_services.akzentfarben_setzen(request.user, [akzent.name_zu_hex(name)])
    return redirect("oberflaeche:kind_heim")


@nur_eltern
@require_GET
def eltern_heim(request):
    return render(
        request,
        "oberflaeche/eltern_heim.html",
        {
            "kacheln": kacheln.fuer(ELTERN, request),
            "gesperrte_kinder": konten_selectors.gesperrte_kinder(),
        },
    )


# --- Tablet ----------------------------------------------------------------------------------


def _tablet_kontext(request):
    jetzt = zeit.jetzt()
    kinder = []
    for kind in konten_selectors.aktive_kinder():
        kinder.append(
            {
                "benutzer": kind,
                "akzent": akzent.akzent_name(kind),
                "gesperrt": bool(sperre.kind_gesperrt_bis(kind.kindprofil, jetzt)),
                "guthaben": selectors.kind_konto(kind)["guthaben"],
                "offen": selectors.offene_anzahl(kind),
            }
        )
    return {"kinder": kinder, "slots": kacheln.fuer(TABLET, request)}


def _tablet_erlaubt(request):
    return netz.kind_login_erlaubt(request)


@require_GET
def tablet(request):
    """Tablet-Startseite ohne Anmeldung (nur Lesen, nur aus dem Heimnetz)."""
    if not _tablet_erlaubt(request):
        return HttpResponseForbidden("Die Tablet-Ansicht gibt es nur im Heimnetz.")
    werte = einstellungen.werte(
        "oberflaeche.tablet_aktualisierung_sekunden", "oberflaeche.tablet_neuladen_stunden"
    )
    kontext = _tablet_kontext(request)
    kontext["intervall"] = werte["oberflaeche.tablet_aktualisierung_sekunden"]
    kontext["neuladen_sekunden"] = werte["oberflaeche.tablet_neuladen_stunden"] * 3600
    return render(request, "oberflaeche/tablet.html", kontext)


@passiv
@require_GET
def tablet_teil(request):
    """Polling-Ausschnitt der Tablet-Startseite. ``@passiv``: verlängert keine Sitzung."""
    if not _tablet_erlaubt(request):
        return HttpResponseForbidden("Die Tablet-Ansicht gibt es nur im Heimnetz.")
    return render(request, "oberflaeche/_tablet_teil.html", _tablet_kontext(request))


# --- Familien-Ranking (AP30) -----------------------------------------------------------------


@nur_eltern
@require_POST
def ranking_modus(request):
    """Eltern schalten die Ranking-Ansicht für Tablet und Kinder-Seite um."""
    gewaehlt = request.POST.get("modus", "")
    if gewaehlt in ranking.RANKING_MODI:
        einstellungen.setzen("oberflaeche.ranking_modus", gewaehlt)
    return redirect("oberflaeche:eltern_heim")
