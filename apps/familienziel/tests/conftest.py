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


@pytest.fixture(autouse=True)
def startwerte(grundeinstellungen):
    """Startwerte per Datenmigration; transaktionale Tests anderer Module leeren die DB."""
    import importlib

    from django.apps import apps

    migration = importlib.import_module("apps.familienziel.migrations.0002_startwerte")
    migration.startwerte(apps, None)
    from apps.kern.einstellungen import startwerte_schreiben
    from apps.spielregeln.einstellungen import STARTWERTE

    startwerte_schreiben(apps.get_model("kern", "Einstellung"), STARTWERTE)


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


_nr = iter(range(1, 100_000))


@pytest.fixture
def xp():
    """Bestätigte Aufgabe: Aktivität und Punkte in einer Transaktion (wie ``aufgaben``)."""
    from django.db import transaction

    from apps.punkte import services as punkte
    from apps.punkte.models import Art
    from apps.spielregeln import services as spielregeln

    def _xp(kind, menge, tag=None, art=Art.AUFGABE, aktiv=True, **extra):
        tag = tag or zeit.heute()
        with transaction.atomic():
            if aktiv:
                spielregeln.aktivitaet_erfassen(kind, tag, modul="t", referenz=str(next(_nr)))
            return punkte.buchen(
                kind,
                art,
                menge,
                schluessel=f"t:{next(_nr)}",
                quelle_modul="test",
                bezugsdatum=tag,
                **({"von": None, "begruendung": "Test"} | extra),
            )

    return _xp
