"""URL-Konfiguration nur für Tests: konten plus passive/aktive Beispiel-Views und
ein Kind-Bereich mit ``eigenes_kind``."""

from django.http import HttpResponse
from django.urls import include, path

from apps.konten.zugriff import eigenes_kind, nur_eltern, nur_kind, passiv


@passiv
def polling(request):
    return HttpResponse("poll")


def aktiv_seite(request):
    return HttpResponse("aktiv")


@eigenes_kind("kind_id")
def kind_daten(request, kind_id):
    return HttpResponse("daten")


@nur_eltern
def eltern_seite(request):
    return HttpResponse("eltern")


@nur_kind
def kind_seite(request):
    return HttpResponse("kind")


urlpatterns = [
    path("test/polling/", polling),
    path("test/aktiv/", aktiv_seite),
    path("test/kind/<uuid:kind_id>/", kind_daten),
    path("test/eltern/", eltern_seite),
    path("test/kind/", kind_seite),
    path("", include("apps.konten.urls")),
]
