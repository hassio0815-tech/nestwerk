from datetime import date

import pytest

from apps.kern.models import Einstellung
from apps.konten import services as konten
from apps.punkte import services
from apps.punkte.models import Art

TAG = date(2026, 10, 23)
PIN = "4817"


@pytest.fixture(autouse=True)
def zeitzone(db):
    """``kern.zeit.heute`` braucht die Zeitzone (Seed folgt mit AP09)."""
    Einstellung.objects.update_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )


@pytest.fixture
def anna(db):
    return konten.kind_anlegen("Anna", PIN)


@pytest.fixture
def ben(db):
    return konten.kind_anlegen("Ben", PIN)


@pytest.fixture
def mama(db):
    return konten.eltern_anlegen("Mama", rolle_label="mama")


_zaehler = iter(range(10**9))


def gutschrift(kind, punkte, *, art=Art.AUFGABE, **kwargs):
    kwargs.setdefault("schluessel", f"test:{next(_zaehler)}")
    kwargs.setdefault("quelle_modul", "aufgaben")
    kwargs.setdefault("bezugsdatum", TAG)
    if art in services.BEGRUENDUNG_PFLICHT:
        kwargs.setdefault("begruendung", "Test")
    return services.buchen(kind, art, punkte, **kwargs)
