"""Rollenschutz: Kind kommt nie in den Eltern-Bereich, Eltern-Bereich ist getrennt."""

import pytest
from django.urls import reverse

from apps.konten.models import Geraet

from .conftest import eltern_anmelden, kind_anmelden

pytestmark = pytest.mark.django_db

ELTERN_URLS = ["konten:eltern_heim", "konten:geraete"]


@pytest.fixture(autouse=True)
def test_urls(settings):
    settings.ROOT_URLCONF = "apps.konten.tests.urls_test"


@pytest.mark.parametrize("name", ELTERN_URLS)
def test_kind_kann_keine_eltern_url_oeffnen(anna, client, name):
    kind_anmelden(client, anna)
    assert client.get(reverse(name)).status_code == 403


def test_kind_kann_keine_eltern_aktion_ausloesen(anna, ben, tablet, client):
    kind_anmelden(client, anna)
    assert client.post(reverse("konten:kind_entsperren", args=[ben.pk])).status_code == 403
    assert client.post(reverse("konten:geraet_widerrufen", args=[tablet.pk])).status_code == 403
    assert (
        client.post(reverse("konten:geraete"), {"bezeichnung": "X", "typ": "kiosk"}).status_code
        == 403
    )
    tablet.refresh_from_db()
    assert tablet.aktiv and Geraet.objects.count() == 1


def test_kind_kann_eltern_decorator_view_nicht_oeffnen(anna, client):
    kind_anmelden(client, anna)
    assert client.get("/test/eltern/").status_code == 403


def test_eltern_koennen_kind_bereich_nicht_oeffnen(mama, client):
    eltern_anmelden(client, mama)
    assert client.get("/test/kind/").status_code == 403
    assert client.get(reverse("konten:kind_heim")).status_code == 403


@pytest.mark.parametrize("url", ["/eltern/", "/eltern/geraete/", "/test/eltern/"])
def test_ohne_anmeldung_weiter_zur_eltern_anmeldung(client, url):
    antwort = client.get(url)
    assert antwort.status_code == 302
    assert antwort.url.startswith(reverse("konten:eltern_login"))
    assert "next=" in antwort.url


def test_kind_bereich_ohne_anmeldung_fuehrt_zur_startseite(client):
    assert client.get("/test/kind/").url.startswith(reverse("konten:start"))


def test_htmx_ohne_anmeldung_bekommt_401(client):
    antwort = client.get("/test/eltern/", headers={"HX-Request": "true"})
    assert antwort.status_code == 401 and "HX-Redirect" in antwort


def test_eigenes_kind_kind_sieht_nur_sich(anna, ben, client):
    kind_anmelden(client, anna)
    assert client.get(f"/test/kind/{anna.pk}/").status_code == 200
    assert client.get(f"/test/kind/{ben.pk}/").status_code == 403


def test_eigenes_kind_eltern_sehen_jedes_kind(mama, anna, client):
    eltern_anmelden(client, mama)
    assert client.get(f"/test/kind/{anna.pk}/").status_code == 200


def test_eigenes_kind_ohne_anmeldung(anna, client):
    assert client.get(f"/test/kind/{anna.pk}/").status_code == 302


def test_deaktiviertes_konto_verliert_sofort_den_zugang(mama, anna, client):
    from apps.konten import services

    kind_anmelden(client, anna)
    services.benutzer_deaktivieren(anna, von=mama)
    assert client.get("/test/kind/").status_code == 302  # Sitzung ungültig


def test_aktueller_elternteil_und_kind(mama, anna, rf):
    from apps.konten.zugriff import aktueller_elternteil, aktuelles_kind

    anfrage = rf.get("/")
    anfrage.user = mama
    assert aktueller_elternteil(anfrage) == mama and aktuelles_kind(anfrage) is None
    anfrage.user = anna
    assert aktuelles_kind(anfrage) == anna and aktueller_elternteil(anfrage) is None


def test_mixins_schuetzen_klassen_views(anna, mama, rf):
    from django.core.exceptions import PermissionDenied
    from django.http import HttpResponse
    from django.views import View

    from apps.konten.zugriff import NurElternMixin, NurKindMixin

    class ElternAnsicht(NurElternMixin, View):
        def get(self, request):
            return HttpResponse("ok")

    class KindAnsicht(NurKindMixin, View):
        def get(self, request):
            return HttpResponse("ok")

    anfrage = rf.get("/")
    anfrage.user = anna
    with pytest.raises(PermissionDenied):
        ElternAnsicht.as_view()(anfrage)
    assert KindAnsicht.as_view()(anfrage).status_code == 200
    anfrage.user = mama
    assert ElternAnsicht.as_view()(anfrage).status_code == 200
    with pytest.raises(PermissionDenied):
        KindAnsicht.as_view()(anfrage)
