"""Seeds müssen exakt Entscheidung 15 (Vorlagen) und 16 (Kategorien) entsprechen."""

import pytest

from apps.aufgaben.models import Kategorie, Vorlage

# Unabhängig von der Migration aus Entscheidung 15 abgetippt: (Titel, Punkte, Freigabeart)
ENTSCHEIDUNG_15 = [
    ("Müll rausbringen", 5, "vertrauen"),
    ("Mülltonnen rausstellen", 10, "vertrauen"),
    ("Leergut", 15, "vertrauen"),
    ("Altglas", 15, "vertrauen"),
    ("Spülmaschine ausräumen", 10, "vertrauen"),
    ("Spülmaschine einräumen", 10, "vertrauen"),
    ("Tisch decken/abräumen", 10, "vertrauen"),
    ("Einkaufsliste", 10, "eltern"),
    ("Wäsche waschen", 15, "eltern"),
    ("Wäsche aufhängen", 15, "eltern"),
    ("Wäsche zusammenlegen & einräumen", 20, "eltern"),
    ("Flur saugen", 15, "eltern"),
    ("Zimmer gründlich", 30, "nachweis"),
    ("Bad putzen", 40, "nachweis"),
    ("Rasen mähen", 45, "nachweis"),
    ("Auto aussaugen", 30, "nachweis"),
    ("Vokabeln lernen 15 Min", 15, "eltern"),
]
ENTSCHEIDUNG_16 = ["Haushalt", "Küche", "Wäsche", "Garten", "Schule", "Sonstiges"]

pytestmark = pytest.mark.django_db


def test_kategorien_exakt():
    kategorien = list(Kategorie.objects.order_by("reihenfolge"))
    assert [k.name for k in kategorien] == ENTSCHEIDUNG_16
    assert all(k.symbol and k.aktiv for k in kategorien)
    assert Kategorie.objects.get(name="Schule").systemschluessel == "schule"


def test_vorlagen_exakt():
    vorhanden = {(v.titel, v.punkte, v.freigabeart) for v in Vorlage.objects.all()}
    assert vorhanden == set(ENTSCHEIDUNG_15)
    assert Vorlage.objects.count() == 17
    assert all(v.kategorie_id and v.aktiv for v in Vorlage.objects.all())


def test_kategorie_zuordnung_sinnvoll():
    assert Vorlage.objects.get(titel="Rasen mähen").kategorie.name == "Garten"
    assert Vorlage.objects.get(titel="Vokabeln lernen 15 Min").kategorie.name == "Schule"
    assert Vorlage.objects.get(titel="Wäsche waschen").kategorie.name == "Wäsche"
