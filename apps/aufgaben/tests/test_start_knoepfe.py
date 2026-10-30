"""Start-Schnell-Knöpfe: einmalig als Aufgaben anlegen (schnellknoepfe_sicherstellen)."""

import pytest
from django.core.management import call_command

from apps.aufgaben import schnellknopf, wiederholung
from apps.aufgaben.models import Aufgabe, SchnellknopfWer, Vorlage
from apps.kern import einstellungen
from apps.konten import services as konten

TITEL = {"Restmüll", "Biomüll", "Altglas"}


def test_legt_drei_knoepfe_einmal_an(mama):
    assert schnellknopf.schnellknoepfe_sicherstellen() == 3
    aufgaben = Aufgabe.objects.all()
    assert {a.titel for a in aufgaben} == TITEL
    for a in aufgaben:
        assert a.wiederholungsart == wiederholung.BEI_BEDARF
        assert a.punkte == 5
        assert a.freigabeart == "eltern"
        assert a.schnellknopf_wer == SchnellknopfWer.ALLE
        assert a.erstellt_von == mama
        vorlage = Vorlage.objects.get(titel=a.titel)
        assert a.vorlage == vorlage
        assert a.kategorie == vorlage.kategorie
        assert a.emoji == vorlage.emoji
    assert einstellungen.wert("aufgaben.schnellknoepfe_angelegt") is True


def test_zweiter_aufruf_tut_nichts(mama):
    schnellknopf.schnellknoepfe_sicherstellen()
    assert schnellknopf.schnellknoepfe_sicherstellen() == 0
    assert Aufgabe.objects.count() == 3


def test_ohne_eltern_nichts_und_kein_merker(db):
    assert schnellknopf.schnellknoepfe_sicherstellen() == 0
    assert not Aufgabe.objects.exists()
    assert einstellungen.wert("aufgaben.schnellknoepfe_angelegt") is False


def test_ersteller_ist_erster_aktiver_elternteil(mama):
    papa = konten.eltern_anlegen("Papa", rolle_label="papa", reihenfolge=-1)
    schnellknopf.schnellknoepfe_sicherstellen()
    assert {a.erstellt_von for a in Aufgabe.objects.all()} == {papa}


def test_vorhandener_titel_wird_uebersprungen(mama):
    vorhanden = Aufgabe.objects.create(titel="Biomüll", punkte=9, erstellt_von=mama)
    assert schnellknopf.schnellknoepfe_sicherstellen() == 2
    assert Aufgabe.objects.count() == 3
    vorhanden.refresh_from_db()
    assert vorhanden.punkte == 9


def test_geloeschter_knopf_kommt_nicht_wieder(mama):
    schnellknopf.schnellknoepfe_sicherstellen()
    Aufgabe.objects.filter(titel="Altglas").delete()
    assert schnellknopf.schnellknoepfe_sicherstellen() == 0
    assert not Aufgabe.objects.filter(titel="Altglas").exists()


def test_job_befehl(mama):
    call_command("schnellknoepfe_sicherstellen")
    assert Aufgabe.objects.count() == 3
    call_command("schnellknoepfe_sicherstellen")
    assert Aufgabe.objects.count() == 3


@pytest.mark.parametrize("titel", sorted(TITEL))
def test_titel_passen_zu_vorlagen(db, titel):
    assert Vorlage.objects.filter(titel=titel).exists()
