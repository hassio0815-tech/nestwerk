"""Parallele Klicks über getrennte SQLite-Verbindungen (BEGIN IMMEDIATE): genau eine Buchung."""

import threading

import pytest
from django.db import connection

from apps.aufgaben import services, wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus, Interesse
from apps.punkte.models import Buchung

pytestmark = pytest.mark.django_db(transaction=True)
THREADS = 6


def _parallel(funktion, anzahl=THREADS):
    start = threading.Barrier(anzahl)
    ergebnisse = [None] * anzahl

    def lauf(nr):
        try:
            start.wait()
            ergebnisse[nr] = funktion(nr)
        except Exception as exc:  # noqa: BLE001 - Ergebnis wird im Test ausgewertet
            ergebnisse[nr] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=lauf, args=(nr,)) for nr in range(anzahl)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return ergebnisse


@pytest.fixture(autouse=True)
def startwerte(db):
    """Transaktionale Tests leeren die DB (flush) inkl. der Seed-Einstellungen."""
    from apps.aufgaben.einstellungen import STARTWERTE, STARTWERTE_ABLAUF
    from apps.kern.einstellungen import startwerte_schreiben
    from apps.kern.models import Einstellung

    startwerte_schreiben(Einstellung, STARTWERTE | STARTWERTE_ABLAUF)


@pytest.fixture
def instanz(mama):
    aufgabe = Aufgabe.objects.create(
        titel="Bad", punkte=40, erstellt_von=mama, wiederholungsart=wiederholung.EINMALIG
    )
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe, titel_snapshot="Bad", punkte_snapshot=40, freigabeart_snapshot="eltern"
    )


def test_parallele_bestaetigung_bucht_genau_einmal(instanz, anna, mama):
    services.interesse_zeigen(instanz, anna)
    services.erledigt_melden(instanz, anna)
    ergebnisse = _parallel(
        lambda nr: services.bestaetigen(instanz, von=mama, sonderpunkte=5, begruendung="gut")
    )
    erfolge = [e for e in ergebnisse if isinstance(e, AufgabenInstanz)]
    abgewiesen = [e for e in ergebnisse if isinstance(e, services.UngueltigerUebergang)]
    assert (len(erfolge), len(abgewiesen)) == (1, THREADS - 1), ergebnisse
    assert Buchung.objects.count() == 2  # Basis + Sonderpunkte, je einmal
    assert sum(Buchung.objects.values_list("guthaben_delta", flat=True)) == 45


def test_parallele_wahl_mehrerer_kinder(instanz, anna, ben):
    kinder = [anna, ben]
    ergebnisse = _parallel(lambda nr: services.interesse_zeigen(instanz, kinder[nr]), anzahl=2)
    assert all(isinstance(e, AufgabenInstanz) for e in ergebnisse), ergebnisse
    instanz.refresh_from_db()
    assert instanz.status == InstanzStatus.KONFLIKT
    assert Interesse.objects.filter(status="aktiv").count() == 2
