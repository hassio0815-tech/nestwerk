"""Seiten der Prüfungsvorbereitung (SPEC 21.7).

Kind: Prüfung anlegen, Plan als Tagesübersicht, "Heute dran" mit Start der Portion, Realitätscheck,
Probe-Prüfung. Eine fremde Prüfung ist ein 404. Eltern: lesen, den Termin ändern, löschen; in den
Plan greifen sie nicht ein.
"""

from datetime import date, timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.kern import zeit
from apps.konten import selectors as konten
from apps.konten.zugriff import aktuelles_kind, nur_eltern, nur_kind

from . import plan, plan_selectors, plan_services, plan_texte, selectors
from .models import PortionArt
from .plan_services import PlanFehler
from .services import LernenFehler

_PROBE_TON = {"staerke": "probe_staerke", "mitte": "probe_mitte", "ueben": "probe_ueben"}


def _hx(request):
    return request.headers.get("HX-Request") == "true"


def _wort(kind, fach=None):
    stufe = selectors.sprachstufe(kind, fach)
    return lambda schluessel, **parameter: plan_texte.ton(schluessel, stufe, **parameter)


def _datum(text):
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        raise PlanFehler(_("Bitte wähle einen Tag für die Prüfung aus.")) from None


# --- Kind: Liste und Anlegen ------------------------------------------------------------------


@nur_kind
def liste(request):
    kind = aktuelles_kind(request)
    plan_services.tag_pflegen(kind)
    zeilen = [
        (p, plan_selectors.fortschritt(p))
        for p in plan_selectors.pruefungen(kind).filter(status__in=plan_selectors.AKTIVE)
    ]
    alte = plan_selectors.pruefungen(kind).exclude(status__in=plan_selectors.AKTIVE)
    return render(request, "lernen/pruefung_liste.html", {"zeilen": zeilen, "alte": alte})


def _neu_kontext(kind, fach, *, werte=None, fehler=""):
    heute = zeit.heute()
    return {
        "faecher": selectors.faecher(),
        "fach": fach,
        "themen": plan_selectors.themen_zur_auswahl(kind, fach) if fach else [],
        "materialien": plan_selectors.materialien_zur_auswahl(kind, fach) if fach else [],
        "werte": werte or {},
        "fehler": fehler,
        "morgen": heute + timedelta(days=1),
    }


def _fach_waehlen(request, daten):
    nr = str(daten.get("fach", ""))
    if nr.isdigit():
        return selectors.faecher().filter(pk=int(nr)).first()
    return selectors.faecher().first()


@nur_kind
def neu(request):
    kind = aktuelles_kind(request)
    fach = _fach_waehlen(request, request.GET)
    vorlage = "lernen/_pruefung_stoff.html" if _hx(request) else "lernen/pruefung_neu.html"
    return render(request, vorlage, _neu_kontext(kind, fach))


@nur_kind
@require_POST
def anlegen(request):
    kind = aktuelles_kind(request)
    p = request.POST
    fach = _fach_waehlen(request, p)
    try:
        if fach is None:
            raise PlanFehler(_("Bitte wähle ein Fach aus."))
        neue = plan_services.pruefung_anlegen(
            kind,
            fach,
            p.get("titel", ""),
            _datum(p.get("termin", "")),
            themen=[int(i) for i in p.getlist("thema") if i.isdigit()],
            materialien=[int(i) for i in p.getlist("material") if i.isdigit()],
        )
    except (PlanFehler, LernenFehler) as fehler:
        kontext = _neu_kontext(kind, fach, werte=p, fehler=str(fehler))
        return render(request, "lernen/pruefung_neu.html", kontext, status=400)
    return redirect("lernen:pruefung", pk=neue.pk)


# --- Kind: eine Prüfung -----------------------------------------------------------------------


def _eigene(request, pk):
    kind = aktuelles_kind(request)
    p = plan_selectors.pruefung(kind, pk)
    if p is None:
        raise Http404
    return kind, p


def _vorschlag_texte(wort, check):
    texte = []
    for v in check.vorschlaege:
        parameter = {
            plan.VORSCHLAG_FRUEHER: {"tage": v.wert},
            plan.VORSCHLAG_KLEINER: {"fragen": v.wert},
            plan.VORSCHLAG_ZIEL: {"minuten": v.wert},
        }[v.art]
        texte.append((v, wort(f"vorschlag_{v.art}", **parameter)))
    return texte


