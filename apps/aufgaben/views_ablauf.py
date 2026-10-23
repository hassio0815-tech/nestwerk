"""Kinderablauf-UI (AP12, HTMX): Kind wählt/meldet, Eltern entscheiden.

Jede Aktion antwortet bei HTMX mit dem neu gerenderten Bereich (inkl. Hinweis), sonst mit der
vollen Seite. Fachliche Fehler (``AblaufFehler``) erscheinen als Hinweis, nie als 500.
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
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

    antwort = _kind_aktion(request, pk, aktion, "Die Aufgabe gehört dir. Los geht's!")
    if ergebnis.get("status") == "konflikt":
        return _kind_seite(
            request,
            hinweis="Auch andere wollen diese Aufgabe. Mama oder Papa entscheiden.",
            art="info",
        )
    return antwort


@nur_kind
@require_POST
def kind_zurueckgeben(request, pk):
    return _kind_aktion(
        request, pk, services.zurueckgeben, "Zurückgegeben. Keine Sorge, das ist okay."
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
        "Super! Die Punkte sind schon gutgeschrieben."
        if instanz.freigabeart_snapshot == Freigabeart.VERTRAUEN
        else "Gemeldet! Mama oder Papa schauen bald drauf."
    )
    return _kind_aktion(request, pk, aktion, erfolg)


@nur_kind
@require_POST
def kind_antworten(request, pk):
    text = request.POST.get("text", "")
    fotos = request.FILES.getlist("foto")

    def aktion(instanz, kind):
        services.rueckfrage_beantworten(instanz, kind, text=text, fotos=fotos)

    return _kind_aktion(request, pk, aktion, "Antwort gesendet!")


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
        raise services.AblaufFehler("Sonderpunkte: bitte eine ganze Zahl.") from None


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
            raise services.AblaufFehler("Dieses Kind hat die Aufgabe nicht gewählt.")
        services.zuteilen(instanz, interesse.kind, von=von)

    return _eltern_aktion(request, pk, aktion, "Zugeteilt.")


@nur_eltern
@require_POST
def eltern_loesen(request, pk):
    return _eltern_aktion(
        request,
        pk,
        lambda instanz, von, daten: services.reservierung_loesen(instanz, von=von),
        "Reservierung gelöst, die Aufgabe ist wieder frei.",
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

    return _eltern_aktion(request, pk, aktion, "Bestätigt, Punkte gebucht.")


@nur_eltern
@require_POST
def eltern_ablehnen(request, pk):
    def aktion(instanz, von, daten):
        services.ablehnen(instanz, von=von, begruendung=daten.get("begruendung", ""))

    return _eltern_aktion(request, pk, aktion, "Abgelehnt.")


@nur_eltern
@require_POST
def eltern_rueckfrage(request, pk):
    def aktion(instanz, von, daten):
        services.rueckfrage_stellen(instanz, von=von, text=daten.get("frage", ""))

    return _eltern_aktion(request, pk, aktion, "Rückfrage gesendet.")


@nur_eltern
@require_POST
def eltern_sonderpunkte(request, pk):
    def aktion(instanz, von, daten):
        punkte = _zahl(daten.get("sonderpunkte"))
        services.sonderpunkte_vergeben(instanz, punkte, daten.get("begruendung", ""), von=von)

    return _eltern_aktion(request, pk, aktion, "Sonderpunkte vergeben.")


@nur_eltern
@require_POST
def eltern_korrigieren(request, pk):
    def aktion(instanz, von, daten):
        services.korrigieren(instanz, von=von, begruendung=daten.get("begruendung", ""))

    return _eltern_aktion(request, pk, aktion, "Korrigiert, Punkte zurückgebucht.")
