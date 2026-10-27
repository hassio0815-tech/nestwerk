"""Kinderablauf-UI (AP12, HTMX): Kind wählt/meldet, Eltern entscheiden.

Jede Aktion antwortet bei HTMX mit dem neu gerenderten Bereich (inkl. Hinweis), sonst mit der
vollen Seite. Fachliche Fehler (``AblaufFehler``) erscheinen als Hinweis, nie als 500.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind, nur_eltern, nur_kind

from . import selectors, services
from .models import AufgabenInstanz, Freigabeart

# --- Kind -------------------------------------------------------------------------------------


def _htmx(request):
    return request.headers.get("HX-Request") == "true"


def _kind_seite(request, *, hinweis="", art="erfolg"):
    kind = aktuelles_kind(request)
    kontext = {
        "offene": selectors.kind_offene(kind),
        "eigene": selectors.kind_eigene(kind),
        "hinweis": hinweis,
        "hinweis_art": art,
    }
    vorlage = "aufgaben/_kind_bereich.html" if _htmx(request) else "aufgaben/kind.html"
    return render(request, vorlage, kontext)


@nur_kind
def kind_aufgaben(request):
    return _kind_seite(request)


def _kind_aktion(request, pk, aktion, erfolg):
    kind = aktuelles_kind(request)
    instanz = get_object_or_404(AufgabenInstanz.objects.select_related("aufgabe"), pk=pk)
    if not services.kind_darf_sehen(instanz, kind):
        raise Http404
    try:
        aktion(instanz, kind)
    except services.AblaufFehler as fehler:
        return _kind_seite(request, hinweis=str(fehler), art="fehler")
    return _kind_seite(request, hinweis=erfolg)


@nur_kind
@require_POST
def kind_waehlen(request, pk):
    ergebnis = {}

    def aktion(instanz, kind):
        ergebnis["status"] = services.interesse_zeigen(instanz, kind).status

    antwort = _kind_aktion(request, pk, aktion, _("Die Aufgabe gehört dir. Los geht's!"))
    if ergebnis.get("status") == "konflikt":
        return _kind_seite(
            request,
            hinweis=_("Auch andere wollen diese Aufgabe. Mama oder Papa entscheiden."),
            art="info",
        )
    return antwort


@nur_kind
@require_POST
def kind_zurueckgeben(request, pk):
    return _kind_aktion(
        request, pk, services.zurueckgeben, _("Zurückgegeben. Keine Sorge, das ist okay.")
    )


@nur_kind
@require_POST
def kind_melden(request, pk):
    text = request.POST.get("text", "")
    fotos = request.FILES.getlist("foto")

    def aktion(instanz, kind):
        services.erledigt_melden(instanz, kind, text=text, fotos=fotos)

    instanz = get_object_or_404(AufgabenInstanz, pk=pk)
    erfolg = (
        _("Super! Die Punkte sind schon gutgeschrieben.")
        if instanz.freigabeart_snapshot == Freigabeart.VERTRAUEN
        else _("Gemeldet! Mama oder Papa schauen bald drauf.")
    )
    return _kind_aktion(request, pk, aktion, erfolg)


@nur_kind
@require_POST
def kind_antworten(request, pk):
    text = request.POST.get("text", "")
    fotos = request.FILES.getlist("foto")

    def aktion(instanz, kind):
        services.rueckfrage_beantworten(instanz, kind, text=text, fotos=fotos)

    return _kind_aktion(request, pk, aktion, _("Antwort gesendet!"))


# --- Eltern -----------------------------------------------------------------------------------


def _eltern_seite(request, *, hinweis="", art="erfolg"):
    kontext = selectors.eltern_entscheidungen()
    for instanz in kontext["meldungen"] + kontext["bestaetigt"]:
        instanz.deckel = services.sonderpunkte_deckel(instanz)
    kontext.update(hinweis=hinweis, hinweis_art=art)
    vorlage = "aufgaben/_entscheidungen.html" if _htmx(request) else "aufgaben/entscheidungen.html"
    return render(request, vorlage, kontext)


@nur_eltern
def entscheidungen(request):
    return _eltern_seite(request)


def _zahl(wert):
    wert = (wert or "").strip()
    if not wert:
        return 0
    try:
        return int(wert)
    except ValueError:
        raise services.AblaufFehler(_("Sonderpunkte: bitte eine ganze Zahl.")) from None


def _eltern_aktion(request, pk, aktion, erfolg):
    von = aktueller_elternteil(request)
    instanz = get_object_or_404(AufgabenInstanz, pk=pk)
    try:
        aktion(instanz, von, request.POST)
    except services.AblaufFehler as fehler:
        return _eltern_seite(request, hinweis=str(fehler), art="fehler")
    return _eltern_seite(request, hinweis=erfolg)


@nur_eltern
@require_POST
def eltern_zuteilen(request, pk, kind_id):
    def aktion(instanz, von, daten):
        interesse = instanz.interessen.filter(kind_id=kind_id).select_related("kind").first()
        if interesse is None:
            raise services.AblaufFehler(_("Dieses Kind hat die Aufgabe nicht gewählt."))
        services.zuteilen(instanz, interesse.kind, von=von)

    return _eltern_aktion(request, pk, aktion, _("Zugeteilt."))


@nur_eltern
@require_POST
def eltern_loesen(request, pk):
    return _eltern_aktion(
        request,
        pk,
        lambda instanz, von, daten: services.reservierung_loesen(instanz, von=von),
        _("Reservierung gelöst, die Aufgabe ist wieder frei."),
    )


@nur_eltern
@require_POST
def eltern_bestaetigen(request, pk):
    def aktion(instanz, von, daten):
        services.bestaetigen(
            instanz,
            von=von,
            sonderpunkte=_zahl(daten.get("sonderpunkte")),
            begruendung=daten.get("begruendung", ""),
        )

    return _eltern_aktion(request, pk, aktion, _("Bestätigt, Punkte gebucht."))


@nur_eltern
@require_POST
def eltern_ablehnen(request, pk):
    def aktion(instanz, von, daten):
        services.ablehnen(instanz, von=von, begruendung=daten.get("begruendung", ""))

    return _eltern_aktion(request, pk, aktion, _("Abgelehnt."))


@nur_eltern
@require_POST
def eltern_rueckfrage(request, pk):
    def aktion(instanz, von, daten):
        services.rueckfrage_stellen(instanz, von=von, text=daten.get("frage", ""))

    return _eltern_aktion(request, pk, aktion, _("Rückfrage gesendet."))


@nur_eltern
@require_POST
def eltern_sonderpunkte(request, pk):
    def aktion(instanz, von, daten):
        punkte = _zahl(daten.get("sonderpunkte"))
        services.sonderpunkte_vergeben(instanz, punkte, daten.get("begruendung", ""), von=von)

    return _eltern_aktion(request, pk, aktion, _("Sonderpunkte vergeben."))


@nur_eltern
@require_POST
def eltern_korrigieren(request, pk):
    def aktion(instanz, von, daten):
        services.korrigieren(instanz, von=von, begruendung=daten.get("begruendung", ""))

    return _eltern_aktion(request, pk, aktion, _("Korrigiert, Punkte zurückgebucht."))


# --- Vertrauen prüfen (Dashboard-Karte "Erledigt – kurz prüfen") -----------------------------------


def _pruefen_antwort(request, hinweis="", art="erfolg"):
    if not _htmx(request):
        return redirect("oberflaeche:eltern_heim")
    kontext = {"k": {"liste": list(services.zu_pruefen())}, "hinweis": hinweis, "hinweis_art": art}
    return render(request, "aufgaben/_pruefen.html", kontext)


def _pruefen_aktion(request, pk, aktion, erfolg):
    von = aktueller_elternteil(request)
    instanz = get_object_or_404(AufgabenInstanz, pk=pk)
    try:
        aktion(instanz, von, request.POST.get("begruendung", ""))
    except services.AblaufFehler as fehler:
        return _pruefen_antwort(request, str(fehler), "fehler")
    return _pruefen_antwort(request, erfolg)


@nur_eltern
@require_POST
def pruefen_passt(request, pk):
    return _pruefen_aktion(
        request, pk, lambda i, von, _g: services.passt(i, von=von), _("Passt, danke.")
    )


@nur_eltern
@require_POST
def pruefen_alle(request):
    anzahl = services.alle_passen(von=aktueller_elternteil(request))
    return _pruefen_antwort(request, _("%(n)s als „passt“ markiert.") % {"n": anzahl})


@nur_eltern
@require_POST
def pruefen_nachbessern(request, pk):
    return _pruefen_aktion(
        request,
        pk,
        lambda i, von, grund: services.korrigieren(i, von=von, begruendung=grund, nachbessern=True),
        _("Zurück ans Kind: Punkte abgezogen, es soll nachbessern."),
    )


@nur_eltern
@require_POST
def pruefen_ablehnen(request, pk):
    return _pruefen_aktion(
        request,
        pk,
        lambda i, von, grund: services.korrigieren(i, von=von, begruendung=grund),
        _("Abgelehnt, Punkte zurückgebucht."),
    )
