"""Middleware von konten, Reihenfolge in den Settings: Session, Locale, Auth, dann diese."""

from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.utils import translation

from apps.kern import audit, zeit

from . import geraet as geraet_modul
from . import sitzung
from .zugriff import ist_passiv


class GeraetMiddleware:
    """Setzt ``request.geraet`` (registriertes Gerät aus dem signierten Cookie oder ``None``)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.geraet = geraet_modul.geraet_aus_cookie(request)
        return self.get_response(request)


class BenutzerSprache:
    """Eigene Sprache des angemeldeten Benutzers schlägt Geräte-Cookie und Browser-Sprache."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        sprache = getattr(user, "sprache", "") if user and user.is_authenticated else ""
        if sprache:
            translation.activate(sprache)
            request.LANGUAGE_CODE = sprache
        return self.get_response(request)


class SitzungsRichtlinie:
    """Kiosk: Sitzung endet nach Leerlauf. Nur **aktive** Anfragen verlängern; Views mit
    ``@passiv`` (Polling) prüfen den Ablauf, verlängern aber nicht."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        jetzt = zeit.jetzt().timestamp()
        if sitzung.geraet_widerrufen(request):
            sitzung.wegen_leerlauf_abmelden(request, grund="geraet_widerrufen")
            return self._abgelaufen(request)
        if sitzung.ist_kiosk_sitzung(request):
            if sitzung.leerlauf_abgelaufen(request, jetzt):
                sitzung.wegen_leerlauf_abmelden(request)
                return self._abgelaufen(request)
        if not ist_passiv(view_func):
            sitzung.aktivitaet_vermerken(request, jetzt)
        return None

    @staticmethod
    def _abgelaufen(request):
        ziel = resolve_url("konten:start")
        if request.headers.get("HX-Request") or request.headers.get("X-Requested-With"):
            return HttpResponse(status=401, headers={"HX-Redirect": ziel})
        return redirect(ziel)


class AuditKontextMiddleware:
    """Macht Akteur und Gerät der Anfrage für ``kern.audit.protokollieren`` verfügbar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        def anbieter():
            user = request.user
            return (user if user.is_authenticated else None), getattr(request, "geraet", None)

        with audit.kontext(anbieter):
            return self.get_response(request)
