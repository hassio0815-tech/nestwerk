"""Die Datenmigration 0021 füllt Karte und Thema für Bestandsdaten (Etappe 11)."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

VOR = [("lernen", "0019_startwerte_mathe_hilfe")]
NACH = [("lernen", "0021_karten_nachtragen")]


def _migrieren(ziel):
    executor = MigrationExecutor(connection)
    executor.migrate(ziel)
    return executor.loader.project_state(ziel).apps


@pytest.mark.django_db(transaction=True)
def test_migration_legt_karten_fuer_bestandsdaten_an(kind_a):
    try:
        alt = _migrieren(VOR)
        Fach, Thema, Frage = (alt.get_model("lernen", n) for n in ("Fach", "Thema", "Frage"))
        Sitzung, Versuch, Stand = (
            alt.get_model("lernen", n) for n in ("Lernsitzung", "Versuch", "Lernstand")
        )
        from django.utils import timezone

        fach = Fach.objects.create(schluessel="migtest", name="Migtest")
        thema = Thema.objects.create(fach=fach, klassenstufe=5, name="T")
        f1 = Frage.objects.create(thema=thema, typ="vokabel", frage="a", antwort="b")
        f2 = Frage.objects.create(
            thema=thema,
            typ="frage",
            frage="rechne",
            antwort="3",
            generiert=True,
            generator="addition",
            gen_daten={"typ": "plus"},
        )
        sitzung = Sitzung.objects.create(kind_id=kind_a.pk, fach=fach, beginn=timezone.now())
        for frage in (f1, f2):
            Versuch.objects.create(
                sitzung=sitzung, frage=frage, richtung="de_en", ergebnis="richtig"
            )
            Stand.objects.create(
                kind_id=kind_a.pk, frage=frage, richtung="de_en", faellig_am=timezone.now().date()
            )
        neu = _migrieren(NACH)
        Karte = neu.get_model("lernen", "Karte")
        V = neu.get_model("lernen", "Versuch")
        S = neu.get_model("lernen", "Lernstand")
        assert Karte.objects.count() == 2
        assert set(Karte.objects.values_list("schluessel", flat=True)) == {
            f"f:{f1.pk}:de_en",
            "m:addition:plus",
        }
        assert V.objects.filter(karte__isnull=False, thema_id=thema.pk).count() == 2
        assert S.objects.filter(karte__isnull=False).count() == 2
    finally:
        _migrieren(MigrationExecutor(connection).loader.graph.leaf_nodes())
