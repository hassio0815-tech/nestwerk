"""Anbindung: Metriken und Kacheln über kern.registry, Jobs/Commands, Eltern-UI, Kind-Kachel.
(aufgaben-Hooks: tests/szenarien/test_spielregeln_aufgaben.py, Schichtenregel.)"""

from datetime import date

import pytest
from django.core.management import CommandError, call_command
from django.db import transaction

from apps.kern import registry
from apps.kern.models import JobLauf
from apps.spielregeln import services
from apps.spielregeln.models import Aktivitaet, Pause, Wochenauswertung
from apps.spielregeln.registry import metrik_wert

from .conftest import lok

# --- Registry --------------------------------------------------------------------------------


def test_metriken_registriert_und_abfragbar(anna, uhr):
    for schluessel in ("wochenserie", "aktive_wochen", "tagesserie", "rekord_tagesserie"):
        assert registry.metrik(schluessel).modul == "spielregeln"
    Aktivitaet.objects.create(kind=anna, datum=date(2026, 10, 20), modul="t", referenz="1")
    Aktivitaet.objects.create(kind=anna, datum=date(2026, 10, 21), modul="t", referenz="2")
    uhr.stellen(lok(2026, 10, 28, 9))
    assert metrik_wert("wochenserie", anna) == 1
    assert metrik_wert("aktive_wochen", anna) == 1
    assert metrik_wert("rekord_tagesserie", anna) == 2
    assert metrik_wert("tagesserie", anna) == 0


# --- Commands --------------------------------------------------------------------------------


def test_job_command_idempotent(anna, uhr, capsys):
    Aktivitaet.objects.create(kind=anna, datum=date(2026, 10, 20), modul="t", referenz="1")
    uhr.stellen(lok(2026, 11, 4, 12))
    call_command("wochen_sicherstellen")
    call_command("wochen_sicherstellen")
    laeufe = JobLauf.objects.filter(name="wochen_sicherstellen").order_by("id")
    assert [lauf.info["angelegt"] for lauf in laeufe] == [2, 0]
    assert Wochenauswertung.objects.count() == 2


def test_neuberechnen_command(anna, uhr, capsys):
    Aktivitaet.objects.create(kind=anna, datum=date(2026, 10, 20), modul="t", referenz="1")
    uhr.stellen(lok(2026, 11, 4, 12))
    call_command("wochen_sicherstellen")
    call_command("spielregeln_neuberechnen")
    assert "keine Abweichung" in capsys.readouterr().out
    Wochenauswertung.objects.update(aktive_wochen_gesamt=5)
    with pytest.raises(CommandError, match="2 Abweichung"):
        call_command("spielregeln_neuberechnen")
    call_command("spielregeln_neuberechnen", "--schreiben", "--nachtragen")
    call_command("spielregeln_neuberechnen")


# --- Oberfläche ------------------------------------------------------------------------------


def test_kind_kachel_zeigt_serie_und_pause(kind_client, anna, mama, uhr):
    Aktivitaet.objects.create(kind=anna, datum=date(2026, 10, 20), modul="t", referenz="1")
    uhr.stellen(lok(2026, 10, 28, 9))
    html = kind_client.get("/kind/").content.decode()
    assert 'data-kachel="spielregeln.kind_serie"' in html
    assert "1 Woche Serie" in html and "1 aktive Woche" in html
    assert "Pause – deine Serie ist sicher" not in html
    with transaction.atomic():
        services.pause_setzen(None, von=mama)
    html = kind_client.get("/kind/").content.decode()
    assert "Pause – deine Serie ist sicher" in html


def test_kind_darf_pausen_nicht(kind_client, anna):
    assert kind_client.get("/eltern/pausen/").status_code == 403
    antwort = kind_client.post("/eltern/pausen/schalter/", {"ziel": str(anna.pk), "aktion": "an"})
    assert antwort.status_code == 403 and not Pause.objects.exists()


def test_eltern_schalter_an_aus(eltern_client, anna, mama, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    html = eltern_client.get("/eltern/").content.decode()
    assert 'data-kachel="spielregeln.eltern_pausen"' in html and "Pause an" in html
    antwort = eltern_client.post(
        "/eltern/pausen/schalter/", {"ziel": str(anna.pk), "aktion": "an", "zurueck": "heim"}
    )
    assert antwort.status_code == 302 and antwort.url == "/eltern/"
    pause = Pause.objects.get()
    assert (pause.kind, pause.von, pause.bis, pause.erstellt_von) == (
        anna,
        date(2026, 10, 21),
        None,
        mama,
    )
    # doppelt "an": verständlicher Fehler statt zweiter Pause
    antwort = eltern_client.post("/eltern/pausen/schalter/", {"ziel": str(anna.pk), "aktion": "an"})
    assert antwort.status_code == 400 and "laufende Pause" in antwort.content.decode()
    uhr.stellen(lok(2026, 10, 24, 9))
    eltern_client.post("/eltern/pausen/schalter/", {"ziel": str(anna.pk), "aktion": "aus"})
    pause.refresh_from_db()
    assert pause.bis == date(2026, 10, 23)
    assert eltern_client.post("/eltern/pausen/schalter/", {"ziel": "x"}).status_code == 404


def test_eltern_pause_mit_zeitraum_familie(eltern_client, anna, ben, uhr):
    uhr.stellen(lok(2026, 10, 21, 9))
    seite = eltern_client.get("/eltern/pausen/")
    assert seite.status_code == 200 and "Ganze Familie" in seite.content.decode()
    antwort = eltern_client.post(
        "/eltern/pausen/neu/",
        {"ziel": "familie", "von": "2026-11-02", "bis": "2026-11-06", "grund": "Urlaub"},
    )
    assert antwort.status_code == 302
    pause = Pause.objects.get()
    assert pause.familie and pause.grund == "Urlaub"
    html = eltern_client.get("/eltern/pausen/").content.decode()
    assert "Urlaub" in html and "Löschen" in html
    fehler = eltern_client.post(
        "/eltern/pausen/neu/", {"ziel": "familie", "von": "2026-11-06", "bis": "2026-11-02"}
    )
    assert fehler.status_code == 400 and "vor dem Beginn" in fehler.content.decode()
    eltern_client.post(f"/eltern/pausen/{pause.pk}/loeschen/", {"zurueck": "pausen"})
    assert not Pause.objects.exists()
