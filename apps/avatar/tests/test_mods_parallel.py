"""AP26: parallele Käufe über echte, getrennte SQLite-Verbindungen (BEGIN IMMEDIATE)."""

import threading
from datetime import UTC, datetime

import pytest
from django.db import connection

from apps.avatar import selectors, services
from apps.avatar.models import ModBesitz, ModDefinition
from apps.punkte import selectors as punkte
from apps.punkte import services as punkte_services
from apps.punkte.models import Art, Buchung
from apps.spielregeln import raenge_start
from apps.spielregeln.models import Kalibrierung, Rang

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


@pytest.fixture
def kind(anna, uhr):
    # Transaktionale Tests anderer Apps leeren die Seed-Daten (flush): Ränge sicherstellen
    raenge_start.anlegen(Rang, Kalibrierung)
    uhr.jetzt = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    services.avatar_waehlen(anna, "ritter", {})
    return anna


def _mod(slot):
    return ModDefinition.objects.get(
        thema__schluessel="ritter", slot__schluessel=slot, seltenheit=1
    )


def test_derselbe_mod_parallel_genau_einmal(kind):
    punkte_services.buchen(kind, Art.AUFGABE, 1000, schluessel="t:1", quelle_modul="t", von=None)
    m = _mod("kopf")
    ergebnisse = _parallel(lambda nr: services.mod_kaufen(kind, m))
    erfolge = [e for e in ergebnisse if isinstance(e, ModBesitz)]
    fehler = [e for e in ergebnisse if isinstance(e, services.ModFehler)]
    assert (len(erfolge), len(fehler)) == (1, THREADS - 1), ergebnisse
    assert Buchung.objects.filter(art=Art.MODKAUF).count() == 1
    assert punkte.guthaben(kind) == 1000 - erfolge[0].preis_bezahlt


def test_verschiedene_mods_parallel_kein_ueberziehen(kind):
    preis = selectors.mod_konditionen(_mod("kopf"), kind).preis
    punkte_services.buchen(
        kind, Art.AUFGABE, preis * 2 + preis // 2, schluessel="t:2", quelle_modul="t", von=None
    )
    slots = ["kopf", "koerper", "ruecken", "hand", "begleiter", "hintergrund"]
    mods = [_mod(s) for s in slots]
    ergebnisse = _parallel(lambda nr: services.mod_kaufen(kind, mods[nr]))
    erfolge = [e for e in ergebnisse if isinstance(e, ModBesitz)]
    assert len(erfolge) == 2, ergebnisse
    assert punkte.guthaben(kind) >= 0
    assert Buchung.objects.filter(art=Art.MODKAUF).count() == 2
