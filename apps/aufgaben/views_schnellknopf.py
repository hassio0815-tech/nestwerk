"""Schnell-Knöpfe (HTMX): Kacheln für Eltern und Kinder sowie das Flur-Tablet.

Flur-Tablet: Dort ist niemand angemeldet, ein Druck ist trotzdem eine Schreibaktion. Sie ist nur
erlaubt, wenn die Anfrage vom **registrierten Kiosk-Gerät** kommt (signiertes Geräte-Cookie, von
Eltern eingerichtet), aus dem Heimnetz stammt und das CSRF-Token trägt (Tablet-Seite sendet es
über ``hx-headers``). Das Kind kommt aus dem Formular; geprüft wird nur, dass es ein aktives,
nicht gesperrtes Kind ist, das die Aufgabe machen darf. Eltern-Knöpfe (``schnellknopf_wer =
eltern``) gibt es am Tablet nie. Fachliche Fehler erscheinen als Hinweis, nie als 500.
"""

from uuid import UUID

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

from . import schnellknopf, selectors
from .models import Aufgabe
from .zustand import AblaufFehler

MELDEN = schnellknopf.MELDEN
JEDES = schnellknopf.JEDES
ICH_MACHS = schnellknopf.ICH_MACHS


def _knopf(pk):
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("kategorie"), pk=pk)
    if not aufgabe.schnellknopf:
        raise Http404
    return aufgabe


def _modus_und_kind(request):
    """``(modus, kind)`` aus dem Formular; ungültige Angaben werden ``AblaufFehler`` (Hinweis).

    ``modus=melden``/``jedes`` ignorieren ``kind_id``. Sonst gilt "Ich mach's" für das Kind aus
    ``kind_id`` (Kind-Kachel: ``modus=ich``, ohne ``kind_id`` für sich selbst, siehe dort).
    """
    modus = request.POST.get("modus", "")
    if modus in (MELDEN, JEDES):
        return modus, None
    kind_id = request.POST.get("kind_id", "").strip()
    if not kind_id:
        if modus == ICH_MACHS:
            raise AblaufFehler(_("Bitte ein Kind wählen."))
        return MELDEN, None
    try:
        kind = konten_selectors.aktive_kinder().filter(pk=UUID(kind_id)).first()
    except ValueError:
        kind = None
    if kind is None:
        raise AblaufFehler(_("Dieses Kind gibt es nicht."))
    return ICH_MACHS, kind


def _namen(kinder):
    return ", ".join(kind.anzeigename for kind in kinder)


def _druecken(aufgabe, *, von, modus, kind):
    """(Hinweistext, Art). Fachliche Fehler werden zum Hinweis."""
    try:
        druck = schnellknopf.druecken(aufgabe, von=von, kind=kind, modus=modus)
    except AblaufFehler as fehler:
        return str(fehler), "fehler"
    titel = uebersetzt(aufgabe.titel)
    if modus == JEDES:
        teile = []
        if druck.angelegt:
            teile.append(
                _("„%(titel)s“ ist reserviert für %(namen)s.")
                % {"titel": titel, "namen": _namen(i.kind for i in druck.angelegt)}
            )
        else:
            teile.append(_("„%(titel)s“ läuft schon.") % {"titel": titel})
        if druck.uebersprungen and druck.angelegt:
            teile.append(
                _("Übersprungen: %(namen)s.")
                % {"namen": _namen(k for k, _grund in druck.uebersprungen)}
            )
        return " ".join(teile), "erfolg" if druck.angelegt else "info"
    if not druck.neu:
        return _("„%(titel)s“ läuft schon.") % {"titel": titel}, "info"
    if kind is not None:
        return _("„%(titel)s“ ist für %(name)s reserviert.") % {
            "titel": titel,
            "name": kind.anzeigename,
        }, "erfolg"
    return _("Gemeldet: „%(titel)s“. Die Kinder wissen Bescheid.") % {"titel": titel}, "erfolg"


def _druecken_aus_formular(request, aufgabe, *, von, tablet_kinder_fuer=None):
    """Formular auswerten und drücken -> (Hinweis, Art)."""
    try:
        modus, kind = _modus_und_kind(request)
    except AblaufFehler as fehler:
        return str(fehler), "fehler"
    if tablet_kinder_fuer is not None and kind is not None and kind not in tablet_kinder_fuer:
        raise Http404
    return _druecken(aufgabe, von=von, modus=modus, kind=kind)


# --- Eltern und Kinder (Dashboard-Kacheln) ----------------------------------------------------


def _eltern_kontext(request, hinweis="", art="erfolg"):
    return {
        "k": {
            "knoepfe": schnellknopf.knoepfe(request.user),
            "kinder": list(konten_selectors.aktive_kinder()),
        },
        "hinweis": hinweis,
        "hinweis_art": art,
    }


@nur_eltern
@require_POST
def eltern_druecken(request, pk):
    hinweis, art = _druecken_aus_formular(request, _knopf(pk), von=aktueller_elternteil(request))
    kontext = _eltern_kontext(request, hinweis, art)
    return render(request, "aufgaben/kacheln/schnellknoepfe_eltern.html", kontext)


@nur_eltern
@require_GET
def schnellknoepfe_seite(request):
    """Verwaltung der Schnell-Knöpfe (löst die frühere Bibliothek ab): Kachel plus Bearbeiten."""
    return render(request, "aufgaben/schnellknoepfe.html", _eltern_kontext(request))


@nur_kind
@require_POST
def kind_druecken(request, pk):
    kind = aktuelles_kind(request)
    modus = request.POST.get("modus")
    if modus == JEDES:
        hinweis, art = _druecken(_knopf(pk), von=kind, modus=JEDES, kind=None)
    elif modus == MELDEN:
        hinweis, art = _druecken(_knopf(pk), von=kind, modus=MELDEN, kind=None)
    else:
        hinweis, art = _druecken(_knopf(pk), von=kind, modus=ICH_MACHS, kind=kind)
    return _kind_kachel(request, hinweis, art)


def _kind_kachel(request, hinweis, art):
    """Kachel plus (oob) der Aufgabenbereich: beides bleibt synchron (Finding A-P3-09).

    Der Hinweis steht nur in der Kachel, der Bereich bekommt keinen zweiten."""
    kind = aktuelles_kind(request)
    kontext = {
        "k": {"knoepfe": schnellknopf.knoepfe(kind), "kinder": []},
        "hinweis": hinweis,
        "hinweis_art": art,
        "bereich_oob": True,
        "offene": selectors.kind_unzugeordnete(kind),
        "eigene": selectors.kind_eigene(kind),
    }
    return render(request, "aufgaben/kacheln/schnellknoepfe_kind_antwort.html", kontext)


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
    hinweis, art = _druecken_aus_formular(
        request, aufgabe, von=None, tablet_kinder_fuer=tablet_kinder(aufgabe)
    )
    kontext = {"a": aufgabe, "hinweis": hinweis, "hinweis_art": art, "fertig": True}
    return render(request, "aufgaben/_tablet_schnellknopf.html", kontext)
