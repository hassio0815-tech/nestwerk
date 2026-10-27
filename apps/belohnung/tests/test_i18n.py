"""Zweisprachigkeit: englische Oberfläche und Meldungen."""

import pytest
from django.urls import reverse
from django.utils import translation

from apps.belohnung import services
from apps.belohnung.models import euro_text

from .conftest import gutschrift

pytestmark = pytest.mark.django_db


def test_kind_katalog_englisch(kind_client, anna, suesses):
    anna.sprache = "en"
    anna.save()
    gutschrift(anna, 10)
    html = kind_client.get(reverse("belohnung:kind")).content.decode()
    assert "My requests" in html and "20 more points needed" in html
    assert "Meine Anträge" not in html


def test_fehlermeldung_und_betrag_englisch(anna, suesses):
    gutschrift(anna, 10)
    with translation.override("en"):
        with pytest.raises(services.GuthabenReichtNicht, match="20 more points"):
            services.antrag_stellen(anna, suesses)
        assert euro_text(250) == "€2.50"
    assert euro_text(250) == "2,50 €"
