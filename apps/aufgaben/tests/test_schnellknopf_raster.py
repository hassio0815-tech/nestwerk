"""Gemeinsames Schnell-Knopf-Raster (Eltern/Kind/Tablet) und Löschen (Soft-Delete)."""

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from apps.aufgaben import schnellknopf, wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, Status
from apps.konten import services as konten
from apps.konten.models import GeraeteTyp
from apps.konten.tests.conftest import client_fuer

RASTER = "aufgaben/kacheln/_schnellknopf_raster.html"


@pytest.fixture
def knopf(mama):
    return Aufgabe.objects.create(
        titel="Restmüll",
        punkte=5,
        erstellt_von=mama,
        freigabeart="eltern",
        wiederholungsart=wiederholung.BEI_BEDARF,
        emoji="🗑️",
    )


def test_eltern_kachel_nutzt_partial(eltern_client, knopf):
    html = eltern_client.get(reverse("aufgaben:schnellknoepfe")).content.decode()
    assert 'class="sk-raster' in html and "Restmüll" in html
    assert "sk-kachel--neu" in html and "Wirklich löschen?" in html
    assert reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk]) in html


def test_kind_kachel_nutzt_partial(kind_client, knopf):
    html = kind_client.get(reverse("aufgaben:kind")).content.decode()
    assert 'class="sk-raster' in html and "Restmüll" in html
    assert "Ich mach&#x27;s" in html or "Ich mach's" in html
    assert "Wirklich löschen?" not in html and "sk-kachel--neu" not in html


def test_tablet_kachel_nutzt_partial(db, mama, knopf):
    geraet = konten.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)
    antwort = client_fuer(geraet).get(reverse("oberflaeche:tablet"))
    html = antwort.content.decode()
    assert 'class="sk-raster sk-raster--gross"' in html and "Restmüll" in html


def test_laeuft_schon_als_badge(mama, knopf):
    schnellknopf.druecken(knopf, von=mama)
    kontext = {"k": {"knoepfe": schnellknopf.knoepfe(mama), "kinder": []}}
    html = render_to_string(RASTER, {**kontext, "art": "eltern"})
    assert "sk__badge" in html and "läuft schon" in html and "noch offen" in html


def test_loeschen_eltern_blendet_aus_und_behaelt_historie(eltern_client, mama, knopf):
    schnellknopf.druecken(knopf, von=mama)
    url = reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk])
    antwort = eltern_client.post(url)
    assert antwort.status_code == 302 and antwort.url == reverse("aufgaben:schnellknoepfe")
    knopf.refresh_from_db()
    assert knopf.status == Status.BEENDET
    assert Aufgabe.objects.filter(pk=knopf.pk).exists()
    assert knopf.pk not in [a.pk for a in schnellknopf.knoepfe(mama)]
    html = eltern_client.get(reverse("aufgaben:schnellknoepfe")).content.decode()
    assert "Restmüll" not in html
    liste = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "Restmüll" not in liste


def test_loeschen_laesst_erledigte_instanz_und_punkte(eltern_client, mama, knopf):
    schnellknopf.druecken(knopf, von=mama)
    instanz = AufgabenInstanz.objects.get(aufgabe=knopf)
    AufgabenInstanz.objects.filter(pk=instanz.pk).update(status="bestaetigt")
    eltern_client.post(reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk]))
    instanz.refresh_from_db()
    assert instanz.status == "bestaetigt" and instanz.punkte_snapshot == 5


def test_loeschen_kind_403(kind_client, knopf):
    url = reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk])
    assert kind_client.post(url).status_code == 403
    knopf.refresh_from_db()
    assert knopf.status == Status.AKTIV


def test_loeschen_get_nicht_erlaubt(eltern_client, knopf):
    url = reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk])
    assert eltern_client.get(url).status_code == 405
    knopf.refresh_from_db()
    assert knopf.status == Status.AKTIV


def test_loeschen_braucht_csrf(mama, knopf):
    c = Client(enforce_csrf_checks=True)
    c.force_login(mama)
    url = reverse("aufgaben:schnellknopf_loeschen", args=[knopf.pk])
    assert c.post(url).status_code == 403
    knopf.refresh_from_db()
    assert knopf.status == Status.AKTIV
