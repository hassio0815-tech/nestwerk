"""Wappen der Eltern: Vergabe, Wahl in den Einstellungen, Anzeige."""

import pytest
from django.urls import reverse

from apps.konten import services, wappen
from apps.konten.models import Benutzer


def test_zufallswappen_unterschiedlich_bei_zwei_eltern(db):
    for _ in range(15):
        Benutzer.objects.all().delete()
        a = services.eltern_anlegen("A", rolle_label="mama")
        b = services.eltern_anlegen("B", rolle_label="papa")
        assert a.wappen in wappen.NACH_SCHLUESSEL
        assert b.wappen in wappen.NACH_SCHLUESSEL
        assert a.wappen != b.wappen


def test_wappen_aendern_ueber_einstellungen(eltern_client, mama):
    url = reverse("oberflaeche:wappen")
    antwort = eltern_client.post(url, {"wappen": "grillmeister"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200
    assert "Gespeichert" in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.wappen == "grillmeister"
    antwort = eltern_client.post(url, {"wappen": "gibtsnicht"}, HTTP_HX_REQUEST="true")
    assert "Unbekanntes Wappen" in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.wappen == "grillmeister"


def test_einstellungen_zeigen_galerie(eltern_client):
    html = eltern_client.get(reverse("oberflaeche:einstellungen")).content.decode()
    assert "Mein Wappen" in html and "Bewacht den Kühlschrank" in html


def test_login_kachel_und_dashboard_zeigen_wappen(client, eltern_client, mama):
    services.wappen_setzen(mama, "hausdrache")
    start = client.__class__().get(reverse("konten:start")).content.decode()
    assert "🐉" in start and "Hausdrache" in start
    heim = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert "🐉 Hausdrache" in heim


def test_kinder_text_mit_wappen(mama):
    services.wappen_setzen(mama, "nachteule")
    assert mama.name_mit_wappen == f"{mama.anzeigename} (🦉 Nachteule)"


def test_migration_vergibt_wappen_an_bestehende(db):
    import importlib

    from django.apps import apps as django_apps

    m = importlib.import_module("apps.konten.migrations.0005_wappen_vergeben")
    a = services.eltern_anlegen("A")
    b = services.eltern_anlegen("B")
    Benutzer.objects.update(wappen="")
    m.vergeben(django_apps, None)
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.wappen and b.wappen and a.wappen != b.wappen
