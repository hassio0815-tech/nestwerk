"""Englische Oberfläche (Entscheidung 45): Deutsch ist Quellsprache, Englisch kommt aus .po."""

import pytest
from django.utils import translation

from apps.spielregeln import raenge
from apps.spielregeln.forms import PauseForm
from apps.spielregeln.models import Vergleich


def test_englische_eltern_seite_per_cookie(eltern_client):
    eltern_client.cookies["nestwerk_sprache"] = "en"
    html = eltern_client.get("/eltern/raenge/").content.decode()
    assert "Calibration" in html and "Levels" in html
    assert "Kalibrierung" not in html


def test_deutsch_bleibt_standard(eltern_client):
    html = eltern_client.get("/eltern/raenge/").content.decode()
    assert "Kalibrierung" in html and "Calibration" not in html


def test_fehlertext_und_auswahl_englisch(db):
    with translation.override("en"):
        assert str(Vergleich.MIN.label) == "at least (≥)"
        assert str(PauseForm.base_fields["grund"].label) == "Reason (optional)"
        with pytest.raises(raenge.RangFehler, match="Only parents"):
            raenge._eltern_pruefen(None)
    with translation.override("de"):
        assert str(Vergleich.MIN.label) == "mindestens (≥)"
