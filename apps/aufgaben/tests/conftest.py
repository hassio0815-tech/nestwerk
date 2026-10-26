import pytest

from apps.konten import services
from apps.konten.tests.conftest import PASSWORT, PIN, eltern_anmelden, kind_anmelden


@pytest.fixture
def mama(db):
    benutzer = services.eltern_anlegen("Mama", rolle_label="mama")
    services.eltern_passwort_setzen(PASSWORT, von=benutzer)
    return benutzer


@pytest.fixture
def anna(db):
    return services.kind_anlegen("Anna", PIN, akzentfarben=["#ff4fa0"])


@pytest.fixture
def eltern_client(client, mama):
    eltern_anmelden(client, mama)
    return client


@pytest.fixture
def kind_client(client, anna):
    kind_anmelden(client, anna)
    return client


@pytest.fixture(autouse=True)
def zeitzone(db):
    from apps.kern.models import Einstellung

    Einstellung.objects.get_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )


@pytest.fixture
def papa(db, mama):
    return services.eltern_anlegen("Papa", rolle_label="papa")


@pytest.fixture
def ben(db):
    return services.kind_anlegen("Ben", PIN)