def _detail_kontext(kind, p, *, fehler=""):
    heute = zeit.heute()
    wort = _wort(kind, p.fach)
    aktiv = p.status in plan_selectors.AKTIVE
    kontext = {
        "p": p,
        "fehler": fehler,
        "aktiv": aktiv,
        "heute": heute,
        "fortschritt": plan_selectors.fortschritt(p),
        "dran": plan_selectors.heute_dran(p, heute) if aktiv else [],
        "puffer_heute": plan_selectors.heute_puffer(p, heute),
        "tage": plan_selectors.tagesuebersicht(p),
        "stoffe": list(p.stoffe.select_related("thema", "material")),
        "tage_bis": (p.termin - heute).days,
        "ton_angepasst": wort("angepasst") if p.plan_angepasst_am == heute else "",
        "ton_puffer": wort("puffer_genutzt") if p.puffer_genutzt else "",
        "ton_frei": wort("heute_frei"),
        "ton_puffer_heute": wort("heute_puffer"),
        "ton_geschafft": wort("portion_geschafft"),
        "probe": plan_selectors.offene_probe(p),
        "letzte_probe": plan_selectors.letzte_probe(p),
        "art_puffer": PortionArt.PUFFER,
    }
    if aktiv and not p.plan_ok:
        check = plan_selectors.realitaetscheck(p, heute)
        kontext["check"] = check
        if check.grund == plan.GRUND_ZU_VIEL:
            kontext["ton_zu_viel"] = wort("zu_viel", braucht=check.benoetigt, hat=check.verfuegbar)
            kontext["vorschlaege"] = _vorschlag_texte(wort, check)
            kontext["ton_keiner"] = wort("vorschlag_keiner") if not check.vorschlaege else ""
        elif check.grund == plan.GRUND_KEIN_STOFF:
            kontext["ton_zu_viel"] = wort("kein_stoff")
        pausen = len(plan_selectors.pausentage_im_plan(kind, heute, p.termin))
        kontext["ton_pausen"] = wort("pause_im_zeitraum", tage=pausen) if pausen else ""
        kontext["knapp"] = wort("knapp") if check.knapp else ""
    elif aktiv and (p.termin - heute).days < plan_selectors.parameter(kind, heute).vorlauf:
        kontext["knapp"] = wort("knapp")
    return kontext


def _detail(request, kind, p, *, fehler="", status=200):
    return render(
        request, "lernen/pruefung.html", _detail_kontext(kind, p, fehler=fehler), status=status
    )


@nur_kind
def detail(request, pk):
    kind, p = _eigene(request, pk)
    plan_services.tag_pflegen(kind)
    p.refresh_from_db()
    return _detail(request, kind, p)


def _aktion(funktion):
    """Fehler zeigen die Prüfung neu mit freundlichem Hinweis, statt abzustürzen."""

    def umhuellung(request, pk, **kwargs):
        kind, p = _eigene(request, pk)
        try:
            ziel = funktion(request, kind, p, **kwargs)
        except PlanFehler as fehler:
            return _detail(request, kind, p, fehler=str(fehler), status=400)
        return ziel or redirect("lernen:pruefung", pk=p.pk)

    umhuellung.__name__ = funktion.__name__
    return nur_kind(require_POST(umhuellung))


@_aktion
def portion_start(request, kind, p, portion_pk):
    portion = plan_selectors.portion(kind, portion_pk)
    if portion is None or portion.pruefung_id != p.pk:
        raise Http404
    sitzung = plan_services.portion_starten(kind, portion)
    return redirect("lernen:sitzung", pk=sitzung.pk)


@_aktion
def ziel_erhoehen(request, kind, p):
    try:
        minuten = int(request.POST.get("minuten", ""))
    except ValueError:
        raise PlanFehler(_("Dieses Ziel ist nicht möglich.")) from None
    plan_services.ziel_erhoehen(kind, p, minuten)


@_aktion
def stoff_entfernen(request, kind, p, stoff_pk):
    plan_services.stoff_entfernen(p, get_object_or_404(p.stoffe, pk=stoff_pk))


@_aktion
def neu_planen(request, kind, p):
    plan_services.plan_berechnen(p, nachholen=bool(p.portionen.exists()))


@_aktion
def abbrechen(request, kind, p):
    plan_services.pruefung_abbrechen(p)
    return redirect("lernen:pruefungen")


# --- Kind: Probe-Prüfung ----------------------------------------------------------------------


