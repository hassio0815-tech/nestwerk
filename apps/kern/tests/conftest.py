import pytest

from apps.kern import einstellungen, registry
from apps.kern.models import Einstellung


@pytest.fixture
def kern_werte(db):
    """Werte der kern-Einstellungen direkt in der DB (wie nach dem Seed)."""
    werte = {
        "allgemein.anzeigename": "Nestwerk",
        "allgemein.zeitzone": "Europe/Berlin",
        "allgemein.go_live_datum": "2026-11-01",
        "allgemein.sprache": "de",
        "allgemein.einrichtung_abgeschlossen": False,
    }
    for schluessel, wert in werte.items():
        Einstellung.objects.create(schluessel=schluessel, wert=wert, modul="allgemein")
    return werte


@pytest.fixture
def einstellungs_verzeichnis():
    """Test-Definitionen werden nach dem Test wieder entfernt."""
    with einstellungen.verzeichnis.isoliert():
        yield einstellungen


@pytest.fixture
def leere_registry():
    with registry.isoliert():
        yield registry
