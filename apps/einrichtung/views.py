"""Einrichtungs-Assistent: ein Schritt pro Seite, HTMX-Fragmente, Zwischenstand in der DB."""

import ipaddress
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

from django.http import Http404
from django.shortcuts import redirect, render, resolve_url
from django.views.decorators.http import require_http_methods

from apps.konten import akzent, begruessung
from apps.konten import selectors as konten_selectors

from . import forms, services, uebersicht, zustand
from .einstellungen import LETZTER_SCHRITT

SCHRITTE = [
    (1, "Willkommen"),
    (2, "Eltern"),
    (3, "Kinder"),
    (4, "E-Mail"),
    (5, "Netzwerk"),
    (6, "Zeit"),
    (7, "Startwerte"),
    (8, "Abschluss"),
]
TITEL = dict(SCHRITTE)
KINDER_STARTZEILEN = 3


def _zugang(view, *, mit_token):
    @wraps(view)
    def innen(request, *args, **kwargs):
        if zustand.abgeschlossen():
            raise Http404("Die Einrichtung ist abgeschlossen.")
        if mit_token and not zustand.token_ok(request):
            return redirect("einrichtung:token")
        return view(request, *args, **kwargs)

    return innen


def zugang(view):
    """Gesperrt nach Abschluss (404); mit gesetztem ``NESTWERK_SETUP_TOKEN`` nur mit Token."""
    return _zugang(view, mit_token=True)


def ohne_token(view):
    return _zugang(view, mit_token=False)


def _htmx(request):
    return bool(request.headers.get("HX-Request"))


def _darstellen(request, nr, kontext=None):
    kontext = dict(kontext or {})
    kontext.update(
        {
            "nr": nr,
            "schritte": LETZTER_SCHRITT,
            "schritt": nr,
            "schritt_titel": f"Schritt {nr}: {TITEL[nr]}",
            "schritt_liste": SCHRITTE,
            "inhalt": f"einrichtung/s{nr}.html",
            "zurueck_url": resolve_url("einrichtung:schritt", nr=nr - 1) if nr > 1 else "",
            "weiter_url": resolve_url("einrichtung:schritt", nr=nr),
            "app_name": services.app_name(),
            "gruss": begruessung.gruss(),
        }
    )
    vorlage = "einrichtung/_assistent.html" if _htmx(request) else "einrichtung/seite.html"
    return render(request, vorlage, kontext)


def _weiter(request, nr):
    ziel = resolve_url("einrichtung:schritt", nr=nr)
    if not _htmx(request):
        return redirect(ziel)
    antwort = _schritt_anzeigen(request, nr, POST=False)
    antwort["HX-Push-Url"] = ziel
    return antwort


def _heute():
    try:
        zone = ZoneInfo(services.zeit_werte(None)["zeitzone"])
    except Exception:
        zone = ZoneInfo("Europe/Berlin")
    return datetime.now(zone).date()


def _remote_privat(request):
    roh = request.META.get("REMOTE_ADDR", "")
    try:
        adresse = ipaddress.ip_address(roh)
    except ValueError:
        return ""
    return roh if not adresse.is_global else ""


# --- Schritte: je Funktion (request, post) -> Kontext zum Anzeigen oder None (gespeichert) -----


def _s1(request, post):
    if post:
        form = forms.AppNameForm(request.POST)
        if form.is_valid():
            services.app_name_speichern(form.cleaned_data["app_name"])
            return None
    else:
        form = forms.AppNameForm(initial={"app_name": services.app_name()})
    return {"form": form}


def _eltern_form(post=None):
    kinder = [k.anzeigename for k in konten_selectors.aktive_kinder()]
    kwargs = {"passwort_pflicht": not services.passwort_gesetzt(), "kinder_namen": kinder}
    if post is not None:
        return forms.ElternForm(post, **kwargs)
    return forms.ElternForm(initial=services.eltern_werte(), **kwargs)


