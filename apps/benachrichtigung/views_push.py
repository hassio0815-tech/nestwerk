"""PWA und Web-Push: Manifest, Service Worker, Offline-Seite, Abo-Endpunkte (AP08).

``/sw.js`` und ``/manifest.json`` sind öffentlich (kein Login, kein Redirect), ohne Cache
ausgeliefert. Abo-Endpunkte verlangen Anmeldung (JSON 401) und CSRF-Token; Kiosk-Sitzungen
(Tablet ohne Web-Push) werden abgewiesen.
"""

import json
import logging
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.konten import sitzung
from apps.konten.models import Rolle
from apps.konten.zugriff import nur_eltern

from . import push, registry
from . import pushschluessel as vapid

logger = logging.getLogger("nestwerk.benachrichtigung")

THEME_FARBE = "#0E6A80"  # Industrial Teal (branding/nestwerk/README.md)
HINTERGRUND_FARBE = "#F4F8F9"  # Splash-Hintergrund, passt zum Logo
AKZENT_FARBE = "#1B8DA6"  # Hauptton
ICON_PFAD = "benachrichtigung/icons/"
MAX_BODY = 4096


def _ohne_cache(antwort):
    antwort["Cache-Control"] = "no-cache"
    return antwort


@require_GET
def service_worker(request):
    antwort = render(
        request,
        "benachrichtigung/sw.js",
        {
            "offline_url": reverse("benachrichtigung:offline"),
            "icon_url": static(ICON_PFAD + "icon-192.png"),
            "badge_url": static(ICON_PFAD + "badge-96.png"),
            "start_url": "/",
        },
        content_type="text/javascript; charset=utf-8",
    )
    antwort["Service-Worker-Allowed"] = "/"
    return _ohne_cache(antwort)


def manifest_daten():
    def icon(name, groesse, zweck="any"):
        return {
            "src": static(ICON_PFAD + name),
            "sizes": f"{groesse}x{groesse}",
            "type": "image/png",
            "purpose": zweck,
        }

    return {
        "name": "Nestwerk",
        "short_name": "Nestwerk",
        "description": _("Das Familien-Dashboard"),
        "lang": get_language() or "de",
        "start_url": "/",
        "scope": "/",
        "id": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": HINTERGRUND_FARBE,
        "theme_color": THEME_FARBE,
        "icons": [
            icon("icon-180.png", 180),
            icon("icon-192.png", 192),
            icon("icon-512.png", 512),
            icon("icon-maskable-512.png", 512, "maskable"),
        ],
    }


@require_GET
def manifest(request):
    antwort = HttpResponse(
        json.dumps(manifest_daten(), ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )
    return _ohne_cache(antwort)


# Die Offline-Seite muss ohne weitere Dateien auskommen (Service-Worker-Cache): eigene CSP mit
# Inline-Style, aber ohne jedes Skript.
OFFLINE_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)


@require_GET
def offline(request):
    antwort = render(request, "benachrichtigung/offline.html", {"theme_farbe": THEME_FARBE})
    antwort["Content-Security-Policy"] = OFFLINE_CSP
    return antwort


# --- Abo-Flow --------------------------------------------------------------------------------


def _ist_kiosk(request):
    return sitzung.ist_kiosk_sitzung(request)


def _json_anmeldung(view):
    @wraps(view)
    def umhuellung(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"fehler": "Nicht angemeldet"}, status=401)
        if _ist_kiosk(request):
            return JsonResponse({"fehler": "Auf dem Tablet gibt es kein Push"}, status=403)
        return view(request, *args, **kwargs)

    return umhuellung


def _body(request):
    if len(request.body) > MAX_BODY:
        return None
    try:
        daten = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return daten if isinstance(daten, dict) else None


def push_kontext(request):
    """Kontext der Push-Karte (Seite ``push_geraet`` und Eltern-Einstellungen)."""
    kiosk = _ist_kiosk(request)
    schluessel = None
    if not kiosk:
        try:
            schluessel = vapid.oeffentlicher_schluessel()
        except OSError:
            logger.exception("VAPID-Schlüssel nicht lesbar/schreibbar (SECRETS_DIR)")
    return {
        "push_kiosk": kiosk,
        "push_schluessel": schluessel,
        "push_anzahl": 0 if kiosk else push.aktive_abos(request.user).count(),
        "push_ist_eltern": request.user.rolle == Rolle.ELTERN,
    }


def push_geraet(request):
    if not request.user.is_authenticated:
        return redirect("konten:start")
    layout = "basis/eltern.html" if request.user.rolle == Rolle.ELTERN else "basis/kind.html"
    return render(
        request, "benachrichtigung/push_geraet.html", {"layout": layout, **push_kontext(request)}
    )


@require_POST
@_json_anmeldung
def abo_anmelden(request):
    daten = _body(request)
    if daten is None:
        return JsonResponse({"fehler": "Ungültige Anfrage"}, status=400)
    try:
        abo = push.abo_speichern(
            request.user,
            daten.get("subscription") or daten,
            geraet=getattr(request, "geraet", None),
            user_agent=request.headers.get("User-Agent", ""),
            bezeichnung=str(daten.get("bezeichnung") or ""),
        )
    except push.UngueltigesAbo as exc:
        return JsonResponse({"fehler": str(exc)}, status=400)
    return JsonResponse({"ok": True, "id": abo.pk})


@require_POST
@_json_anmeldung
def abo_abmelden(request):
    daten = _body(request)
    if daten is None:
        return JsonResponse({"fehler": "Ungültige Anfrage"}, status=400)
    geloescht = push.abo_entfernen(request.user, str(daten.get("endpoint") or ""))
    return JsonResponse({"ok": True, "entfernt": geloescht})


@nur_eltern
@require_POST
def test_push(request):
    """Test-Push an alle Geräte des Elternteils; antwortet mit einem HTML-Schnipsel (HTMX)."""
    try:
        gesendet, fehler = push.probe_senden(request.user)
    except registry.NichtKonfiguriert as exc:
        text, art = str(exc), "fehler"
    else:
        if not gesendet and not fehler:
            text, art = (
                _("Noch kein Gerät angemeldet. Zuerst Benachrichtigungen aktivieren."),
                "fehler",
            )
        elif fehler:
            text, art = (
                _("%(gesendet)s gesendet, %(fehler)s fehlgeschlagen.")
                % {"gesendet": gesendet, "fehler": fehler},
                "fehler",
            )
        else:
            text, art = (
                _("Test an %(anzahl)s Gerät(e) gesendet.") % {"anzahl": gesendet},
                "ok",
            )
    return render(request, "benachrichtigung/_push_test_ergebnis.html", {"text": text, "art": art})
