"""Englische Texte der kern-Einstellungen (Entscheidung 45)."""

import pytest
from django.utils import translation

from apps.kern import einstellungen
from apps.kern.models import JobStatus


def test_einstellung_bezeichnung_uebersetzt():
    d = einstellungen.definition("allgemein.zeitzone")
    with translation.override("en"):
        assert str(d.bezeichnung) == "Time zone"
    with translation.override("de"):
        assert str(d.bezeichnung) == "Zeitzone"


def test_validierungsfehler_englisch(db):
    with translation.override("en"):
        with pytest.raises(einstellungen.UngueltigerWert, match="smaller than the minimum 7"):
            einstellungen.setzen("allgemein.joblauf_aufbewahrung_tage", 1, akteur=None)
    with translation.override("de"):
        with pytest.raises(einstellungen.UngueltigerWert, match="kleiner als Minimum 7"):
            einstellungen.setzen("allgemein.joblauf_aufbewahrung_tage", 1, akteur=None)


def test_job_status_label_englisch():
    with translation.override("en"):
        assert str(JobStatus.UEBERSPRUNGEN.label) == "skipped"
