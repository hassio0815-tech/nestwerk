"""Texte der Sondertage in beiden Sprachen."""

import pytest
from django.utils import translation

from apps.sondertag import selectors, services

pytestmark = pytest.mark.django_db


def test_noch_text_deutsch_und_englisch():
    assert selectors.noch_text(2, 1) == "Noch 2 Mods und 1 Woche bis zum Sondertag"
    with translation.override("en"):
        assert selectors.noch_text(2, 1) == "2 mods and 1 week to go until your special day"
        assert selectors.noch_text(1, 0) == "1 mod to go until your special day"
        assert "Almost there" in selectors.noch_text(0, 0)


def test_fehlermeldung_auf_englisch(anna):
    with translation.override("en"):
        with pytest.raises(services.SondertagFehler) as fehler:
            services.wunsch_senden(anna, None, wunsch="", begleitung="egal")
    assert "Write down what you wish for." in str(fehler.value)


def test_status_label_uebersetzt():
    from apps.sondertag.models import Status

    assert str(Status.WUNSCH_OFFEN.label) == "Wunsch offen"
    with translation.override("en"):
        assert str(Status.WUNSCH_OFFEN.label) == "Wish open"
