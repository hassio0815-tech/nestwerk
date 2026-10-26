"""Anmelde- und Geräteseiten (ARCHITECTURE 4). Die Dashboards selbst liefert ``oberflaeche``;
``kind_heim`` und ``eltern_heim`` sind Platzhalter, bis diese Schicht sie ersetzt."""

from django.contrib import auth
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.kern import audit, zeit

from . import akzent, begruessung, netz, selectors, services, sitzung, sperre
from .geraet import cookie_loeschen, cookie_setzen
from .models import Benutzer, Geraet, GeraeteTyp, Rolle
from .zugriff import nur_eltern, nur_kind

MELDUNG_FALSCH = "Das hat nicht gepasst. Versuch es noch einmal."


def _heim(user):
    return reverse("konten:eltern_heim" if user.rolle == Rolle.ELTERN else "konten:kind_heim")


def _nach_login(user):
    """Eltern landen im Modul-Launcher (oberflaeche), sonst im eigenen Heim."""
    if user.rolle == Rolle.ELTERN:
        try:
            return reverse("oberflaeche:module")
        except NoReverseMatch:
            pass
    return _heim(user)


def _weiter(request, user):
    ziel = request.POST.get("next") or request.GET.get("next") or ""
    if ziel and url_has_allowed_host_and_scheme(
        ziel, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(ziel)
    return redirect(_nach_login(user))


def _minuten_text(bis):
    rest = max(int((bis - zeit.jetzt()).total_seconds()), 0)
    minuten = -(-rest // 60)  # aufrunden
    return f"{minuten} Minute{'n' if minuten != 1 else ''}"


@require_GET
def start(request):
    """Tablet-/Familien-Startseite: Avatar-Kacheln der Kinder (nur Lesen, ohne Anmeldung)."""
    if request.user.is_authenticated:
        return redirect(_heim(request.user))
    jetzt = zeit.jetzt()
    kinder = [
        {
            "benutzer": kind,
            "akzent": akzent.akzent_name(kind),
            "gesperrt": bool(sperre.kind_gesperrt_bis(kind.kindprofil, jetzt)),
        }
        for kind in selectors.aktive_kinder()
    ]
    return render(
        request,
        "konten/start.html",
        {"kinder": kinder, "eltern": selectors.aktive_eltern(), "gruss": begruessung.gruss()},
    )


@require_http_methods(["GET", "POST"])
def kind_pin(request, kind_id):
    if request.user.is_authenticated:
        return redirect(_heim(request.user))
    kind = get_object_or_404(selectors.aktive_kinder(), pk=kind_id)
    kontext = {
        "kind": kind,
        "akzent": akzent.akzent_name(kind),
        "next": request.GET.get("next", ""),
    }

    if not netz.kind_login_erlaubt(request):
        kontext["fehler"] = "Die Anmeldung geht nur im Heimnetz."
        return render(request, "konten/pin.html", kontext, status=403)

    gesperrt_bis = selectors.kind_gesperrt_bis(kind)
    if request.method == "GET" or gesperrt_bis:
        if gesperrt_bis:
            kontext["fehler"] = f"Gesperrt. Versuch es in {_minuten_text(gesperrt_bis)} wieder."
        return render(request, "konten/pin.html", kontext, status=429 if gesperrt_bis else 200)

    benutzer = auth.authenticate(request, kind=kind, pin=request.POST.get("pin", ""))
    if benutzer is None:
        gesperrt_bis = selectors.kind_gesperrt_bis(kind)
        if gesperrt_bis:
            audit.protokollieren(
                "konten.pin_gesperrt",
                akteur=kind,
                kind=kind,
                details={"bis": gesperrt_bis.isoformat()},
            )
            kontext["fehler"] = f"Gesperrt. Versuch es in {_minuten_text(gesperrt_bis)} wieder."
            return render(request, "konten/pin.html", kontext, status=429)
        kontext["fehler"] = MELDUNG_FALSCH
        return render(request, "konten/pin.html", kontext, status=401)

    sitzung.sitzung_beginnen(request, benutzer)
    return _weiter(request, benutzer)


@require_http_methods(["GET", "POST"])
def eltern_login(request):
    if request.user.is_authenticated:
        return redirect(_heim(request.user))
    kontext = {"eltern": selectors.aktive_eltern(), "next": request.GET.get("next", "")}
    gewaehlt = _uuid(request.POST.get("eltern") or request.GET.get("eltern"))
    kontext["gewaehlt"] = kontext["eltern"].filter(pk=gewaehlt).first() if gewaehlt else None
    if request.method == "GET":
        return render(request, "konten/eltern_login.html", kontext)

    ip = netz.client_ip_text(request)
    gesperrt_bis = sperre.eltern_gesperrt_bis(ip, zeit.jetzt())
    if gesperrt_bis:
        kontext["fehler"] = f"Zu viele Versuche. Bitte in {_minuten_text(gesperrt_bis)} wieder."
        return render(request, "konten/eltern_login.html", kontext, status=429)

    elternteil = selectors.aktive_eltern().filter(pk=_uuid(request.POST.get("eltern"))).first()
    benutzer = None
    if elternteil is not None:
        benutzer = auth.authenticate(
            request, eltern=elternteil, passwort=request.POST.get("passwort", "")
        )
    if benutzer is None:
        kontext["fehler"] = MELDUNG_FALSCH
        return render(request, "konten/eltern_login.html", kontext, status=401)

    sitzung.sitzung_beginnen(request, benutzer, vertraut=request.POST.get("vertraut") == "on")
    return _weiter(request, benutzer)


def _uuid(text):
    try:
        return Benutzer._meta.pk.to_python(text)
    except (ValidationError, TypeError):
        return None


@require_POST
def abmelden(request):
    if request.user.is_authenticated:
        audit.protokollieren("konten.abgemeldet")
        auth.logout(request)
    return redirect("konten:start")


@require_POST
def aktiv(request):
    """Aktiver Herzschlag des Leerlauf-Timers im Browser (Touch/Klick): zählt als Aktivität.
    Im Gegensatz zum Polling ist diese View **nicht** ``@passiv``."""
    return HttpResponse(status=204)


@nur_kind
def kind_heim(request):
    return render(request, "konten/kind_heim.html")


@nur_eltern
def eltern_heim(request):
    return render(
        request,
        "konten/eltern_heim.html",
        {"gesperrte_kinder": selectors.gesperrte_kinder()},
    )


@nur_eltern
@require_http_methods(["GET", "POST"])
def geraete(request):
    kontext = {"typen": GeraeteTyp.choices}
    if request.method == "POST":
        bezeichnung = request.POST.get("bezeichnung", "")
        try:
            geraet = services.geraet_registrieren(
                bezeichnung, request.POST.get("typ", ""), registriert_von=request.user
            )
        except ValidationError as fehler:
            kontext["fehler"] = " ".join(fehler.messages)
        else:
            antwort = redirect("konten:geraete")
            cookie_setzen(request, antwort, geraet)
            if request.session.get(sitzung.GERAET):
                # Diese Sitzung gehört jetzt zum neu registrierten Gerät (sonst endete sie)
                request.session[sitzung.GERAET] = str(geraet.pk)
            return antwort
    kontext["geraete"] = selectors.geraete()
    kontext["dieses"] = getattr(request, "geraet", None)
    return render(request, "konten/geraete.html", kontext)


@nur_eltern
@require_POST
def geraet_widerrufen(request, geraet_id):
    geraet = get_object_or_404(Geraet, pk=geraet_id, aktiv=True)
    services.geraet_widerrufen(geraet)
    antwort = redirect("konten:geraete")
    if getattr(request, "geraet", None) == geraet:
        cookie_loeschen(antwort)
    return antwort


@nur_eltern
@require_POST
def kind_entsperren(request, kind_id):
    kind = get_object_or_404(selectors.aktive_kinder(), pk=kind_id)
    services.kind_entsperren(kind)
    return redirect("konten:eltern_heim")
