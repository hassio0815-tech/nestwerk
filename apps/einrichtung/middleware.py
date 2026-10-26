"""Erzwingt den Einrichtungs-Assistenten (ARCHITECTURE AP16).

Solange ``allgemein.einrichtung_abgeschlossen`` nicht gesetzt ist, führt jede Anfrage zum
Assistenten (außer Gesundheitscheck, Static, Service Worker und Manifest). Der Assistent
selbst ist nur aus dem Heimnetz und, falls ``NESTWERK_SETUP_TOKEN`` gesetzt ist, mit Token
erreichbar. Nach Abschluss ist er gesperrt (404).
"""

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import resolve_url

from . import zustand

FREIE_PFADE = ("/gesundheit/", "/static/", "/sw.js", "/manifest.json")


class EinrichtungErzwingen:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "EINRICHTUNG_ERZWINGEN", True):
            return self.get_response(request)
        pfad = request.path
        im_assistenten = pfad.startswith(zustand.PRAEFIX)
        if zustand.abgeschlossen():
            if im_assistenten:
                raise Http404("Die Einrichtung ist abgeschlossen.")
            return self.get_response(request)
        if pfad.startswith(FREIE_PFADE):
            return self.get_response(request)
        if not zustand.aus_heimnetz(request):
            return HttpResponseForbidden(
                "Die Einrichtung ist nur aus dem Heimnetz möglich.", content_type="text/plain"
            )
        if not im_assistenten:
            ziel = resolve_url("einrichtung:start")
            if request.headers.get("HX-Request"):
                return HttpResponse(status=204, headers={"HX-Redirect": ziel})
            return HttpResponse(status=302, headers={"Location": ziel})
        return self.get_response(request)
