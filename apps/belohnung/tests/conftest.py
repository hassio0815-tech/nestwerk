import pytest

from apps.belohnung.models import Belohnung, Belohnungskategorie
from apps.kern.models import Einstellung
from apps.konten import services as konten
from apps.konten.tests.conftest import PASSWORT, PIN, eltern_anmelden, kind_anmelden
from apps.punkte import services as punkte
from apps.punkte.models import Art

_zaehler = iter(range(10**9))


@pytest.fixture(autouse=True)
def grundeinstellungen(db):
    """Zeitzone und Limit (Seeds fehlen nach transaktionalen Tests, die die DB leeren)."""
    Einstellung.objects.update_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )
    Einstellung.objects.update_or_create(
        schluessel="belohnung.taschengeld_limit_cent", defaults={"wert": 1000, "modul": "belohnung"}
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
    eltern_anmelden(client, mama)
    return client


@pytest.fixture
def kind_client(client, anna):
    kind_anmelden(client, anna)
    return client


@pytest.fixture
def kategorien(db):
    return {
        name: Belohnungskategorie.objects.get_or_create(
            name=name, defaults={"symbol": symbol, "systemschluessel": schluessel}
        )[0]
        for name, symbol, schluessel in [
            ("Süßes", "geschenk", ""),
            ("Taschengeld", "muenze", "taschengeld"),
        ]
    }


@pytest.fixture
def suesses(kategorien):
    return Belohnung.objects.create(
        titel="Testsüßes", kategorie=kategorien["Süßes"], preis_punkte=30
    )


@pytest.fixture
def euro(kategorien):
    """1 € Taschengeld für 30 Punkte."""
    return Belohnung.objects.create(
        titel="Test-Euro", kategorie=kategorien["Taschengeld"], preis_punkte=30, geldwert_cent=100
    )


def gutschrift(kind, punkte_anzahl):
    return punkte.buchen(
        kind,
        Art.AUFGABE,
        punkte_anzahl,
        schluessel=f"test:{next(_zaehler)}",
        quelle_modul="aufgaben",
    )
