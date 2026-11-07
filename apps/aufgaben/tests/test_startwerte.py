"""Seeds müssen exakt Entscheidung 15 (Vorlagen) und 16 (Kategorien) entsprechen."""

import pytest

from apps.aufgaben.models import Kategorie, Vorlage

# Unabhängig von der Migration aus Entscheidung 15 abgetippt: (Titel, Punkte, Freigabeart)
ENTSCHEIDUNG_15 = [
    ("Müll rausbringen", 5, "vertrauen"),
    ("Mülltonnen rausstellen", 10, "vertrauen"),
    ("Leergut", 15, "vertrauen"),
    ("Spülmaschine ausräumen", 10, "vertrauen"),
    ("Spülmaschine einräumen", 10, "vertrauen"),
    ("Tisch decken/abräumen", 10, "vertrauen"),
    ("Einkaufsliste", 10, "eltern"),
    ("Wäsche waschen", 15, "eltern"),
    ("Wäsche aufhängen", 15, "eltern"),
    ("Wäsche zusammenlegen & einräumen", 20, "eltern"),
    ("Flur saugen", 15, "eltern"),
    ("Zimmer gründlich reinigen und aufräumen", 50, "nachweis"),
    ("Bad putzen", 40, "nachweis"),
    ("Rasen mähen", 45, "nachweis"),
    ("Auto aussaugen", 30, "nachweis"),
    ("Vokabeln lernen 15 Min", 15, "eltern"),
]
# Schnell-Knöpfe (bei Bedarf), später ergänzt; "Altglas" aus Entscheidung 15 wurde dazu umgewandelt
SCHNELLKNOEPFE = [("Restmüll", 5, "eltern"), ("Biomüll", 5, "eltern"), ("Altglas", 5, "eltern")]
# Migration 0016 (Bibliothek -> Schnell-Knöpfe): zwei neue Vorlagen
NEUE_VORLAGEN = [("Zimmer saugen", 15, "eltern"), ("Waschmaschine ausräumen", 10, "eltern")]
ENTSCHEIDUNG_16 = ["Haushalt", "Küche", "Wäsche", "Garten", "Schule", "Sonstiges"]

pytestmark = pytest.mark.django_db


def test_kategorien_exakt():
    kategorien = list(Kategorie.objects.order_by("reihenfolge"))
    assert [k.name for k in kategorien] == ENTSCHEIDUNG_16
    assert all(k.symbol and k.aktiv for k in kategorien)
    assert Kategorie.objects.get(name="Schule").systemschluessel == "schule"


def test_vorlagen_exakt():
    vorhanden = {(v.titel, v.punkte, v.freigabeart) for v in Vorlage.objects.all()}
    assert vorhanden == set(ENTSCHEIDUNG_15) | set(SCHNELLKNOEPFE) | set(NEUE_VORLAGEN)
    assert Vorlage.objects.count() == 21
    assert all(v.kategorie_id and v.aktiv for v in Vorlage.objects.all())


def test_kategorie_zuordnung_sinnvoll():
    assert Vorlage.objects.get(titel="Rasen mähen").kategorie.name == "Garten"
    assert Vorlage.objects.get(titel="Vokabeln lernen 15 Min").kategorie.name == "Schule"
    assert Vorlage.objects.get(titel="Wäsche waschen").kategorie.name == "Wäsche"


def test_schnellknopf_vorlagen_bei_bedarf():
    for titel, emoji in (("Restmüll", "🗑️"), ("Biomüll", "🍂"), ("Altglas", "🍾")):
        vorlage = Vorlage.objects.get(titel=titel)
        assert vorlage.plan.art == "bei_bedarf" and vorlage.emoji == emoji
        assert vorlage.schnellknopf_wer == "alle" and vorlage.kategorie.name == "Haushalt"
    assert Vorlage.objects.filter(titel="Altglas").count() == 1
