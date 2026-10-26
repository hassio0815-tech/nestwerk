from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.kern import einstellungen, zeit
from apps.konten import services
from apps.konten.tests.conftest import PASSWORT, PIN, eltern_anmelden, kind_anmelden

BERLIN = ZoneInfo("Europe/Berlin")
GO_LIVE = date(2026, 10, 19)  # Montag, ISO-Woche 2026-W43


def lok(*args):
    """Lokale Berliner Zeit -> aware datetime."""
    return datetime(*args, tzinfo=BERLIN)


class Uhr:
    def __init__(self):
        self.jetzt = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)

    def stellen(self, moment):
        self.jetzt = moment
        return moment

    def weiter(self, **kwargs):
        self.jetzt += timedelta(**kwargs)
        return self.jetzt


@pytest.fixture(autouse=True)
def grundeinstellungen(db):
    from apps.kern.models import Einstellung

    Einstellung.objects.get_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )
    einstellungen.setzen("allgemein.go_live_datum", GO_LIVE, akteur=None)


@pytest.fixture
def uhr(monkeypatch):
    u = Uhr()
    monkeypatch.setattr(zeit, "jetzt", lambda: u.jetzt)
    return u


@pytest.fixture
def mama(db):
    benutzer = services.eltern_anlegen("Mama", rolle_label="mama")
    services.eltern_passwort_setzen(PASSWORT, von=benutzer)
    return benutzer


@pytest.fixture
def anna(db):
    return services.kind_anlegen("Anna", PIN)


@pytest.fixture
def ben(db):
    return services.kind_anlegen("Ben", PIN)


@pytest.fixture
def eltern_client(client, mama):
    eltern_anmelden(client, mama)
    return client


@pytest.fixture
def kind_client(client, anna):
    kind_anmelden(client, anna)
    return client
