import pytest
from django.test import Client

from apps.konten.tests.conftest import (  # noqa: F401  (Fixtures weiterreichen)
    PIN,
    angemeldet,
    anna,
    ben,
    client_fuer,
    iphone,
    mama,
    papa,
    tablet,
    uhr,
)


def _beispielwert(d):
    from apps.kern.einstellungen import Typ

    if d.auswahl:
        return list(d.auswahl)[:1] if d.typ is Typ.LISTE else d.auswahl[0]
    return {
        Typ.GANZZAHL: d.minimum if d.minimum is not None else 1,
        Typ.BOOL: False,
        Typ.TEXT: "",
        Typ.DATUM: "2026-01-01",
        Typ.UHRZEIT: "12:00",
        Typ.ZEITZONE: "Europe/Berlin",
        Typ.LISTE: [],
    }[d.typ]


@pytest.fixture(autouse=True)
def alle_einstellungen(db):
    """Dashboards lesen Einstellungen; transaktionale Tests anderer Apps leeren die Seeds."""
    from apps.kern import einstellungen
    from apps.kern.models import Einstellung

    vorhanden = set(Einstellung.objects.values_list("schluessel", flat=True))
    for d in einstellungen.definitionen():
        if d.schluessel not in vorhanden:
            Einstellung.objects.create(
                schluessel=d.schluessel, modul=d.modul, wert=d.pruefen(_beispielwert(d))
            )


@pytest.fixture
def kind_client(anna):  # noqa: F811
    return angemeldet(Client(), anna)


@pytest.fixture
def eltern_client(mama):  # noqa: F811
    return angemeldet(Client(), mama)
