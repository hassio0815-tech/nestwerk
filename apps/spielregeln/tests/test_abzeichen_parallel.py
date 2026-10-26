"""AP23: Parallele Prüfungen über echte, getrennte SQLite-Verbindungen verleihen jedes Abzeichen
und jeden Meilenstein genau einmal (unique Kind+Regel+Bereich) und melden genau einmal."""

import threading

import pytest
from django.db import connection

from apps.ereignisse.models import Ereignis
from apps.spielregeln import services
from apps.spielregeln.models import AbzeichenDefinition, AbzeichenVerleihung, MeilensteinErreicht

from . import testmodul_lernen as lernen

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


def test_parallele_pruefung_verleiht_einmal(anna):
    with lernen.aktiv():
        AbzeichenDefinition.objects.all().delete()  # nur die Test-Regeln
        for schwelle in (10, 20):
            AbzeichenDefinition.objects.create(
                schluessel=f"vokabeln-{schwelle}",
                name=f"Vokabeln {schwelle}",
                symbol=f"vokabeln-{schwelle}",
                metrik="lernen_test.vokabeln",
                schwelle=schwelle,
            )
        services.meilenstein_anlegen(
            "test-parallel",
            "Parallel",
            [{"metrik": "lernen_test.vokabeln", "wert": 20}],
            modul="test",
        )
        lernen.setzen("lernen_test.vokabeln", anna, 25)
        ergebnisse = _parallel(lambda nr: services.abzeichen_pruefen(anna))
    assert not [e for e in ergebnisse if isinstance(e, Exception)], ergebnisse
    assert AbzeichenVerleihung.objects.filter(kind=anna).count() == 2
    assert MeilensteinErreicht.objects.filter(kind=anna).count() == 1
    assert sum(len(e.verliehen) for e in ergebnisse) == 2
    assert Ereignis.objects.filter(typ_id="abzeichen.verliehen").count() == 1
    assert Ereignis.objects.filter(typ_id="meilenstein.erreicht").count() == 1
