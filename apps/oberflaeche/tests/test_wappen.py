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


def test_rolle_setzen_ueberschreiben_und_fallback(client, eltern_client, mama):
    url = reverse("oberflaeche:wappen")
    # Fallback ohne Rolle: Name
    services.wappen_setzen(mama, "hausdrache")
    assert mama.name_mit_wappen == f"{mama.anzeigename} (🐉 Hausdrache)"
    heim = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert f"Hallo {mama.anzeigename}!" in heim
    # Rolle wählen (HTMX)
    eltern_client.post(url, {"wappen": "hausdrache", "wappen_rolle": "mum", "wappen_rolle_eigen": ""}, HTTP_HX_REQUEST="true")
    mama.refresh_from_db()
    assert mama.rolle_anzeige == "Mum"
    assert mama.name_mit_wappen == "Mum (🐉 Hausdrache)"
    heim = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert "🐉 Mum" in heim and "Hausdrache" in heim
    start = client.__class__().get(reverse("konten:start")).content.decode()
    assert "Mum" in start
    # Eigene Rolle überschreibt
    eltern_client.post(url, {"wappen": "hausdrache", "wappen_rolle": "mum", "wappen_rolle_eigen": " Mami "}, HTTP_HX_REQUEST="true")
    mama.refresh_from_db()
    assert mama.wappen_rolle_eigen == "Mami" and mama.name_mit_wappen == "Mami (🐉 Hausdrache)"
    # Zu lang / ungültig wird abgelehnt
    antwort = eltern_client.post(url, {"wappen_rolle_eigen": "x" * 16}, HTTP_HX_REQUEST="true")
    assert 'role="alert"' in antwort.content.decode()
    mama.refresh_from_db()
    assert mama.wappen_rolle_eigen == "Mami"


def test_bestehende_eltern_haben_leere_rolle(db):
    b = services.eltern_anlegen("Opa")
    assert b.wappen_rolle == "" and b.wappen_rolle_eigen == "" and b.wappen_name == "Opa"


def test_wizard_speichert_rolle(db):
    from apps.einrichtung import services as ei

    daten = {}
    for i, n in ((1, "Eva"), (2, "Tom")):
        daten.update({f"eltern{i}_name": n, f"eltern{i}_rolle": "andere", f"eltern{i}_email": f"{n}@x.de",
                      f"eltern{i}_wappen": "", f"eltern{i}_wappen_rolle": "dad" if i == 2 else "",
                      f"eltern{i}_wappen_rolle_eigen": "Mami" if i == 1 else ""})
    ei.eltern_speichern(daten)
    e, t = Benutzer.objects.get(anzeigename="Eva"), Benutzer.objects.get(anzeigename="Tom")
    assert e.rolle_anzeige == "Mami" and t.rolle_anzeige == "Dad"
