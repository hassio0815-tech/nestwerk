"""Instanz-Erzeugung, Verfall, Vorwarnung und Reservierungs-Hooks (AP11)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.aufgaben import events, services, wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus, Status
from apps.aufgaben.wiederholung import maske_aus_tagen
from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen, zeit
from apps.kern.models import JobLauf

BERLIN = ZoneInfo("Europe/Berlin")


def lok(*args):
    return datetime(*args, tzinfo=BERLIN)


@pytest.fixture
def neue_aufgabe(mama):
    def anlegen(**felder):
        werte = {
            "titel": "Mülltonnen",
            "punkte": 10,
            "erstellt_von": mama,
            "start_datum": date(2026, 10, 1),
            "wiederholungsart": wiederholung.INTERVALL,
            "intervall_tage": 1,
        }
        werte.update(felder)
        return Aufgabe.objects.create(**werte)

    return anlegen


def zeitgebunden(neue_aufgabe, **felder):
    return neue_aufgabe(fenster_von=time(18, 0), fenster_bis=time(20, 0), **felder)


def daten(aufgabe):
    return sorted(aufgabe.instanzen.values_list("plan_datum", flat=True))


def ereignisse(typ):
    return Ereignis.objects.filter(typ_id=typ)


def test_startwerte_vorhanden(db):
    assert einstellungen.wert("aufgaben.instanz_horizont_tage") == 14
    assert einstellungen.wert("aufgaben.vorwarnung_stunden_vorher") == 3
    assert einstellungen.wert("aufgaben.reservierung_stunden") == 48
    assert einstellungen.wert("aufgaben.erinnerung_kind_stunden_vorher") == 6


# --- Erzeugung --------------------------------------------------------------------------------


def test_zeitgebunden_bis_horizont_mit_snapshot(neue_aufgabe):
    aufgabe = zeitgebunden(neue_aufgabe)
    ergebnis = services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 12))
    assert ergebnis["neu"] == 15  # heute + 14 Tage
    assert daten(aufgabe)[0] == date(2026, 10, 10)
    assert daten(aufgabe)[-1] == date(2026, 10, 24)
    instanz = aufgabe.instanzen.first()
    assert instanz.status == InstanzStatus.OFFEN
    assert (instanz.titel_snapshot, instanz.punkte_snapshot) == ("Mülltonnen", 10)
    assert instanz.freigabeart_snapshot == aufgabe.freigabeart


def test_doppelter_lauf_ohne_duplikate(neue_aufgabe):
    zeitgebunden(neue_aufgabe)
    neue_aufgabe(titel="ohne Fenster")
    jetzt = lok(2026, 10, 10, 12)
    erster = services.instanzen_erzeugen(jetzt=jetzt)
    anzahl = AufgabenInstanz.objects.count()
    zweiter = services.instanzen_erzeugen(jetzt=jetzt)
    assert erster["neu"] == anzahl == 16
    assert zweiter["neu"] == 0
    assert AufgabenInstanz.objects.count() == anzahl


def test_schon_beendetes_fenster_wird_nicht_angelegt(neue_aufgabe):
    aufgabe = zeitgebunden(neue_aufgabe)
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 21))  # heute 20:00 vorbei
    assert daten(aufgabe)[0] == date(2026, 10, 11)


def test_catch_up_nach_mehrtaegigem_ausfall(neue_aufgabe):
    einstellungen.setzen("aufgaben.instanz_horizont_tage", 1, akteur=None)
    timed = zeitgebunden(neue_aufgabe)
    frei = neue_aufgabe(titel="täglich ohne Fenster")
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 12))
    assert daten(timed) == [date(2026, 10, 10), date(2026, 10, 11)]
    assert daten(frei) == [date(2026, 10, 10)]

    # 3 Tage Ausfall; ungebundene Instanz wurde zwischendurch erledigt
    frei.instanzen.update(status=InstanzStatus.BESTAETIGT, abgeschlossen_am=lok(2026, 10, 10, 15))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 14, 12))
    # 12./13. sind vorbei (nichts nachträglich), 14./15. neu
    assert daten(timed) == [date(2026, 10, d) for d in (10, 11, 14, 15)]
    # kein Stapel: genau eine neue, für den jüngsten fälligen Termin
    assert daten(frei) == [date(2026, 10, 10), date(2026, 10, 14)]

    ergebnis = services.verfall_pruefen(jetzt=lok(2026, 10, 14, 12))
    assert ergebnis["verfallen"] == 2  # 10. und 11.


def test_dst_woche_vollstaendig_und_korrekt(neue_aufgabe):
    """ISO-Woche 2026-W43 (19.–25.10.) enthält das Ende der Sommerzeit am Sonntag."""
    aufgabe = zeitgebunden(
        neue_aufgabe,
        wiederholungsart=wiederholung.WOECHENTLICH,
        intervall_tage=None,
        wochentage=maske_aus_tagen(range(7)),
        start_datum=date(2026, 10, 19),
        end_datum=date(2026, 10, 26),
    )
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 8))
    instanzen = list(aufgabe.instanzen.order_by("plan_datum"))
    assert [i.plan_datum for i in instanzen] == [date(2026, 10, d) for d in range(19, 27)]
    for instanz in instanzen:
        assert zeit.lokal(instanz.fenster_start).time() == time(18, 0)
        assert zeit.lokal(instanz.fenster_ende).time() == time(20, 0)
        assert zeit.heute(instanz.fenster_ende) == instanz.plan_datum
    assert instanzen[5].fenster_ende.hour == 18  # Sa: UTC+2
    assert instanzen[6].fenster_ende.hour == 19  # So: UTC+1


def test_ungebunden_hoechstens_eine_laufende(neue_aufgabe):
    aufgabe = neue_aufgabe()
    for tag in (10, 11, 12):
        services.instanzen_erzeugen(jetzt=lok(2026, 10, tag, 9))
    assert aufgabe.instanzen.count() == 1
    instanz = aufgabe.instanzen.get()
    assert instanz.plan_datum == date(2026, 10, 10)
    assert instanz.fenster_ende is None

    # DB-Ebene: zweite laufende ungebundene Instanz unmöglich
    with pytest.raises(IntegrityError), transaction.atomic():
        AufgabenInstanz.objects.create(
            aufgabe=aufgabe,
            plan_datum=date(2026, 10, 11),
            titel_snapshot="x",
            punkte_snapshot=1,
            freigabeart_snapshot="eltern",
            status=InstanzStatus.RESERVIERT,
        )

    # Erledigt am 12. -> nächste erst zum nächsten Termin danach (13.)
    aufgabe.instanzen.update(
        status=InstanzStatus.BESTAETIGT, abgeschlossen_am=lok(2026, 10, 12, 10)
    )
    assert services.instanzen_erzeugen(jetzt=lok(2026, 10, 12, 11))["neu"] == 0
    assert services.instanzen_erzeugen(jetzt=lok(2026, 10, 13, 0, 5))["neu"] == 1
    assert daten(aufgabe) == [date(2026, 10, 10), date(2026, 10, 13)]


def test_ungebunden_woechentlich_erst_ab_faelligkeit(neue_aufgabe):
    aufgabe = neue_aufgabe(
        wiederholungsart=wiederholung.WOECHENTLICH,
        intervall_tage=None,
        wochentage=maske_aus_tagen([0]),
        start_datum=date(2026, 10, 1),
    )
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 14, 12))  # Mi
    assert daten(aufgabe) == [date(2026, 10, 12)]  # jüngster Montag
    aufgabe.instanzen.update(
        status=InstanzStatus.BESTAETIGT, abgeschlossen_am=lok(2026, 10, 14, 13)
    )
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 18, 12))  # So
    assert daten(aufgabe) == [date(2026, 10, 12)]
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 0, 5))
    assert daten(aufgabe) == [date(2026, 10, 12), date(2026, 10, 19)]


def test_einmalig_genau_einmal(neue_aufgabe):
    timed = zeitgebunden(
        neue_aufgabe,
        wiederholungsart=wiederholung.EINMALIG,
        intervall_tage=None,
        start_datum=date(2026, 10, 12),
    )
    frei = neue_aufgabe(
        titel="einmal frei",
        wiederholungsart=wiederholung.EINMALIG,
        intervall_tage=None,
        start_datum=None,
    )
    for tag in (10, 11, 12):
        services.instanzen_erzeugen(jetzt=lok(2026, 10, tag, 9))
    assert daten(timed) == [date(2026, 10, 12)]
    assert frei.instanzen.count() == 1
    frei.instanzen.update(status=InstanzStatus.BESTAETIGT)
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 13, 9))
    assert frei.instanzen.count() == 1


def test_start_und_ende_respektiert(neue_aufgabe):
    aufgabe = zeitgebunden(
        neue_aufgabe, start_datum=date(2026, 10, 20), end_datum=date(2026, 10, 22)
    )
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 12))
    assert daten(aufgabe) == [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]


def test_pausiert_und_beendet_erzeugen_nichts(neue_aufgabe):
    pausiert = zeitgebunden(neue_aufgabe, status=Status.PAUSIERT)
    beendet = neue_aufgabe(status=Status.BEENDET)
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 12))
    assert not pausiert.instanzen.exists()
    assert not beendet.instanzen.exists()


def test_status_wechsel_raeumt_offene_auf_und_plant_neu(neue_aufgabe, mama):
    heute = zeit.heute()
    aufgabe = zeitgebunden(neue_aufgabe, start_datum=heute + timedelta(days=1))
    services.instanzen_erzeugen()
    assert aufgabe.instanzen.exists()
    reserviert = aufgabe.instanzen.order_by("plan_datum").last()
    reserviert.status = InstanzStatus.RESERVIERT
    reserviert.save()

    services.aufgabe_status_setzen(aufgabe, Status.PAUSIERT, von=mama)
    assert list(aufgabe.instanzen.all()) == [reserviert]  # Begonnenes bleibt
    services.instanzen_erzeugen()
    assert aufgabe.instanzen.count() == 1

    services.aufgabe_status_setzen(aufgabe, Status.AKTIV, von=mama)
    assert aufgabe.instanzen.count() == 14


# --- Verfall + Vorwarnung ---------------------------------------------------------------------


@pytest.fixture
def heute_abend(neue_aufgabe):
    """Eine zeitgebundene Instanz am 10.10. (18:00–20:00)."""
    aufgabe = zeitgebunden(
        neue_aufgabe,
        wiederholungsart=wiederholung.EINMALIG,
        intervall_tage=None,
        start_datum=date(2026, 10, 10),
    )
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 8))
    return aufgabe.instanzen.get()


def test_vorwarnung_genau_einmal(heute_abend):
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 16, 55))["vorgewarnt"] == 0
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 17, 0))["vorgewarnt"] == 1
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 17, 5))["vorgewarnt"] == 0
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 19, 59))["vorgewarnt"] == 0
    heute_abend.refresh_from_db()
    assert heute_abend.vorwarnung_am == lok(2026, 10, 10, 17, 0)
    ereignis = ereignisse(events.VERFALL_VORWARNUNG).get()
    assert ereignis.daten["instanz_id"] == heute_abend.pk
    assert ereignis.daten["aufgabe"] == "Mülltonnen"


def test_vorwarnung_abschaltbar(heute_abend):
    einstellungen.setzen("aufgaben.vorwarnung_stunden_vorher", 0, akteur=None)
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 19))["vorgewarnt"] == 0


def test_verfall_genau_einmal(heute_abend):
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 20, 0))["verfallen"] == 1
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 10, 20, 5))["verfallen"] == 0
    heute_abend.refresh_from_db()
    assert heute_abend.status == InstanzStatus.NICHT_UEBERNOMMEN
    assert heute_abend.abgeschlossen_am == lok(2026, 10, 10, 20)
    assert ereignisse(events.NICHT_UEBERNOMMEN).count() == 1
    # verspätete Läufe ohne vorherige Vorwarnung warnen nicht mehr nachträglich
    assert not ereignisse(events.VERFALL_VORWARNUNG).exists()


def test_verfall_nur_fuer_offene(heute_abend):
    AufgabenInstanz.objects.filter(pk=heute_abend.pk).update(status=InstanzStatus.RESERVIERT)
    assert services.verfall_pruefen(jetzt=lok(2026, 10, 11, 9)) == {"verfallen": 0, "vorgewarnt": 0}


def test_ungebundene_verfallen_nie(neue_aufgabe):
    neue_aufgabe()
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 8))
    assert services.verfall_pruefen(jetzt=lok(2026, 12, 1, 8))["verfallen"] == 0


# --- Verschieben (AP14) -----------------------------------------------------------------------


def test_verschieben_aendert_datum_ohne_neuerzeugung(neue_aufgabe, mama):
    aufgabe = zeitgebunden(neue_aufgabe)
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 8))
    anzahl = aufgabe.instanzen.count()
    services.verfall_pruefen(jetzt=lok(2026, 10, 10, 17, 30))  # Vorwarnung gesendet
    erste = aufgabe.instanzen.get(plan_datum=date(2026, 10, 10))
    instanz = services.instanz_verschieben(erste, date(2026, 10, 12), von=mama, sortierung=3)
    assert instanz.faellig_am == date(2026, 10, 12)
    assert instanz.plan_datum == date(2026, 10, 10)
    assert zeit.lokal(instanz.fenster_ende) == lok(2026, 10, 12, 20)
    assert instanz.vorwarnung_am is None
    assert instanz.sortierung == 3
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 10, 9))
    assert aufgabe.instanzen.count() == anzahl
    assert aufgabe.instanzen.filter(faellig_am=date(2026, 10, 12)).count() == 2


# --- Reservierung (Hooks für AP12) ------------------------------------------------------------


def test_reservierungsfrist(heute_abend, neue_aufgabe):
    ab = lok(2026, 10, 10, 9)
    assert services.reservierung_frist(heute_abend, ab) == heute_abend.fenster_ende
    neue_aufgabe(titel="frei")
    services.instanzen_erzeugen(jetzt=ab)
    frei = AufgabenInstanz.objects.get(fenster_ende__isnull=True)
    assert services.reservierung_frist(frei, ab) == ab + timedelta(hours=48)


def test_reservierung_erinnerung_und_ablauf(neue_aufgabe, anna):
    neue_aufgabe()
    start = lok(2026, 10, 10, 9)
    services.instanzen_erzeugen(jetzt=start)
    instanz = AufgabenInstanz.objects.get()
    bis = services.reservierung_frist(instanz, start)
    AufgabenInstanz.objects.filter(pk=instanz.pk).update(
        status=InstanzStatus.RESERVIERT, kind=anna, reserviert_bis=bis
    )
    aufgerufen = []
    hook = services.reservierungsablauf_hook_registrieren(lambda i, k: aufgerufen.append((i.pk, k)))
    try:
        assert services.reservierungen_pruefen(jetzt=bis - timedelta(hours=7))["erinnert"] == 0
        assert services.reservierungen_pruefen(jetzt=bis - timedelta(hours=6))["erinnert"] == 1
        assert services.reservierungen_pruefen(jetzt=bis - timedelta(hours=1))["erinnert"] == 0
        assert ereignisse(events.RESERVIERUNG_ERINNERUNG).get().kind == anna

        assert services.reservierungen_pruefen(jetzt=bis)["abgelaufen"] == 1
        assert services.reservierungen_pruefen(jetzt=bis)["abgelaufen"] == 0
    finally:
        from apps.aufgaben import instanzen

        instanzen._ablauf_hooks.remove(hook)
    instanz.refresh_from_db()
    assert (instanz.status, instanz.kind, instanz.reserviert_bis) == (
        InstanzStatus.OFFEN,
        None,
        None,
    )
    assert ereignisse(events.RESERVIERUNG_ABGELAUFEN).count() == 1
    assert aufgerufen == [(instanz.pk, anna)]


# --- Commands ---------------------------------------------------------------------------------


def test_commands_laufen_ueber_job_sperre(neue_aufgabe):
    zeitgebunden(neue_aufgabe, start_datum=zeit.heute())
    call_command("aufgaben_erzeugen")
    anzahl = AufgabenInstanz.objects.count()
    call_command("aufgaben_erzeugen")
    call_command("verfall_pruefen")
    assert AufgabenInstanz.objects.count() == anzahl > 0
    laeufe = JobLauf.objects.filter(name__in=["aufgaben_erzeugen", "verfall_pruefen"])
    assert laeufe.count() == 3
    assert set(laeufe.values_list("status", flat=True)) == {"ok"}
