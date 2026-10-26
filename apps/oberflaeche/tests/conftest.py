from itertools import count

import pytest

from apps.kern import einstellungen, zeit
from apps.kern.einstellungen import Typ
from apps.kern.models import Einstellung
from apps.konten import services as konten
from apps.konten.models import GeraeteTyp
from apps.konten.tests.conftest import PASSWORT, PIN, Uhr, angemeldet
from apps.punkte import services as punkte
from apps.punkte.models import Art

_nummer = count(1)


def beispielwert(d):
    """Gültiger Wert für eine Definition (nur für Tests)."""
    if d.auswahl:
        return list(d.auswahl)[:1] if d.typ is Typ.LISTE else d.auswahl[0]
    match d.typ:
        case Typ.GANZZAHL:
            return d.minimum if d.minimum is not None else 1
        case Typ.BOOL:
            return False
        case Typ.TEXT:
            return ""
        case Typ.DATUM:
            return "2026-01-01"
        case Typ.UHRZEIT:
            return "12:00"
        case Typ.ZEITZONE:
            return "Europe/Berlin"
        case Typ.LISTE:
            return []
    raise AssertionError(d)


def gutschrift(kind, betrag, von):
    return punkte.buchen(
        kind,
        Art.AUFGABE,
        betrag,
        schluessel=f"test:{next(_nummer)}",
        quelle_modul="test",
        begruendung="Test",
        von=von,
    )


@pytest.fixture(autouse=True)
def alle_einstellungen(db):
    """Transaktionale Tests anderer Apps leeren die Seeds: fehlende Werte ergänzen."""
    vorhanden = set(Einstellung.objects.values_list("schluessel", flat=True))
    for d in einstellungen.definitionen():
        if d.schluessel in vorhanden:
            continue
        Einstellung.objects.create(
            schluessel=d.schluessel, modul=d.modul, wert=d.pruefen(beispielwert(d))
        )


@pytest.fixture
def mama(db):
    benutzer = konten.eltern_anlegen("Mama", rolle_label="mama")
    konten.eltern_passwort_setzen(PASSWORT, von=benutzer)
    return benutzer


@pytest.fixture
def anna(db):
    return konten.kind_anlegen("Anna", PIN, akzentfarben=["#ff4fa0"])


@pytest.fixture
def ben(db):
    return konten.kind_anlegen("Ben", PIN)


@pytest.fixture
def eltern_client(client, mama):
    return angemeldet(client, mama)


@pytest.fixture
def kind_client(client, anna):
    return angemeldet(client, anna)


@pytest.fixture
def uhr(monkeypatch):
    u = Uhr()
    monkeypatch.setattr(zeit, "jetzt", lambda: u.jetzt)
    return u


@pytest.fixture
def tablet(db, mama):
    return konten.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)