def _probe_eigene(request, pk):
    kind = aktuelles_kind(request)
    probe = plan_selectors.probe(kind, pk)
    if probe is None:
        raise Http404
    return kind, probe


def _probe_zeigen(request, kind, probe, *, fehler=""):
    wort = _wort(kind, probe.pruefung.fach)
    aufgabe = None if probe.ende else plan_services.probe_aufgabe(probe)
    kontext = {"probe": probe, "p": probe.pruefung, "aufgabe": aufgabe, "fehler": fehler}
    if probe.ende:
        ergebnisse = plan_services.probe_ergebnis(probe)
        kontext.update(
            ergebnisse=[
                (
                    e,
                    wort(
                        {"staerke": "probe_staerke", "mitte": "probe_mitte"}.get(
                            e.einstufung, "probe_ueben"
                        )
                    ),
                )
                for e in ergebnisse
            ],
            ton_hinweis=wort("probe_hinweis"),
            schwaechen=len(plan_services.schwaechen(probe)),
        )
    vorlage = "lernen/_probe.html" if _hx(request) else "lernen/probe.html"
    return render(request, vorlage, kontext)


@_aktion
def probe_start(request, kind, p):
    probe = plan_services.probe_starten(p)
    return redirect("lernen:probe", pk=probe.pk)


@nur_kind
def probe(request, pk):
    kind, probe_ = _probe_eigene(request, pk)
    return _probe_zeigen(request, kind, probe_)


@nur_kind
@require_POST
def probe_antwort(request, pk):
    kind, probe_ = _probe_eigene(request, pk)
    try:
        plan_services.probe_antworten(probe_, request.POST.get("eingabe", ""))
    except PlanFehler as fehler:
        return _probe_zeigen(request, kind, probe_, fehler=str(fehler))
    probe_.refresh_from_db()
    return _probe_zeigen(request, kind, probe_)


@nur_kind
@require_POST
def probe_schwaechen(request, pk):
    _kind, probe_ = _probe_eigene(request, pk)
    plan_services.schwaechen_einplanen(probe_)
    return redirect("lernen:pruefung", pk=probe_.pruefung_id)


# --- Eltern: mitlesen -------------------------------------------------------------------------


def _eltern_zeile(p, heute):
    return {
        "p": p,
        "fortschritt": plan_selectors.fortschritt(p),
        "problem": p.status in plan_selectors.AKTIVE and not p.plan_ok,
        "vorbei": p.termin < heute and p.status in plan_selectors.AKTIVE,
    }


@nur_eltern
def eltern_liste(request):
    heute = zeit.heute()
    kinder = [
        (k, [_eltern_zeile(p, heute) for p in plan_selectors.alle_fuer_eltern(k)])
        for k in konten.aktive_kinder()
    ]
    return render(request, "lernen/eltern_pruefungen.html", {"kinder": kinder, "heute": heute})


def _eltern_detail(request, p, *, fehler="", status=200):
    heute = zeit.heute()
    kontext = {
        "p": p,
        "fehler": fehler,
        "fortschritt": plan_selectors.fortschritt(p),
        "tage": plan_selectors.tagesuebersicht(p),
        "stoffe": list(p.stoffe.select_related("thema", "material")),
        "heute": heute,
        "morgen": heute + timedelta(days=1),
        "art_puffer": PortionArt.PUFFER,
        "aktiv": p.status in plan_selectors.AKTIVE,
    }
    if kontext["aktiv"] and not p.plan_ok:
        kontext["check"] = plan_selectors.realitaetscheck(p, heute)
    return render(request, "lernen/eltern_pruefung.html", kontext, status=status)


@nur_eltern
def eltern_detail(request, pk):
    p = plan_selectors.fuer_eltern(pk)
    if p is None:
        raise Http404
    return _eltern_detail(request, p)


@nur_eltern
@require_POST
def eltern_termin(request, pk):
    p = plan_selectors.fuer_eltern(pk)
    if p is None:
        raise Http404
    try:
        plan_services.termin_aendern(p, _datum(request.POST.get("termin", "")))
    except PlanFehler as fehler:
        return _eltern_detail(request, p, fehler=str(fehler), status=400)
    return redirect("lernen:eltern_pruefung", pk=p.pk)


@nur_eltern
@require_POST
def eltern_loeschen(request, pk):
    p = plan_selectors.fuer_eltern(pk)
    if p is None:
        raise Http404
    plan_services.pruefung_loeschen(p)
    return redirect("lernen:eltern_pruefungen")
