import pytest

from apps.ereignisse import registry, services
from apps.kern.models import Einstellung

STARTWERTE = {
    "ereignisse.max_versuche": 3,
    "ereignisse.backoff_basis_sekunden": 30,
    "ereignisse.backoff_max_sekunden": 3600,
}

TYP = "test.passiert"
TYP_OHNE_HANDLER = "test.still"


@pytest.fixture
def worker_werte(db):
    """Worker-Einstellungen (transaktionale Tests leeren die Seed-Werte per flush)."""
    for schluessel, wert in STARTWERTE.items():
        Einstellung.objects.update_or_create(
            schluessel=schluessel, defaults={"wert": wert, "modul": "ereignisse"}
        )
    return STARTWERTE


@pytest.fixture
def katalog(worker_werte):
    """Isolierter Typ-/Handler-Katalog mit zwei Testtypen, in die DB synchronisiert."""
    with registry.isoliert():
        registry.typ_deklarieren(
            TYP,
            modul="test",
            bezeichnung="Etwas passiert",
            zielgruppe="eltern",
            standard_kanaele=["push", "email"],
        )
        registry.typ_deklarieren(
            TYP_OHNE_HANDLER, modul="test", bezeichnung="Still", zielgruppe="intern"
        )
        services.typen_synchronisieren()
        yield registry
