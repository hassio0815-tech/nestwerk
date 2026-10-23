"""Parallele Anträge/Entscheidungen über echte, getrennte SQLite-Verbindungen (BEGIN IMMEDIATE)."""

import threading

import pytest
from django.db import connection

from apps.belohnung import services
from apps.belohnung.models import Einloeseantrag, Status
from apps.punkte import selectors as punkte
from apps.punkte.models import Art, Buchung

from .conftest import gutschrift

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


def test_parallele_antraege_ueberbeantragen_nicht(anna, suesses):
    gutschrift(anna, 100)  # reicht für 3 x 30
    ergebnisse = _parallel(lambda nr: services.antrag_stellen(anna, suesses))
    erfolge = [e for e in ergebnisse if isinstance(e, Einloeseantrag)]
    abgelehnt = [e for e in ergebnisse if isinstance(e, services.GuthabenReichtNicht)]
    assert (len(erfolge), len(abgelehnt)) == (3, THREADS - 3), ergebnisse
    assert punkte.reserviert(anna) == 90
    assert punkte.verfuegbar(anna) == 10


def test_parallele_taschengeld_antraege_halten_das_limit(anna, euro):
    gutschrift(anna, 1000)
    from apps.belohnung.models import TaschengeldLimit

    TaschengeldLimit.objects.create(kind=anna, monatslimit_cent=300)  # 3 x 1 €
    ergebnisse = _parallel(lambda nr: services.antrag_stellen(anna, euro))
    erfolge = [e for e in ergebnisse if isinstance(e, Einloeseantrag)]
    abgelehnt = [e for e in ergebnisse if isinstance(e, services.LimitUeberschritten)]
    assert (len(erfolge), len(abgelehnt)) == (3, THREADS - 3), ergebnisse


def test_paralleles_bestaetigen_bucht_einmal(anna, mama, suesses):
    gutschrift(anna, 100)
    antrag = services.antrag_stellen(anna, suesses)
    ergebnisse = _parallel(lambda nr: services.bestaetigen(antrag.pk, von=mama))
    assert all(isinstance(e, Einloeseantrag) for e in ergebnisse), ergebnisse
    assert Buchung.objects.filter(art=Art.EINLOESUNG).count() == 1
    assert punkte.guthaben(anna) == 70


def test_bestaetigen_gegen_zurueckziehen_genau_ein_ergebnis(anna, mama, suesses):
    gutschrift(anna, 100)
    antrag = services.antrag_stellen(anna, suesses)

    def aktion(nr):
        if nr % 2:
            return services.bestaetigen(antrag.pk, von=mama)
        return services.zurueckziehen(antrag.pk, kind=anna)

    _parallel(aktion)
    antrag.refresh_from_db()
    buchungen = Buchung.objects.filter(art=Art.EINLOESUNG).count()
    assert antrag.status in (Status.BESTAETIGT, Status.ZURUECKGEZOGEN)
    assert buchungen == (1 if antrag.status == Status.BESTAETIGT else 0)
    assert punkte.guthaben(anna) == 100 - 30 * buchungen
