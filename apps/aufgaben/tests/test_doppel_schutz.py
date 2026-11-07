"""Doppel-Schutz beim Anlegen (gleicher Titel, gleiche Wiederholung, gleiche Zuweisung)."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.aufgaben import services
from apps.aufgaben.forms import AufgabeForm
from apps.aufgaben.models import Aufgabe

HX = {"HTTP_HX_REQUEST": "true"}
pytestmark = pytest.mark.django_db


def daten(**extra):
    d = {
        "titel": "Fenster putzen",
        "punkte": "25",
        "freigabeart": "eltern",
        "wiederholungsart": "einmalig",
    }
    d.update(extra)
    return d


def anzahl(titel="Fenster putzen"):
    return Aufgabe.objects.filter(titel=titel).count()


def test_doppelklick_legt_nur_eine_aufgabe_an(eltern_client):
    erste = eltern_client.post(reverse("aufgaben:neu"), daten(), **HX)
    zweite = eltern_client.post(reverse("aufgaben:neu"), daten(), **HX)
    assert erste.status_code == 204
    assert zweite.status_code == 200 and "gibt es schon" in zweite.content.decode()
    assert "trotzdem_anlegen" in zweite.content.decode()  # Häkchen zum Bestätigen
    assert anzahl() == 1


def test_trotzdem_anlegen_per_haekchen(eltern_client):
    eltern_client.post(reverse("aufgaben:neu"), daten(), **HX)
    antwort = eltern_client.post(reverse("aufgaben:neu"), daten(trotzdem_anlegen="on"), **HX)
    assert antwort.status_code == 204 and anzahl() == 2


def test_vergleich_normalisiert(eltern_client):
    eltern_client.post(reverse("aufgaben:neu"), daten(), **HX)
    antwort = eltern_client.post(reverse("aufgaben:neu"), daten(titel="  fenster PUTZEN "), **HX)
    assert antwort.status_code == 200 and Aufgabe.objects.count() == 1


def test_andere_wiederholung_oder_zuweisung_ist_kein_doppel(eltern_client, anna):
    eltern_client.post(reverse("aufgaben:neu"), daten(), **HX)
    taeglich = eltern_client.post(
        reverse("aufgaben:neu"), daten(wiederholungsart="intervall", intervall_tage="2"), **HX
    )
    fuer_anna = eltern_client.post(reverse("aufgaben:neu"), daten(zugewiesen_an=anna.pk), **HX)
    assert taeglich.status_code == 204 and fuer_anna.status_code == 204
    assert anzahl() == 3


def test_pausierte_oder_beendete_zaehlen_nicht(eltern_client, mama):
    a = Aufgabe.objects.create(
        titel="Fenster putzen", punkte=5, erstellt_von=mama, status="pausiert"
    )
    assert eltern_client.post(reverse("aufgaben:neu"), daten(), **HX).status_code == 204
    assert a.pk and anzahl() == 2


def test_bearbeiten_ist_kein_doppel(eltern_client, mama):
    a = Aufgabe.objects.create(titel="Fenster putzen", punkte=5, erstellt_von=mama)
    antwort = eltern_client.post(
        reverse("aufgaben:bearbeiten", args=[a.pk]), daten(punkte="30"), **HX
    )
    assert antwort.status_code == 204
    a.refresh_from_db()
    assert a.punkte == 30


def test_schnellknopf_doppel(eltern_client):
    knopf = daten(wiederholungsart="bei_bedarf", titel="Restmüll")
    assert eltern_client.post(reverse("aufgaben:neu"), knopf, **HX).status_code == 204
    assert eltern_client.post(reverse("aufgaben:neu"), knopf, **HX).status_code == 200
    assert anzahl("Restmüll") == 1


def test_je_kind_doppel_wird_erkannt(eltern_client, anna, ben):
    eltern_client.post(reverse("aufgaben:neu"), daten(je_kind="on"), **HX)
    zweite = eltern_client.post(reverse("aufgaben:neu"), daten(je_kind="on"), **HX)
    assert zweite.status_code == 200 and anzahl() == 2


def test_service_schuetzt_auch_ohne_formularpruefung(mama):
    """Zwei parallel gültige Formulare: das zweite scheitert im Service (Transaktion)."""
    form1 = AufgabeForm(daten())
    form2 = AufgabeForm(daten())
    assert form1.is_valid() and form2.is_valid()  # beide prüfen vor dem Speichern
    services.aufgabe_speichern(form1, von=mama)
    with pytest.raises(ValidationError):
        services.aufgabe_speichern(form2, von=mama)
    assert anzahl() == 1
