from datetime import UTC, datetime, timedelta

import pytest
from django.core import signing
from django.test import Client
from django.urls import reverse

from apps.kern import zeit
from apps.konten import services
from apps.konten.geraet import COOKIE_NAME, COOKIE_SALT
from apps.konten.models import GeraeteTyp

PASSWORT = "Zebra-Korkenzieher-77"
PIN = "4817"
FALSCHE_PIN = "1111"


class Uhr:
    """Steuerbare Uhr: ersetzt ``kern.zeit.jetzt`` (alle Zeitprüfungen laufen darüber)."""

    def __init__(self):
        self.jetzt = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)

    def weiter(self, **kwargs):
        self.jetzt += timedelta(**kwargs)


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
def papa(db, mama):
    return services.eltern_anlegen("Papa", rolle_label="papa")


@pytest.fixture
def anna(db):
    return services.kind_anlegen("Anna", PIN, akzentfarben=["#ff4fa0"])


@pytest.fixture
def ben(db):
    return services.kind_anlegen("Ben", PIN)


@pytest.fixture
def tablet(db, mama):
    return services.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)


@pytest.fixture
def iphone(db, mama):
    return services.geraet_registrieren(
        "Annas iPhone", GeraeteTyp.PERSOENLICH, registriert_von=mama
    )


def client_fuer(geraet=None, **extra):
    """Test-Client, optional mit Geräte-Cookie (so wie ihn der Server beim Registrieren setzt)."""
    c = Client(**extra)
    if geraet is not None:
        c.cookies[COOKIE_NAME] = signing.get_cookie_signer(salt=COOKIE_NAME + COOKIE_SALT).sign(
            str(geraet.pk)
        )
    return c


def kind_anmelden(client, kind, pin=PIN, **extra):
    return client.post(reverse("konten:kind_pin", args=[kind.pk]), {"pin": pin}, **extra)


def eltern_anmelden(client, elternteil, passwort=PASSWORT, vertraut=False, **extra):
    daten = {"eltern": str(elternteil.pk), "passwort": passwort}
    if vertraut:
        daten["vertraut"] = "on"
    return client.post(reverse("konten:eltern_login"), daten, **extra)


def angemeldet(client, benutzer):
    """Direkt anmelden (ohne Formular), Sitzungsrichtlinie wie beim echten Login."""
    if benutzer.rolle == "kind":
        antwort = kind_anmelden(client, benutzer)
    else:
        antwort = eltern_anmelden(client, benutzer)
    assert antwort.status_code == 302, antwort.content.decode()[:300]
    return client
