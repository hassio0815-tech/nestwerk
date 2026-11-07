"""Übernehmen aus der Wochenvorschau: bestehende Instanz suchen, per ``interesse_zeigen`` wählen."""

from datetime import time, timedelta

import pytest

from apps.aufgaben import selectors, services, uebernahme
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.kern import zeit
from apps.konten import services as konten


@pytest.fixture
def ben(db):
    return konten.kind_anlegen("Ben", "4321", akzentfarben=["#3377ff"])


def taeglich(mama, titel="Zähne putzen", **kw):
    kw.setdefault("punkte", 5)
    kw.setdefault("start_datum", zeit.heute() - timedelta(days=3))
    kw.setdefault("fenster_von", time(0, 0))  # zeitgebunden: Instanzen bis zum Horizont
    kw.setdefault("fenster_bis", time(23, 59))
    aufgabe = Aufgabe.objects.create(
        titel=titel, erstellt_von=mama, wiederholungsart="intervall", intervall_tage=1, **kw
    )
    services.instanzen_erzeugen(aufgaben=Aufgabe.objects.filter(pk=aufgabe.pk))
    return aufgabe


def morgen():
    return zeit.heute() + timedelta(days=1)


def test_uebernehmen_reserviert_die_instanz_fuer_das_kind(mama, anna):
    aufgabe = taeglich(mama)
    ergebnis = uebernahme.uebernehmen(anna, aufgabe.pk, morgen())
    assert ergebnis.art == "erfolg" and "Zähne putzen" in ergebnis.text
    instanz = AufgabenInstanz.objects.get(aufgabe=aufgabe, plan_datum=morgen())
    assert instanz.kind == anna and instanz.status == InstanzStatus.RESERVIERT


def test_ohne_instanz_freundliche_meldung_ohne_neue_instanz(mama, anna):
    aufgabe = taeglich(mama)
    weit = zeit.heute() + timedelta(days=400)
    vorher = AufgabenInstanz.objects.count()
    ergebnis = uebernahme.uebernehmen(anna, aufgabe.pk, weit)
    assert ergebnis.art == "fehler" and "noch nicht" in ergebnis.text
    assert AufgabenInstanz.objects.count() == vorher


def test_unbekannte_aufgabe_ist_freundliche_meldung(mama, anna):
    ergebnis = uebernahme.uebernehmen(anna, 987654, morgen())
    assert ergebnis.art == "fehler"


def test_aufgabe_eines_anderen_kindes_wird_abgelehnt(mama, anna, ben):
    aufgabe = taeglich(mama, zugewiesen_an=ben)
    ergebnis = uebernahme.uebernehmen(anna, aufgabe.pk, morgen())
    assert ergebnis.art == "fehler" and "anderes Kind" in ergebnis.text
    assert AufgabenInstanz.objects.get(aufgabe=aufgabe, plan_datum=morgen()).kind is None


def test_eigene_zugewiesene_aufgabe_klappt(mama, anna, ben):
    aufgabe = taeglich(mama, zugewiesen_an=anna)
    assert uebernahme.uebernehmen(anna, aufgabe.pk, morgen()).art == "erfolg"


def test_schon_uebernommen_sagt_hast_du_schon(mama, anna):
    aufgabe = taeglich(mama)
    uebernahme.uebernehmen(anna, aufgabe.pk, morgen())
    ergebnis = uebernahme.uebernehmen(anna, aufgabe.pk, morgen())
    assert ergebnis.art == "info" and "schon" in ergebnis.text


def test_eltern_koennen_nicht_uebernehmen(mama):
    aufgabe = taeglich(mama)
    ergebnis = uebernahme.uebernehmen(mama, aufgabe.pk, morgen())  # Eltern sind keine Kinder
    assert ergebnis.art == "fehler"
    assert AufgabenInstanz.objects.get(aufgabe=aufgabe, plan_datum=morgen()).kind is None


def test_wochen_aufgabe_findet_nur_aufgaben_der_woche(mama):
    aufgabe = taeglich(mama)
    assert selectors.start_woche_aufgabe(aufgabe.pk, morgen()) == aufgabe
    assert selectors.start_woche_aufgabe(aufgabe.pk, zeit.heute() + timedelta(days=9)) is None
    assert selectors.start_woche_aufgabe(aufgabe.pk, zeit.heute() - timedelta(days=1)) is None
    einmal = Aufgabe.objects.create(
        titel="Einmal", punkte=1, erstellt_von=mama, wiederholungsart="einmalig"
    )
    assert selectors.start_woche_aufgabe(einmal.pk, morgen()) is None


def test_ungebundene_aufgabe_hat_morgen_noch_keine_instanz(mama, anna):
    aufgabe = taeglich(mama, fenster_von=None, fenster_bis=None)
    ergebnis = uebernahme.uebernehmen(anna, aufgabe.pk, morgen())
    assert ergebnis.art == "fehler" and "noch nicht" in ergebnis.text
