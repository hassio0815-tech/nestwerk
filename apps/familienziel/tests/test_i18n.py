"""Zweisprachigkeit: englische Eltern-Seite und Fehlermeldungen."""

import pytest
from django.utils import translation

from apps.familienziel import services
from apps.familienziel.models import AbstimmungStatus

pytestmark = pytest.mark.django_db


def test_eltern_seite_englisch(eltern_client, mama, uhr):
    mama.sprache = "en"
    mama.save()
    html = eltern_client.get("/eltern/familienziel/").content.decode()
    assert "Reward list" in html and "Current week" in html
    assert "Belohnungsliste" not in html


def test_fehlermeldung_englisch(anna, mama):
    with translation.override("en"):
        with pytest.raises(services.FamilienzielFehler, match="only kids vote|Only kids vote"):
            services.stimme_abgeben(mama, 1)
    assert AbstimmungStatus.GLEICHSTAND.label == "Eltern entscheiden"
    with translation.override("en"):
        assert str(AbstimmungStatus.GLEICHSTAND.label) == "Parents decide"
