"""Seiten von lernen: Kinder üben (HTMX), Eltern sehen den Stand und tragen Pausen ein.

Nur die Rolle Kind darf üben; eine Sitzung gehört genau einem Kind (fremde: 404). Die Eltern-Seite
zeigt Beteiligung (Tage, Serie), nie Noten oder Vergleiche zwischen Geschwistern.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.kern import zeit
from apps.konten import selectors as konten
from apps.konten.zugriff import aktuelles_kind, nur_eltern, nur_kind

from . import mathe_ki, plan_texte, selectors, services, texte, tutor_selectors, tutor_services
from .models import (
    Erwartung,
    Intensitaet,
    Lernpause,
    PausenGrund,
    PortionStatus,
    Selbsteinschaetzung,
    Strategie,
    Vorhaben,
)


def _hx(request):
    return request.headers.get("HX-Request") == "true"


def _wortwahl(kind, fach=None):
    """Ein Satzbaustein-Aufrufer in der Sprachstufe des Kindes."""
    stufe = selectors.sprachstufe(kind, fach)
    return lambda schluessel, **parameter: texte.ton(schluessel, stufe, **parameter)


# --- Kind: Startseite --------------------------------------------------------------------------


def _fach_optionen(kind):
    """Auswahl "Was möchtest du üben?": je Fach alles gemischt oder ein Thema."""
    ergebnis = []
    for fach in selectors.faecher():
        # nur Themen mit Fragen, die dieses Kind nutzen darf: Themen aus dem Material eines
        # Geschwisters (oder noch ohne Freigabe) tauchen hier nie auf
        themen = [t for t in selectors.themen_fuer(kind, fach) if selectors.hat_fragen(t, kind)]
        if themen:
            ergebnis.append((fach, themen))
    return ergebnis


def _vorbelegung(kind):
    """Auswahl der Startseite: die der letzten Sitzung, sonst die bisherigen Standardwerte."""
    letzte = selectors.letzte_auswahl(kind)
    wahl = {
        "vorhaben": Vorhaben.WIEDERHOLEN,
        "strategie": Strategie.ABDECKEN,
        "erwartung": Erwartung.EINIGES,
        "intensitaet": Intensitaet.NORMAL,
        "fach_id": None,
        "thema_id": None,
    }
    if letzte is not None:
        for name in ("vorhaben", "strategie", "erwartung"):
            wahl[name] = getattr(letzte, name) or wahl[name]
        wahl["intensitaet"] = letzte.intensitaet or wahl["intensitaet"]
        wahl["fach_id"] = letzte.fach_id
        wahl["thema_id"] = letzte.thema_id
    return wahl


def _start_kontext(kind, *, fehler=""):
    heute = zeit.heute()
    wort = _wortwahl(kind)
    bild = selectors.tagesbild(kind, heute)
    return {
        "optionen": _fach_optionen(kind),
        "intensitaeten": Intensitaet.choices,
        "vorhaben": Vorhaben.choices,
        "strategien": Strategie.choices,
        "erwartungen": Erwartung.choices,
        "bild": bild,
        "offen": selectors.offene_sitzung(kind),
        "fehler": fehler,
        "vorschlag_text": wort("ziel_vorschlag", minuten=bild.vorschlag_minuten)
        if bild.vorschlag_minuten
        else "",
        "serie_text": wort("serie", wochen=bild.serie.wochen)
        if bild.serie.wochen >= 2
        else wort("serie_neu"),
        "ton_ziel": wort("ziel_geschafft"),
        "tutor_sichtbar": tutor_selectors.bereit(),
        "vorbelegt": _vorbelegung(kind),
        "rueckschau_letzte": (selectors.rueckschauen(kind, 1) or [None])[0],
    }


@nur_kind
def start(request):
    kind = aktuelles_kind(request)
    anpassung = services.tag_vorbereiten(kind)
    kontext = _start_kontext(kind)
    if anpassung.art == "gesenkt":
        kontext["hinweis"] = _wortwahl(kind)("ziel_gesenkt", minuten=anpassung.minuten)
        kontext["bild"] = selectors.tagesbild(kind, zeit.heute())
    return render(request, "lernen/start.html", kontext)


def _auswahl(kind, wert_):
    """``fach:<id>`` oder ``thema:<id>`` -> (Fach, Thema oder None)."""
    art, _sep, nr = str(wert_).partition(":")
    if not nr.isdigit():
        raise services.LernenFehler(_("Bitte wähle aus, was du üben möchtest."))
    for fach, themen in _fach_optionen(kind):
        if art == "fach" and fach.pk == int(nr):
            return fach, None
        for thema in themen:
            if art == "thema" and thema.pk == int(nr):
                return fach, thema
    raise services.LernenFehler(_("Bitte wähle aus, was du üben möchtest."))


@nur_kind
@require_POST
def los(request):
    kind = aktuelles_kind(request)
    p = request.POST
    try:
        fach, thema = _auswahl(kind, p.get("was", ""))
        neue = services.sitzung_starten(
            kind,
            fach,
            thema=thema,
            intensitaet=p.get("intensitaet", Intensitaet.NORMAL),
            vorhaben=p.get("vorhaben", Vorhaben.WIEDERHOLEN),
            strategie=p.get("strategie", Strategie.ABDECKEN),
            erwartung=p.get("erwartung", Erwartung.EINIGES),
        )
    except services.LernenFehler as fehler:
        return render(
            request, "lernen/start.html", _start_kontext(kind, fehler=str(fehler)), status=400
        )
    return redirect("lernen:sitzung", pk=neue.pk)


@nur_kind
@require_POST
def ziel_vorschlag(request, aktion):
    if aktion not in ("annehmen", "lassen"):
        raise Http404
    services.vorschlag_entscheiden(aktuelles_kind(request), annehmen=aktion == "annehmen")
    return redirect("lernen:start")


# --- Kind: Sitzung -----------------------------------------------------------------------------


def _eigene(request, pk):
    kind = aktuelles_kind(request)
    sitzung_ = selectors.sitzung(kind, pk)
    if sitzung_ is None:
        raise Http404
    return kind, sitzung_


def _zustand(request, sitzung_, *, rueckmeldung=None, hinweis="", fehler="", erklaerung=""):
    """Zeigt den Stand der Sitzung: Frage, Rückmeldung, Rückschau oder Ergebnis. Bei HTMX nur
    der austauschbare Teil."""
    kind = sitzung_.kind
    wort = _wortwahl(kind, sitzung_.fach)
    zustand = selectors.zustand(sitzung_)
    aufgabe = None
    # Nach einer Antwort steht erst die Rückmeldung; nur bei "fast richtig" bleibt die Frage
    if zustand == "frage" and (rueckmeldung is None or rueckmeldung.nochmal):
        aufgabe = services.frage_stellen(sitzung_)
        if aufgabe is None:
            services.sitzung_beenden(sitzung_)
            zustand = selectors.zustand(sitzung_)
    kontext = {
        "s": sitzung_,
        "zustand": zustand,
        "aufgabe": aufgabe,
        "rueckmeldung": rueckmeldung,
        "hinweis": hinweis,
        "fehler": fehler,
        "erklaerung": erklaerung,
        "einschaetzungen": Selbsteinschaetzung.choices,
        "nummer": min(sitzung_.versuche + 1, sitzung_.ziel_fragen),
        "fortschritt": range(sitzung_.ziel_fragen),
        "ton_frust": wort("frust"),
        "ton_ziel": wort("ziel_geschafft"),
    }
    kontext.update(services.hilfe_kontext(sitzung_, aufgabe))
    if sitzung_.portion_id:
        portion = sitzung_.portion
        portion.refresh_from_db()
        kontext.update(
            portion=portion,
            portion_erledigt=portion.status == PortionStatus.ERLEDIGT,
            ton_portion=plan_texte.ton(
                "portion_geschafft", selectors.sprachstufe(kind, sitzung_.fach)
            ),
        )
    if zustand in ("rueckschau", "fertig"):
        heute = zeit.heute()
        bild = selectors.tagesbild(kind, heute)
        vergleich = selectors.vergleich(sitzung_)
        kontext.update(
            bild=bild,
            quote=selectors.quote(sitzung_),
            minuten=sitzung_.dauer_sekunden // 60,
            ton_ende=wort("ende"),
            ton_vergleich=wort(f"vergleich_{vergleich}") if vergleich else "",
        )
    vorlage = "lernen/_zustand.html" if _hx(request) else "lernen/sitzung.html"
    return render(request, vorlage, kontext)


@nur_kind
def sitzung(request, pk):
    _kind, sitzung_ = _eigene(request, pk)
    return _zustand(request, sitzung_)


def _geschuetzt(funktion):
    """Fehler beim Üben (z. B. doppelt abgeschickt) zeigen die Sitzung neu, statt abzustürzen."""

    def umhuellung(request, pk):
        _kind, sitzung_ = _eigene(request, pk)
        try:
            return funktion(request, sitzung_)
        except services.LernenFehler as fehler:
            return _zustand(request, sitzung_, fehler=str(fehler))

    umhuellung.__name__ = funktion.__name__
    return nur_kind(require_POST(umhuellung))


@_geschuetzt
def antwort(request, sitzung_):
    rueckmeldung = services.antworten(sitzung_, request.POST.get("eingabe", ""))
    return _zustand(request, sitzung_, rueckmeldung=rueckmeldung)


@_geschuetzt
def hilfe(request, sitzung_):
    hinweis = services.hilfe(sitzung_)
    return _zustand(request, sitzung_, hinweis=hinweis)


@_geschuetzt
def erklaerung(request, sitzung_):
    """ "Erkläre es anders" (Mathe, nur mit Tutor): andere Worte zu Karte und Beispiel."""
    try:
        text = mathe_ki.erklaerung_anders(sitzung_)
    except tutor_services.TutorFehler as fehler:
        return _zustand(request, sitzung_, fehler=str(fehler))
    return _zustand(request, sitzung_, erklaerung=text)


@_geschuetzt
def loesung(request, sitzung_):
    return _zustand(request, sitzung_, rueckmeldung=services.loesung_zeigen(sitzung_))


@_geschuetzt
def beenden(request, sitzung_):
    services.sitzung_beenden(sitzung_)
    return _zustand(request, sitzung_)


@_geschuetzt
def rueckschau(request, sitzung_):
    p = request.POST
    services.rueckschau_speichern(
        sitzung_, p.get("schwer", ""), p.get("geholfen", ""), p.get("einschaetzung", "")
    )
    return _zustand(request, sitzung_)


# --- Eltern ------------------------------------------------------------------------------------


def _eltern_kontext(*, fehler=""):
    heute = zeit.heute()
    kinder = list(konten.aktive_kinder())
    return {
        "zeilen": [
            (k, selectors.tagesbild(k, heute), selectors.tage_der_woche(k, heute)) for k in kinder
        ],
        "kinder": kinder,
        "pausen": selectors.pausen().select_related("kind"),
        "gruende": PausenGrund.choices,
        "heute": heute,
        "fehler": fehler,
    }


@nur_eltern
def eltern_seite(request):
    return render(request, "lernen/eltern.html", _eltern_kontext())


@nur_eltern
@require_POST
def pause_neu(request):
    p = request.POST
    try:
        kind = None
        if p.get("kind"):
            kind = get_object_or_404(konten.aktive_kinder(), pk=p["kind"])
        services.pause_eintragen(
            kind,
            date.fromisoformat(p.get("von", "")),
            date.fromisoformat(p.get("bis", "")),
            p.get("grund", PausenGrund.KRANK),
        )
    except (ValueError, ValidationError, services.LernenFehler):
        return render(
            request,
            "lernen/eltern.html",
            _eltern_kontext(fehler=_("Bitte Anfang und Ende prüfen (Ende nicht vor dem Anfang).")),
            status=400,
        )
    return redirect("lernen:eltern")


@nur_eltern
@require_POST
def pause_loeschen(request, pk):
    services.pause_loeschen(get_object_or_404(Lernpause, pk=pk))
    return redirect("lernen:eltern")
