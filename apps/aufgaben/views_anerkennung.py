"""Anerkennung (Eltern): Punkte ohne Aufgabe schenken. Fachliche Fehler erscheinen als Hinweis."""

from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.konten import selectors as konten_selectors
from apps.konten.zugriff import nur_eltern

from . import anerkennung
from .zustand import AblaufFehler


def _seite(request, *, hinweis="", art="erfolg", status=200, vorgaben=None):
    kinder = list(konten_selectors.aktive_kinder())
    je_vergabe, je_woche = anerkennung.grenzen()
    kontext = {
        "zeilen": anerkennung.uebersicht(kinder),
        "je_vergabe": je_vergabe,
        "je_woche": je_woche,
        "vorgang": anerkennung.neuer_vorgang(),
        "hinweis": hinweis,
        "hinweis_art": art,
        "vorgaben": vorgaben or {},
    }
    return render(request, "aufgaben/anerkennung.html", kontext, status=status)


def _kind(kind_id):
    try:
        return konten_selectors.aktive_kinder().filter(pk=kind_id).first()
    except (ValidationError, ValueError):
        return None


@nur_eltern
@require_http_methods(["GET", "POST"])
def anerkennung_vergeben(request):
    if request.method == "GET":
        return _seite(request)
    daten = request.POST
    kind = _kind(daten.get("kind_id") or None)
    vorgaben = {
        "kind_id": daten.get("kind_id", ""),
        "punkte": daten.get("punkte", ""),
        "bemerkung": daten.get("bemerkung", ""),
    }
    try:
        if kind is None:
            raise AblaufFehler(_("Bitte ein Kind auswählen."))
        try:
            punkte = int((daten.get("punkte") or "").strip())
        except ValueError:
            raise AblaufFehler(_("Bitte eine ganze Zahl für die Punkte eingeben.")) from None
        anerkennung.vergeben(
            kind,
            punkte,
            daten.get("bemerkung", ""),
            von=request.user,
            vorgang=_vorgang(daten.get("vorgang")),
        )
    except AblaufFehler as fehler:
        return _seite(request, hinweis=str(fehler), art="fehler", status=422, vorgaben=vorgaben)
    hinweis = _("%(punkte)s Punkte Anerkennung für %(name)s gebucht.") % {
        "punkte": punkte,
        "name": kind.anzeigename,
    }
    return _seite(request, hinweis=hinweis)


def _vorgang(wert):
    """Nur eine Hex-Kennung (vom Formular), sonst neu."""
    wert = (wert or "").strip()
    return wert if 8 <= len(wert) <= 40 and all(z in "0123456789abcdef" for z in wert) else None