def _s2(request, post):
    form = _eltern_form(request.POST if post else None)
    if post and form.is_valid():
        try:
            services.eltern_speichern(form.cleaned_data)
            return None
        except services.SchrittFehler as exc:
            for m in exc.meldungen:
                form.add_error(None, m)
    return {
        "form": form,
        "passwort_gesetzt": services.passwort_gesetzt(),
        "passwort_pflicht": not services.passwort_gesetzt(),
        "mindestlaenge": forms.PASSWORT_MINDESTLAENGE,
        "rollen": forms.ElternForm.base_fields["eltern1_rolle"].choices,
    }


def _s3(request, post):
    eltern = [b.anzeigename for b in konten_selectors.aktive_eltern()]
    allgemein = []
    if post:
        try:
            anzahl = max(1, min(int(request.POST.get("anzahl", KINDER_STARTZEILEN)), 30))
        except ValueError:
            anzahl = KINDER_STARTZEILEN
        zeilen = services.kinder_zeilen_lesen(request.POST, anzahl)
        if request.POST.get("aktion") == "mehr":
            for z in zeilen:  # PINs nie zurück ins HTML
                z.pin = z.pin2 = ""
            zeilen += services.kinder_zeilen_lesen({}, 0)
            zeilen.append(services.KindZeile(len(zeilen), "", "", "", "", "", {}))
        else:
            aktive, allgemein = services.kinder_pruefen(zeilen, eltern)
            if not allgemein and not any(z.fehler for z in aktive):
                try:
                    services.kinder_speichern(aktive)
                    return None
                except services.SchrittFehler as exc:
                    allgemein = exc.meldungen
            for z in zeilen:
                z.pin = z.pin2 = ""
    else:
        zeilen = services.kinder_zeilen_aus_db()
        while len(zeilen) < KINDER_STARTZEILEN:
            zeilen.append(services.KindZeile(len(zeilen), "", "", "", "", "", {}))
    return {
        "zeilen": zeilen,
        "anzahl": len(zeilen),
        "farben": list(akzent.PALETTE),
        "allgemein_fehler": allgemein,
    }


def _s4(request, post):
    gespeichert = services.smtp_gespeichert()
    ergebnis = None
    if post and request.POST.get("aktion") == "ueberspringen":
        services.smtp_ueberspringen()
        return None
    if post:
        form = forms.SmtpForm(request.POST, passwort_gespeichert=gespeichert)
        testen = request.POST.get("aktion") == "testen"
        if testen and not request.POST.get("testadresse", "").strip():
            eltern = konten_selectors.aktive_eltern().first()
            vorbelegt = konten_selectors.eltern_email(eltern) if eltern else ""
            daten = request.POST.copy()
            daten["testadresse"] = vorbelegt
            form = forms.SmtpForm(daten, passwort_gespeichert=gespeichert)
        if form.is_valid():
            if testen and not form.cleaned_data["testadresse"]:
                form.add_error("testadresse", "Bitte eine Adresse für die Testmail angeben.")
            else:
                try:
                    ergebnis = services.smtp_speichern(form.cleaned_data, testen=testen)
                    if not testen:
                        return None
                    gespeichert = True
                except services.SchrittFehler as exc:
                    for m in exc.meldungen:
                        form.add_error(None, m)
    else:
        werte = services.smtp_werte()
        eltern = konten_selectors.aktive_eltern().first()
        werte["testadresse"] = konten_selectors.eltern_email(eltern) if eltern else ""
        form = forms.SmtpForm(initial=werte, passwort_gespeichert=gespeichert)
    return {
        "form": form,
        "ergebnis": ergebnis,
        "passwort_gespeichert": gespeichert,
        "passwort_hilfe": "Gespeichert. Leer lassen, um es zu behalten."
        if gespeichert
        else "Wird verschlüsselt gespeichert.",
        "sicherheiten": forms.SmtpForm.base_fields["sicherheit"].choices,
    }


