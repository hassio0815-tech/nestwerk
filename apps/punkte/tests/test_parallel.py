"""Parallele Buchungen über echte, getrennte SQLite-Verbindungen (BEGIN IMMEDIATE)."""

import threading

import pytest
from django.db import connection

from apps.punkte import selectors, services
from apps.punkte.models import Art, Buchung

from .conftest import gutschrift

pytestmark = pytest.mark.django_db(transaction=True)

THREADS = 6


def _parallel(funktion, anzahl=THREADS):
    """Startet ``funktion(nr)`` gleichzeitig in ``anzahl`` Threads (je eigene DB-Verbindung)."""
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


def test_paralleles_ausgeben_macht_guthaben_nicht_negativ(anna):
    gutschrift(anna, 100)
    ergebnisse = _parallel(
        lambda nr: gutschrift(anna, 30, art=Art.MODKAUF, schluessel=f"modkauf:{nr}")
    )
    erfolge = [e for e in ergebnisse if isinstance(e, Buchung)]
    abgelehnt = [e for e in ergebnisse if isinstance(e, services.GuthabenUnzureichend)]
    assert (len(erfolge), len(abgelehnt)) == (3, THREADS - 3), ergebnisse
    assert selectors.salden(anna) == selectors.Saldo(guthaben=10, xp=100)


def test_paralleler_gleicher_schluessel_bucht_einmal(anna):
    ergebnisse = _parallel(lambda nr: gutschrift(anna, 25, schluessel="aufgabe:1:basis"))
    assert all(isinstance(e, Buchung) for e in ergebnisse), ergebnisse
    assert len({e.pk for e in ergebnisse}) == 1
    assert Buchung.objects.count() == 1
    assert selectors.guthaben(anna) == 25


def test_parallele_gegenbuchung_nur_einmal(anna, mama):
    original = gutschrift(anna, 40)
    ergebnisse = _parallel(lambda nr: services.gegenbuchen(original.pk, von=mama))
    assert all(isinstance(e, Buchung) for e in ergebnisse), ergebnisse
    assert len({e.pk for e in ergebnisse}) == 1
    assert selectors.salden(anna) == selectors.Saldo(guthaben=0, xp=0)
