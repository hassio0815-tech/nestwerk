"""Einstellungen von lernen auf einer eigenen Seite (Etappe 13, E-5).

Bisher waren sie nur im allgemeinen Editor erreichbar. Hier stehen die, die Eltern wirklich
anfassen: Tagesziel, Punkte, Ferien, Titel, Tutor, neue Vokabeln pro Tag, Denkpause, Meldungen
an die Eltern und die Rechenarten. Gespeichert wird alles oder nichts; jede Änderung landet im
Audit-Log (``einstellungen.setzen``).
"""

from django.shortcuts import redirect, render
from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_http_methods

from apps.kern import einstellungen
from apps.kern.einstellungen import EinstellungFehler, Typ
from apps.konten.zugriff import nur_eltern

from .mathe import registry as mathe_registry

PRAEFIX = "lernen."

# (Überschrift, Schlüssel ohne Präfix); Reihenfolge = Reihenfolge auf der Seite
GRUPPEN = (
    (
        gettext_noop("Üben"),
        ("tagesziel_minuten", "lernpunkte_aktiv", "leerlauf_sekunden", "pause_nach_minuten"),
    ),
    (gettext_noop("Schonung"), ("ferien_schalter",)),
    (gettext_noop("Anerkennung"), ("titel_anzeigen",)),
    (gettext_noop("Tutor"), ("tutor_aktiv",)),
    (
        gettext_noop("Neue Vokabeln pro Tag"),
        ("neu_vokabeln_bis_klasse5", "neu_vokabeln_klasse6_7", "neu_vokabeln_ab_klasse8"),
    ),
    (
        gettext_noop("Meldungen an die Eltern"),
        ("eltern_hinweise_aktiv", "digest_aktiv", "digest_wochentag", "digest_uhrzeit"),
    ),
)


def _felder():
    schluessel = [k for _g, ks in GRUPPEN for k in ks]
    return {k: einstellungen.definition(PRAEFIX + k) for k in schluessel}


def _kontext(*, fehler="", eingabe=None):
    definitionen = _felder()
    gruppen = []
    for titel, schluessel in GRUPPEN:
        felder = []
        for k in schluessel:
            d = definitionen[k]
            wert = einstellungen.wert(PRAEFIX + k)
            if eingabe is not None and k in eingabe:
                wert = eingabe[k]
            elif eingabe is not None and d.typ is Typ.BOOL:
                wert = False
            if d.typ is Typ.UHRZEIT and not isinstance(wert, str):
                wert = wert.strftime("%H:%M")
            felder.append(
                {
                    "name": k,
                    "typ": d.typ.value,
                    "label": d.bezeichnung,
                    "hilfe": d.beschreibung,
                    "einheit": d.einheit,
                    "minimum": d.minimum,
                    "maximum": d.maximum,
                    "wert": wert,
                }
            )
        gruppen.append((titel, felder))
    aus = set(einstellungen.wert("lernen.mathe_rechenarten_aus"))
    rechenarten = [(k, g.name, k not in aus) for k, g in mathe_registry.alle().items()]
    return {
        "gruppen": gruppen,
        "rechenarten": rechenarten,
        "wochentage": sorted(WEEKDAYS.items()),
        "fehler": fehler,
    }


def _lesen(post):
    """``{schluessel: wert}`` aus dem Formular; ``ValueError`` bei Unlesbarem."""
    neu = {}
    for k, d in _felder().items():
        if d.typ is Typ.BOOL:
            neu[PRAEFIX + k] = post.get(k) in ("on", "1", "true")
        elif k not in post:
            continue
        elif d.typ is Typ.GANZZAHL:
            neu[PRAEFIX + k] = int(post[k])
        else:
            neu[PRAEFIX + k] = post[k]
    if post.get("rechenarten_form"):
        an = set(post.getlist("rechenarten_an"))
        neu[PRAEFIX + "mathe_rechenarten_aus"] = [
            k for k in mathe_registry.schluessel_alle() if k not in an
        ]
    return neu


@nur_eltern
@require_http_methods(["GET", "POST"])
def eltern_einstellungen(request):
    if request.method == "GET":
        return render(request, "lernen/eltern_einstellungen.html", _kontext())
    try:
        neu = _lesen(request.POST)
        for schluessel, wert in neu.items():
            einstellungen.definition(schluessel).pruefen(wert)
    except (ValueError, EinstellungFehler):
        return render(
            request,
            "lernen/eltern_einstellungen.html",
            _kontext(
                fehler=_("Bitte die Eingaben prüfen. Es wurde nichts gespeichert."),
                eingabe=request.POST,
            ),
            status=400,
        )
    for schluessel, wert in neu.items():
        einstellungen.setzen(schluessel, wert)
    return redirect("lernen:eltern_einstellungen")
