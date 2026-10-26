"""Kinder- und Elternverwaltung nach der Einrichtung."""

import pytest
from django.urls import reverse

from apps.kern.models import AuditEintrag
from apps.konten import selectors
from apps.konten.models import Benutzer, ElternProfil
from apps.konten.tests.conftest import PASSWORT, client_fuer, eltern_anmelden, kind_anmelden

from .conftest import PIN


def url(name, *args):
    return reverse(f"oberflaeche:{name}", args=args)


def test_seite_zeigt_kinder_eltern_und_geraete_link(eltern_client, anna):
    html = eltern_client.get(url("familie")).content.decode()
    assert "Anna" in html and "Mama" in html
    assert reverse("konten:geraete") in html


def test_kind_anlegen_mit_pin(eltern_client, mama):
    antwort = eltern_client.post(url("familie_kind_neu"), {"anzeigename": "Clara", "pin": "1234"})
    assert antwort.status_code == 302
    assert AuditEintrag.objects.filter(aktion="konten.kind_angelegt").exists()
    clara = Benutzer.objects.get(anzeigename="Clara")
    assert kind_anmelden(client_fuer(), clara, pin="1234").status_code == 302


@pytest.mark.parametrize("pin", ["12", "abcd", "12345", ""])
def test_kind_anlegen_mit_schlechter_pin_scheitert(eltern_client, pin):
    antwort = eltern_client.post(url("familie_kind_neu"), {"anzeigename": "Clara", "pin": pin})
    assert antwort.status_code == 422 and "4 Ziffern" in antwort.content.decode()


def test_kind_umbenennen(eltern_client, anna):
    eltern_client.post(url("familie_kind_umbenennen", anna.pk), {"anzeigename": "Annabelle"})
    anna.refresh_from_db()
    assert anna.anzeigename == "Annabelle"
    assert AuditEintrag.objects.filter(aktion="konten.kind_umbenannt", kind=anna).exists()


def test_pin_zuruecksetzen_hebt_sperre_auf(eltern_client, anna):
    for _ in range(10):
        kind_anmelden(client_fuer(), anna, pin="0000")
    assert selectors.gesperrte_kinder() == [anna]
    antwort = eltern_client.post(url("familie_kind_pin", anna.pk), {"pin": "9999"})
    assert antwort.status_code == 302
    assert kind_anmelden(client_fuer(), anna, pin="9999").status_code == 302
    assert selectors.gesperrte_kinder() == []
    assert AuditEintrag.objects.filter(aktion="konten.pin_zurueckgesetzt", kind=anna).exists()


def test_sperre_aufheben(eltern_client, anna):
    for _ in range(10):
        kind_anmelden(client_fuer(), anna, pin="0000")
    assert selectors.gesperrte_kinder() == [anna]
    eltern_client.post(url("familie_kind_entsperren", anna.pk))
    assert selectors.gesperrte_kinder() == []
    assert kind_anmelden(client_fuer(), anna, pin=PIN).status_code == 302


def test_kind_deaktivieren(eltern_client, anna):
    eltern_client.post(url("familie_kind_deaktivieren", anna.pk))
    anna.refresh_from_db()
    assert anna.aktiv is False
    assert "Anna" not in eltern_client.get(url("familie")).content.decode()
    assert eltern_client.post(url("familie_kind_pin", anna.pk), {"pin": "1234"}).status_code == 404


def test_eltern_angaben_aendern(eltern_client, mama):
    antwort = eltern_client.post(
        url("familie_eltern", mama.pk),
        {"anzeigename": "Mami", "rolle_label": "mama", "email": "mami@example.org"},
    )
    assert antwort.status_code == 302
    mama.refresh_from_db()
    assert mama.anzeigename == "Mami"
    assert ElternProfil.objects.get(pk=mama.pk).email == "mami@example.org"


def test_eltern_ungueltige_mail(eltern_client, mama):
    antwort = eltern_client.post(
        url("familie_eltern", mama.pk),
        {"anzeigename": "Mama", "rolle_label": "mama", "email": "keine-mail"},
    )
    assert antwort.status_code == 422


def test_passwort_aendern(eltern_client, mama):
    antwort = eltern_client.post(
        url("familie_passwort"), {"passwort": "Neues-Passwort-42", "passwort2": "Neues-Passwort-42"}
    )
    assert antwort.status_code == 302
    assert eltern_anmelden(client_fuer(), mama, passwort="Neues-Passwort-42").status_code == 302
    assert eltern_anmelden(client_fuer(), mama, passwort=PASSWORT).status_code == 401
    eintraege = AuditEintrag.objects.filter(aktion="konten.passwort_geaendert")
    assert eintraege.count() == 2  # Fixture + Änderung
    assert all("Neues-Passwort" not in str(e.details) for e in eintraege)


@pytest.mark.parametrize(
    "daten,text",
    [
        ({"passwort": "Neues-Passwort-42", "passwort2": "anders"}, "verschieden"),
        ({"passwort": "kurz", "passwort2": "kurz"}, "mindestens"),
    ],
)
def test_passwort_fehler(eltern_client, daten, text):
    antwort = eltern_client.post(url("familie_passwort"), daten)
    assert antwort.status_code == 422 and text in antwort.content.decode()


def test_nur_post_fuer_aenderungen(eltern_client, anna):
    assert eltern_client.get(url("familie_kind_pin", anna.pk)).status_code == 405