def _s5(request, post):
    remote = _remote_privat(request)
    if post:
        form = forms.NetzwerkForm(request.POST)
        if form.is_valid():
            try:
                services.netzwerk_speichern(form.cleaned_data)
                return None
            except services.SchrittFehler as exc:
                for m in exc.meldungen:
                    form.add_error(None, m)
    else:
        werte = services.netzwerk_werte(remote)
        from django.conf import settings

        werte["basis_url"] = werte["basis_url"] or getattr(settings, "BASIS_URL", "")
        form = forms.NetzwerkForm(initial=werte)
    return {"form": form, "remote": remote}


def _s6(request, post):
    if post:
        form = forms.ZeitForm(request.POST)
        if form.is_valid():
            try:
                services.zeit_speichern(form.cleaned_data)
                return None
            except services.SchrittFehler as exc:
                for m in exc.meldungen:
                    form.add_error(None, m)
    else:
        werte = services.zeit_werte(_heute())
        werte["go_live_datum"] = werte["go_live_datum"].isoformat()
        form = forms.ZeitForm(initial=werte)
    return {"form": form}


def _listen():
    """Katalog und Bibliothek nur zur Ansicht (über die Selectors der Fach-Module)."""
    from apps.aufgaben import selectors as aufgaben
    from apps.belohnung import selectors as belohnung

    return [
        {
            "titel": "Belohnungs-Katalog",
            "zeilen": [(b.titel, b.preis_punkte) for b in belohnung.katalog(nur_aktive=False)],
        },
        {
            "titel": "Aufgaben-Bibliothek",
            "zeilen": [(v.titel, v.punkte) for v in aufgaben.vorlagen()],
        },
    ]


def _s7(request, post):
    fehler = {}
    if post:
        aenderungen, fehler = uebersicht.pruefen(request.POST)
        if not fehler:
            services.startwerte_speichern(aenderungen)
            return None
    gruppen = uebersicht.felder(request.POST if post else None, fehler)
    return {"gruppen": gruppen, "fehler_anzahl": len(fehler), "listen": _listen()}


def _s8(request, post):
    if post:
        try:
            services.abschliessen()
            return None
        except services.SchrittFehler as exc:
            offen = exc.meldungen
    else:
        offen = services.offene_punkte()
    return {"z": services.zusammenfassung(), "offen": offen}


_HANDLER = {1: _s1, 2: _s2, 3: _s3, 4: _s4, 5: _s5, 6: _s6, 7: _s7, 8: _s8}


def _schritt_anzeigen(request, nr, POST):
    kontext = _HANDLER[nr](request, POST)
    if kontext is None:
        return _weiter(request, nr + 1)
    return _darstellen(request, nr, kontext)


def _fertig(request):
    antwort = render(
        request,
        "einrichtung/_assistent.html" if _htmx(request) else "einrichtung/seite.html",
        {"fertig": True, "app_name": services.app_name(), "schritte": 0},
    )
    antwort["HX-Push-Url"] = "false"
    return antwort


@zugang
def start(request):
    return redirect("einrichtung:schritt", nr=zustand.freigegebener_schritt())


@ohne_token
@require_http_methods(["GET", "POST"])
def token(request):
    if not zustand.erwartetes_token():
        return redirect("einrichtung:start")
    fehler = ""
    if request.method == "POST":
        if zustand.token_stimmt(request.POST.get("token")):
            request.session[zustand.SESSION_TOKEN_OK] = True
            return redirect("einrichtung:start")
        fehler = "Das Setup-Token stimmt nicht."
    return render(request, "einrichtung/token.html", {"fehler": fehler, "schritte": 0})


@zugang
@require_http_methods(["GET", "POST"])
def schritt(request, nr):
    if nr not in TITEL:
        raise Http404
    if nr > zustand.freigegebener_schritt():
        return redirect("einrichtung:schritt", nr=zustand.freigegebener_schritt())
    post = request.method == "POST"
    if nr == LETZTER_SCHRITT and post:
        if _s8(request, True) is None:
            return _fertig(request)
        return _darstellen(request, nr, _s8(request, False))
    return _schritt_anzeigen(request, nr, post)
