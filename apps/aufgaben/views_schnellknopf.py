"""Schnell-Knöpfe (HTMX): Kacheln für Eltern und Kinder sowie das Flur-Tablet.

Flur-Tablet: Dort ist niemand angemeldet, ein Druck ist trotzdem eine Schreibaktion. Sie ist nur
erlaubt, wenn die Anfrage vom **registrierten Kiosk-Gerät** kommt (signiertes Geräte-Cookie, von
Eltern eingerichtet), aus dem Heimnetz stammt und das CSRF-Token trägt (Tablet-Seite sendet es
über ``hx-headers``). Das Kind kommt aus dem Formular; geprüft wird nur, dass es ein aktives,
nicht gesperrtes Kind ist, das die Aufgabe machen darf. Eltern-Knöpfe (``schnellknopf_wer =
eltern``) gibt es am Tablet nie. Fachliche Fehler erscheinen als Hinweis, nie als 500.
"""

from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.kern import zeit
from apps.kern.sprache import uebersetzt
from apps.konten import netz, sperre
from apps.konten import selectors as konten_selectors
from apps.konten.geraet import ist_kiosk
from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind, nur_eltern, nur_kind

from . import schnellknopf
from .models import Aufgabe
from .zustand import AblaufFehler

MELDEN = "melden"


def _knopf(pk):
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("kategorie"), pk=pk)
    if not aufgabe.schnellknopf:
        raise Http404
    return aufgabe


def _kind_aus_formular(request):
    """Gewähltes Kind (``kind_id``) oder ``None`` = "Nur melden"."""
    kind_id = request.POST.get("kind_id", "")
    if not kind_id or request.POST.get("modus") == MELDEN:
        return None
    kind = konten_selectors.aktive_kinder().filter(pk=kind_id).first()
    if kind is None:
        raise Http404
    return kind


def _druecken(aufgabe, *, von, kind):
    """(Hinweistext, Art). Fachliche Fehler werden zum Hinweis."""
    try:
        _instanz, neu = schnellknopf.druecken(aufgabe, von=von, kind=kind)
    except AblaufFehler as fehler:
        return str(fehler), "fehler"
    titel = uebersetzt(aufgabe.titel)
    if not neu:
        return _("„%(titel)s“ läuft schon.") % {"titel": titel}, "info"
    if kind is not None:
        return _("„%(titel)s“ ist für %(name)s reserviert.") % {
            "titel": titel,
            "name": kind.anzeigename,
        }, "erfolg"
    return _("Gemeldet: „%(titel)s“. Die Kinder wissen Bescheid.") % {"titel": titel}, "erfolg"


# --- Eltern und Kinder (Dashboard-Kacheln) ----------------------------------------------------


def _kachel(request, vorlage, hinweis="", art="erfolg"):
    kontext = {
        "k": {"knoepfe": schnellknopf.knoepfe(request.user), "kinder": []},
        "hinweis": hinweis,
        "hinweis_art": art,
    }
    if vorlage.endswith("eltern.html"):
        kontext["k"]["kinder"] = list(konten_selectors.aktive_kinder())
    return render(request, vorlage, kontext)


@nur_eltern
@require_POST
def eltern_druecken(request, pk):
    hinweis, art = _druecken(
        _knopf(pk), von=aktueller_elternteil(request), kind=_kind_aus_formular(request)
    )
    return _kachel(request, "aufgaben/kacheln/schnellknoepfe_eltern.html", hinweis, art)


@nur_kind
@require_POST
def kind_druecken(request, pk):
    kind = aktuelles_kind(request)
    mach_ich = request.POST.get("modus") != MELDEN
    hinweis, art = _druecken(_knopf(pk), von=kind, kind=kind if mach_ich else None)
    return _kachel(request, "aufgaben/kacheln/schnellknoepfe_kind.html", hinweis, art)


# --- Flur-Tablet ------------------------------------------------------------------------------


def _tablet_gesperrt(request):
    """``None`` = erlaubt, sonst die Fehlerantwort."""
    if not netz.kind_login_erlaubt(request):
        return HttpResponseForbidden(_("Die Tablet-Ansicht gibt es nur im Heimnetz."))
    if not ist_kiosk(request):
        return HttpResponseForbidden(_("Dieses Gerät ist nicht als Flur-Tablet eingerichtet."))
    return None


def tablet_kinder(aufgabe):
    """Kinder, die am Tablet gewählt werden können (aktiv, nicht gesperrt, dürfen die Aufgabe)."""
    jetzt = zeit.jetzt()
    return [
        kind
        for kind in schnellknopf.erlaubte_kinder(aufgabe)
        if not sperre.kind_gesperrt_bis(kind.kindprofil, jetzt)
    ]


@require_GET
def tablet_waehlen(request, pk):
    """Auswahl nach dem Tippen: "Nur melden" oder ein Kind ("Ich mach's"), ohne PIN."""
    if (verboten := _tablet_gesperrt(request)) is not None:
        return verboten
    aufgabe = _knopf(pk)
    if not schnellknopf.darf_druecken(aufgabe, None):
        raise Http404
    kontext = {"a": aufgabe, "kinder": tablet_kinder(aufgabe)}
    return render(request, "aufgaben/_tablet_schnellknopf.html", kontext)


@require_POST
def tablet_druecken(request, pk):
    if (verboten := _tablet_gesperrt(request)) is not None:
        return verboten
    aufgabe = _knopf(pk)
    kind = _kind_aus_formular(request)
    if kind is not None and kind not in tablet_kinder(aufgabe):
        raise Http404
    hinweis, art = _druecken(aufgabe, von=None, kind=kind)
    kontext = {"a": aufgabe, "hinweis": hinweis, "hinweis_art": art, "fertig": True}
    return render(request, "aufgaben/_tablet_schnellknopf.html", kontext)
