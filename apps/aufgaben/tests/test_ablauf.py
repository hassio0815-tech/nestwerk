"""Kinderablauf (AP12): Interesse, Konflikt, Zuteilung, Reservierungsablauf, Meldung,
Bestätigung, Vertrauen, Korrektur, Sonderpunkte, Limit pro Zeitraum, Hooks."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.aufgaben import ablauf, events, selectors, services, wiederholung
from apps.aufgaben.models import (
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Interesse,
    InteresseStatus,
    Meldung,
    MeldungStatus,
    Status,
)
from apps.ereignisse.models import Ereignis
from apps.kern import einstellungen
from apps.kern.models import AuditEintrag
from apps.punkte import selectors as punkte_selectors
from apps.punkte.models import Art, Buchung

BERLIN = ZoneInfo("Europe/Berlin")
S = InstanzStatus


def lok(*args):
    return datetime(*args, tzinfo=BERLIN)


T0 = lok(2026, 10, 14, 10)  # Mittwoch


@pytest.fixture
def aufgabe(mama):
    def anlegen(**felder):
        werte = {
            "titel": "Rasen mähen",
            "punkte": 10,
            "erstellt_von": mama,
            "wiederholungsart": wiederholung.EINMALIG,
            "freigabeart": "eltern",
        }
        werte.update(felder)
        return Aufgabe.objects.create(**werte)

    return anlegen


SPAETER = lok(2026, 11, 30, 20)


def instanz_von(aufgabe, *, tag=None, fenster_ende=None):
    return AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        plan_datum=tag,
        faellig_am=tag,
        fenster_start=fenster_ende - timedelta(hours=2) if fenster_ende else None,
        fenster_ende=fenster_ende,
        titel_snapshot=aufgabe.titel,
        punkte_snapshot=aufgabe.punkte,
        freigabeart_snapshot=aufgabe.freigabeart,
    )


@pytest.fixture
def instanz(aufgabe):
    return instanz_von(aufgabe())


def ereignisse(typ):
    return Ereignis.objects.filter(typ_id=typ)


def frisch(i):
    i.refresh_from_db()
    return i


# --- Interesse, Reservierung, Konflikt (K11) ---------------------------------------------------


def test_ein_interessent_reserviert_mit_48h_frist(instanz, anna):
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    i = frisch(instanz)
    assert (i.status, i.kind, i.reserviert_bis) == (S.RESERVIERT, anna, T0 + timedelta(hours=48))
    assert Interesse.objects.get().status == InteresseStatus.ZUGETEILT
    assert ereignisse(events.INTERESSE).get().kind == anna
    with pytest.raises(services.AblaufFehler, match="schon gewählt"):
        services.interesse_zeigen(instanz, anna, jetzt=T0)


def test_zeitgebunden_frist_ist_fensterende(aufgabe, anna):
    ende = lok(2026, 10, 14, 20)
    i = instanz_von(aufgabe(fenster_bis=time(20)), tag=date(2026, 10, 14), fenster_ende=ende)
    services.interesse_zeigen(i, anna, jetzt=T0)
    assert frisch(i).reserviert_bis == ende
    with pytest.raises(services.AblaufFehler, match="vorbei"):
        services.interesse_zeigen(instanz_von(aufgabe(), fenster_ende=T0), anna, jetzt=T0)


def test_konflikt_stoppt_frist_und_zuteilung_startet_sie(instanz, anna, ben, mama):
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    services.interesse_zeigen(instanz, ben, jetzt=T0 + timedelta(hours=1))
    i = frisch(instanz)
    assert (i.status, i.kind, i.reserviert_bis) == (S.KONFLIKT, None, None)
    assert ereignisse(events.KONFLIKT).count() == 1
    assert set(Interesse.objects.values_list("status", flat=True)) == {InteresseStatus.AKTIV}

    zuteilung = T0 + timedelta(hours=30)
    services.zuteilen(instanz, ben, von=mama, jetzt=zuteilung)
    i = frisch(instanz)
    assert (i.status, i.kind) == (S.RESERVIERT, ben)
    assert i.reserviert_bis == zuteilung + timedelta(hours=48)  # K11: ab Zuteilung
    assert Interesse.objects.get(kind=ben).status == InteresseStatus.ZUGETEILT
    verloren = Interesse.objects.get(kind=anna)
    assert (verloren.status, verloren.entschieden_von) == (InteresseStatus.VERDRAENGT, mama)
    assert ereignisse(events.ZUGETEILT).get().kind == ben
    assert ereignisse(events.VERGEBEN).get().kind == anna
    # Anna sieht "vergeben", nicht mehr als offene Aufgabe
    eigene = selectors.kind_eigene(anna, jetzt=zuteilung)
    assert [(e.pk, e.anzeige_status) for e in eigene] == [(instanz.pk, "vergeben")]
    assert AuditEintrag.objects.filter(aktion="aufgabe.zugeteilt", akteur=mama).exists()


def test_konflikt_ohne_mitbewerben_nicht_moeglich(instanz, anna, ben):
    einstellungen.setzen("aufgaben.mitbewerben_erlaubt", False, akteur=None)
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    with pytest.raises(services.UngueltigerUebergang, match="nicht mehr frei"):
        services.interesse_zeigen(instanz, ben, jetzt=T0)
    assert selectors.kind_offene(ben, jetzt=T0) == []


def test_rueckzug_im_konflikt_reserviert_fuer_den_rest(instanz, anna, ben):
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    services.interesse_zeigen(instanz, ben, jetzt=T0)
    spaeter = T0 + timedelta(hours=5)
    services.zurueckgeben(instanz, anna, jetzt=spaeter)
    i = frisch(instanz)
    assert (i.status, i.kind, i.reserviert_bis) == (
        S.RESERVIERT,
        ben,
        spaeter + timedelta(hours=48),
    )


def test_eltern_loesen_reservierung_und_konflikt(aufgabe, anna, ben, mama):
    a, b = instanz_von(aufgabe()), instanz_von(aufgabe(titel="B"))
    services.interesse_zeigen(a, anna, jetzt=T0)
    services.interesse_zeigen(b, anna, jetzt=T0)
    services.interesse_zeigen(b, ben, jetzt=T0)
    services.reservierung_loesen(a, von=mama)
    services.reservierung_loesen(b, von=mama)
    for i in (a, b):
        assert (frisch(i).status, i.kind, i.reserviert_bis) == (S.OFFEN, None, None)
    assert not Interesse.objects.filter(status__in=["aktiv", "zugeteilt"]).exists()
    assert ereignisse(events.GELOEST).count() == 3
    with pytest.raises(services.NichtErlaubt):
        services.reservierung_loesen(a, von=anna)


def test_kind_gibt_zurueck(instanz, anna, ben):
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    with pytest.raises(services.NichtErlaubt):
        services.zurueckgeben(instanz, ben)
    services.zurueckgeben(instanz, anna)
    assert frisch(instanz).status == S.OFFEN
    assert Interesse.objects.get().status == InteresseStatus.ZURUECKGEZOGEN
    services.interesse_zeigen(instanz, anna, jetzt=T0)  # keine Strafe, erneut möglich


# --- Reservierungsablauf, Konflikt-Verfall (AP11-Korrekturen) ---------------------------------


def test_ungebundener_ablauf_macht_frei_und_meldet_einmal(instanz, anna):
    services.interesse_zeigen(instanz, anna, jetzt=T0)
    bis = frisch(instanz).reserviert_bis
    assert services.reservierungen_pruefen(jetzt=bis - timedelta(hours=6))["erinnert"] == 1
    assert ereignisse(events.RESERVIERUNG_ERINNERUNG).get().kind == anna
    assert services.reservierungen_pruefen(jetzt=bis)["abgelaufen"] == 1
    assert (frisch(instanz).status, instanz.kind) == (S.OFFEN, None)
    assert Interesse.objects.get().status == InteresseStatus.ABGELAUFEN
    assert ereignisse(events.RESERVIERUNG_ABGELAUFEN).count() == 1


def test_zeitgebundener_ablauf_nur_eine_eltern_meldung(aufgabe, anna):
    ende = lok(2026, 10, 14, 20)
    i = instanz_von(aufgabe(fenster_bis=time(20)), tag=date(2026, 10, 14), fenster_ende=ende)
    services.interesse_zeigen(i, anna, jetzt=T0)
    for _ in range(2):
        services.reservierungen_pruefen(jetzt=ende + timedelta(minutes=5))
        services.verfall_pruefen(jetzt=ende + timedelta(minutes=5))
    i = frisch(i)
    assert (i.status, i.abgeschlossen_am) == (S.NICHT_UEBERNOMMEN, ende + timedelta(minutes=5))
    assert ereignisse(events.RESERVIERUNG_ABGELAUFEN).count() == 1
    assert ereignisse(events.RESERVIERUNG_ABGELAUFEN).get().daten["nicht_uebernommen"] is True
    assert not ereignisse(events.NICHT_UEBERNOMMEN).exists()
    assert Interesse.objects.get().status == InteresseStatus.ABGELAUFEN


def test_konflikt_verfaellt_am_fensterende(aufgabe, anna, ben):
    ende = lok(2026, 10, 14, 20)
    i = instanz_von(aufgabe(fenster_bis=time(20)), tag=date(2026, 10, 14), fenster_ende=ende)
    services.interesse_zeigen(i, anna, jetzt=T0)
    services.interesse_zeigen(i, ben, jetzt=T0)
    assert services.verfall_pruefen(jetzt=ende - timedelta(hours=3))["vorgewarnt"] == 1
    assert services.reservierungen_pruefen(jetzt=ende)["abgelaufen"] == 0  # keine Frist
    assert services.verfall_pruefen(jetzt=ende)["verfallen"] == 1
    assert services.verfall_pruefen(jetzt=ende)["verfallen"] == 0
    assert frisch(i).status == S.NICHT_UEBERNOMMEN
    assert set(Interesse.objects.values_list("status", flat=True)) == {InteresseStatus.ABGELAUFEN}
    assert ereignisse(events.NICHT_UEBERNOMMEN).count() == 1


# --- Meldung und Entscheidung -----------------------------------------------------------------


def reserviert(instanz, kind):
    services.interesse_zeigen(instanz, kind, jetzt=T0)
    return frisch(instanz)


def test_bestaetigen_bucht_einmal_mit_meldedatum(instanz, anna, mama):
    reserviert(instanz, anna)
    sonntag = lok(2026, 10, 18, 19)
    services.erledigt_melden(instanz, anna, text="Fertig, auch die Kanten", jetzt=sonntag)
    i = frisch(instanz)
    assert (i.status, i.gemeldet_am) == (S.GEMELDET, sonntag)
    assert ereignisse(events.GEMELDET).get().daten["mit_text"] is True
    assert "Kanten" not in str(ereignisse(events.GEMELDET).get().daten)

    montag = lok(2026, 10, 19, 8)
    services.bestaetigen(instanz, von=mama, jetzt=montag)
    with pytest.raises(services.UngueltigerUebergang):
        services.bestaetigen(instanz, von=mama, jetzt=montag)  # Doppelklick
    buchung = Buchung.objects.get()
    assert (buchung.art, buchung.guthaben_delta, buchung.idempotenz_schluessel) == (
        Art.AUFGABE,
        10,
        f"aufgabe:{instanz.pk}:basis",
    )
    assert buchung.bezugsdatum == date(2026, 10, 18)  # K1: Meldedatum (Sonntag)
    assert buchung.erstellt_von == mama
    erledigt = ereignisse(events.ERLEDIGT).get()
    assert erledigt.daten["bezugsdatum"] == "2026-10-18"
    assert ereignisse(events.BESTAETIGT).get().kind == anna
    meldung = Meldung.objects.get()
    assert (meldung.status, meldung.text, meldung.entschieden_von) == (
        MeldungStatus.BESTAETIGT,
        "",
        mama,
    )
    assert meldung.nachweis_geloescht_am == montag
    nachweis = AuditEintrag.objects.get(aktion="aufgabe.nachweis_geloescht")
    assert "Kanten" not in str(nachweis.details) and nachweis.akteur == mama


def test_nachweis_braucht_text_oder_foto(aufgabe, anna):
    i = reserviert(instanz_von(aufgabe(freigabeart="nachweis")), anna)
    with pytest.raises(services.AblaufFehler, match="Foto"):
        services.erledigt_melden(i, anna)
    gespeichert = []
    echte = list(ablauf._nachweis_speicher)  # AP13-Speicher für diesen Test beiseite
    ablauf._nachweis_speicher.clear()
    with pytest.raises(services.AblaufFehler, match="noch nicht"):
        services.erledigt_melden(i, anna, fotos=["bild"])
    hook = services.nachweis_speicher_registrieren(lambda m, f, neu: gespeichert.append((m.pk, f)))
    try:
        services.erledigt_melden(i, anna, fotos=["bild"])
    finally:
        ablauf._nachweis_speicher.remove(hook)
        ablauf._nachweis_speicher.extend(echte)
    assert gespeichert == [(Meldung.objects.get().pk, ["bild"])]


def test_nur_inhaber_meldet(instanz, anna, ben):
    reserviert(instanz, anna)
    with pytest.raises(services.NichtErlaubt):
        services.erledigt_melden(instanz, ben)
    with pytest.raises(services.UngueltigerUebergang):
        services.erledigt_melden(instanz_von(instanz.aufgabe, fenster_ende=SPAETER), anna)


def test_rueckfrage_antwort_ablehnen(instanz, anna, mama):
    reserviert(instanz, anna)
    services.erledigt_melden(instanz, anna, text="erledigt")
    with pytest.raises(services.AblaufFehler):
        services.rueckfrage_stellen(instanz, von=mama, text="")
    services.rueckfrage_stellen(instanz, von=mama, text="Auch hinter dem Haus?")
    assert frisch(instanz).status == S.RUECKFRAGE
    assert selectors.kind_eigene(anna)[0].rueckfrage_text == "Auch hinter dem Haus?"
    assert "Haus" not in str(ereignisse(events.RUECKFRAGE).get().daten)
    services.rueckfrage_beantworten(instanz, anna, text="Ja")
    m = Meldung.objects.get()
    assert (frisch(instanz).status, m.status, m.antwort_text) == (S.GEMELDET, "offen", "Ja")
    services.ablehnen(instanz, von=mama, begruendung="Nur halb gemäht")
    m.refresh_from_db()
    assert frisch(instanz).status == S.ABGELEHNT
    assert (m.text, m.antwort_text, m.rueckfrage_text) == ("", "", "")
    assert not Buchung.objects.exists()
    assert ereignisse(events.ABGELEHNT).get().daten["begruendung"] == "Nur halb gemäht"


def test_rueckfrage_kann_direkt_bestaetigt_werden(instanz, anna, mama):
    reserviert(instanz, anna)
    services.erledigt_melden(instanz, anna)
    services.rueckfrage_stellen(instanz, von=mama, text="?")
    services.bestaetigen(instanz, von=mama)
    assert frisch(instanz).status == S.BESTAETIGT
    assert punkte_selectors.guthaben(anna) == 10


def test_kind_kann_nicht_bestaetigen(instanz, anna):
    reserviert(instanz, anna)
    services.erledigt_melden(instanz, anna)
    with pytest.raises(services.NichtErlaubt):
        services.bestaetigen(instanz, von=anna)


# --- Vertrauen und Korrektur (K2) -------------------------------------------------------------


def test_vertrauen_bucht_sofort_korrektur_per_gegenbuchung(aufgabe, anna, mama):
    i = reserviert(instanz_von(aufgabe(freigabeart="vertrauen")), anna)
    services.erledigt_melden(i, anna, text="wird nicht gespeichert", jetzt=T0)
    i = frisch(i)
    assert (i.status, i.bestaetigt_von, i.gemeldet_am) == (S.BESTAETIGT, None, T0)
    assert punkte_selectors.salden(anna) == punkte_selectors.Saldo(guthaben=10, xp=10)
    assert Meldung.objects.get().text == ""
    assert ereignisse(events.VERTRAUEN).count() == 1
    assert ereignisse(events.ERLEDIGT).get().daten["vertrauen"] is True

    services.sonderpunkte_vergeben(i, 3, "sehr ordentlich", von=mama)
    with pytest.raises(services.AblaufFehler):
        services.korrigieren(i, von=mama, begruendung="")
    services.korrigieren(i, von=mama, begruendung="War nicht erledigt")
    assert frisch(i).status == S.STORNIERT
    assert punkte_selectors.salden(anna) == punkte_selectors.Saldo(guthaben=0, xp=0)
    assert Buchung.objects.filter(art=Art.STORNO).count() == 2
    assert ereignisse(events.KORRIGIERT).get().daten["punkte"] == 13
    with pytest.raises(services.UngueltigerUebergang):
        services.korrigieren(i, von=mama, begruendung="nochmal")
    assert Buchung.objects.filter(art=Art.STORNO).count() == 2


# --- Sonderpunkte (Deckel) --------------------------------------------------------------------


def bestaetigt(instanz, kind, eltern, **extra):
    reserviert(instanz, kind)
    services.erledigt_melden(instanz, kind)
    return services.bestaetigen(instanz, von=eltern, **extra)


def test_sonderpunkte_mit_deckel_bei_bestaetigung(instanz, anna, mama):
    reserviert(instanz, anna)
    services.erledigt_melden(instanz, anna)
    assert services.sonderpunkte_deckel(instanz) == 5  # 50 % von 10
    with pytest.raises(services.AblaufFehler, match="Höchstens 5"):
        services.bestaetigen(instanz, von=mama, sonderpunkte=6, begruendung="toll")
    with pytest.raises(services.AblaufFehler, match="Begründung"):
        services.bestaetigen(instanz, von=mama, sonderpunkte=2)
    assert frisch(instanz).status == S.GEMELDET  # Fehler -> nichts passiert
    services.bestaetigen(instanz, von=mama, sonderpunkte=5, begruendung="sehr gründlich")
    i = frisch(instanz)
    assert (i.sonderpunkte, i.sonderpunkte_begruendung) == (5, "sehr gründlich")
    assert punkte_selectors.guthaben(anna) == 15
    bonus = Buchung.objects.get(art=Art.SONDERPUNKTE)
    assert (bonus.begruendung, bonus.bezugsdatum) == (
        "sehr gründlich",
        Buchung.objects.get(art=Art.AUFGABE).bezugsdatum,
    )
    with pytest.raises(services.AblaufFehler, match="schon"):
        services.sonderpunkte_vergeben(instanz, 1, "nochmal", von=mama)
    # Kind sieht Bonus + Begründung
    eigene = selectors.kind_eigene(anna)[0]
    assert (eigene.sonderpunkte, eigene.sonderpunkte_begruendung) == (5, "sehr gründlich")
    assert ereignisse(events.SONDERPUNKTE).get().daten["begruendung"] == "sehr gründlich"


def test_deckel_aufgerundet_eigener_wert_und_abschaltbar(aufgabe, anna, mama):
    fuenf = bestaetigt(instanz_von(aufgabe(punkte=5)), anna, mama)
    assert services.sonderpunkte_deckel(fuenf) == 3
    eigen = bestaetigt(instanz_von(aufgabe(sonderpunkte_deckel_prozent=20)), anna, mama)
    assert services.sonderpunkte_deckel(eigen) == 2
    einstellungen.setzen("aufgaben.sonderpunkte_deckel_aktiv", False, akteur=None)
    assert services.sonderpunkte_deckel(fuenf) is None
    assert services.sonderpunkte_deckel(eigen) == 2  # eigener Wert gilt weiter
    services.sonderpunkte_vergeben(fuenf, 100, "Extra-Einsatz", von=mama)
    with pytest.raises(services.AblaufFehler):
        services.sonderpunkte_vergeben(eigen, 3, "zu viel", von=mama)
    with pytest.raises(services.UngueltigerUebergang):
        services.sonderpunkte_vergeben(instanz_von(aufgabe()), 1, "offen", von=mama)


# --- Limit pro Zeitraum (K10) -----------------------------------------------------------------


def test_limit_pro_woche_je_kind_und_aufgabe(aufgabe, anna, ben, mama):
    a = aufgabe(limit_anzahl=1, limit_zeitraum="woche")
    erste, zweite, dritte = (instanz_von(a, fenster_ende=SPAETER) for _ in range(3))
    services.interesse_zeigen(erste, anna, jetzt=T0)
    with pytest.raises(services.LimitErreicht, match="1× pro Woche"):
        services.interesse_zeigen(zweite, anna, jetzt=T0)  # laufende zählt
    services.interesse_zeigen(zweite, ben, jetzt=T0)  # anderes Kind: eigenes Limit
    services.erledigt_melden(erste, anna, jetzt=T0)
    services.bestaetigen(erste, von=mama, jetzt=T0)
    assert services.limit_stand(a, anna, jetzt=T0) == (1, 1)
    offene = selectors.kind_offene(anna, jetzt=T0)
    assert [o.limit_erreicht for o in offene if o.pk == dritte.pk] == [True]
    with pytest.raises(services.LimitErreicht):
        services.interesse_zeigen(dritte, anna, jetzt=lok(2026, 10, 18, 23))  # noch Woche 42
    services.interesse_zeigen(dritte, anna, jetzt=lok(2026, 10, 19, 0, 1))  # neue Woche


def test_limit_abgelehnt_und_zurueckgegeben_zaehlen_nicht(aufgabe, anna, mama):
    a = aufgabe(limit_anzahl=1, limit_zeitraum="tag")
    erste, zweite = instanz_von(a, fenster_ende=SPAETER), instanz_von(a, fenster_ende=SPAETER)
    services.interesse_zeigen(erste, anna, jetzt=T0)
    services.zurueckgeben(erste, anna)
    services.interesse_zeigen(erste, anna, jetzt=T0)
    services.erledigt_melden(erste, anna, jetzt=T0)
    services.ablehnen(erste, von=mama)
    services.interesse_zeigen(zweite, anna, jetzt=T0)


@pytest.mark.parametrize(
    ("art", "jetzt", "beginn", "ende"),
    [
        ("tag", lok(2026, 10, 25, 12), lok(2026, 10, 25), lok(2026, 10, 26)),
        ("woche", lok(2026, 10, 14, 12), lok(2026, 10, 12), lok(2026, 10, 19)),
        ("monat", lok(2026, 12, 31, 23), lok(2026, 12, 1), lok(2027, 1, 1)),
    ],
)
def test_zeitraeume(db, art, jetzt, beginn, ende):
    from apps.kern.models import Einstellung

    Einstellung.objects.get_or_create(
        schluessel="allgemein.zeitzone", defaults={"wert": "Europe/Berlin", "modul": "allgemein"}
    )
    assert ablauf.zeitraum(art, jetzt) == (beginn, ende)


# --- Sichtbarkeit -----------------------------------------------------------------------------


def test_kind_sieht_nur_eigene_und_freie(aufgabe, anna, ben, mama):
    frei = instanz_von(aufgabe(titel="frei"))
    fuer_ben = instanz_von(aufgabe(titel="nur Ben", zugewiesen_an=ben))
    pausiert = instanz_von(aufgabe(titel="pausiert", status=Status.PAUSIERT))
    morgen = lok(2026, 10, 15, 20)
    spaeter = instanz_von(
        aufgabe(titel="später"), tag=date(2026, 10, 20), fenster_ende=lok(2026, 10, 20, 20)
    )
    instanz_von(aufgabe(titel="morgen"), tag=date(2026, 10, 15), fenster_ende=morgen)
    bens = instanz_von(aufgabe(titel="Bens gemeldete"))
    bestaetigt(bens, ben, mama)
    bens.refresh_from_db()

    offene = {i.titel_snapshot for i in selectors.kind_offene(anna, jetzt=T0)}
    assert offene == {"frei", "morgen"}
    assert {i.titel_snapshot for i in selectors.kind_offene(ben, jetzt=T0)} == {
        "frei",
        "morgen",
        "nur Ben",
    }
    assert selectors.kind_eigene(anna, jetzt=T0) == []
    with pytest.raises(services.NichtErlaubt):
        services.interesse_zeigen(fuer_ben, anna, jetzt=T0)
    with pytest.raises(services.AblaufFehler, match="pausiert"):
        services.interesse_zeigen(pausiert, anna, jetzt=T0)
    assert not services.kind_darf_sehen(bens, anna)
    assert services.kind_darf_sehen(frei, anna) and not services.kind_darf_sehen(fuer_ben, anna)
    assert spaeter.pk and services.kind_darf_sehen(spaeter, anna)


# --- Hooks für Phase 2 / AP21 -----------------------------------------------------------------


def test_erledigung_und_storno_hooks(instanz, anna, mama):
    erledigt, storniert = [], []
    h1 = services.erledigung_hook_registrieren(erledigt.append)
    h2 = services.storno_hook_registrieren(lambda i, k, v: storniert.append((i.pk, k, v)))
    try:
        reserviert(instanz, anna)
        services.erledigt_melden(instanz, anna, jetzt=lok(2026, 10, 18, 19))
        services.bestaetigen(instanz, von=mama)
        services.korrigieren(instanz, von=mama, begruendung="Fehler")
    finally:
        ablauf._erledigung_hooks.remove(h1)
        ablauf._storno_hooks.remove(h2)
    (e,) = erledigt
    assert (e.kind, e.bezugsdatum, e.punkte, e.vertrauen, e.von) == (
        anna,
        date(2026, 10, 18),
        10,
        False,
        mama,
    )
    assert e.buchung.idempotenz_schluessel == f"aufgabe:{instanz.pk}:basis"
    assert storniert == [(instanz.pk, anna, mama)]


# --- Plan-Änderung / Pause mit verschobenen Instanzen -----------------------------------------


def test_plan_aenderung_behaelt_verschobene_pause_nicht(mama):
    from apps.aufgaben.forms import AufgabeForm
    from apps.kern import zeit

    heute = zeit.heute()
    aufgabe = Aufgabe.objects.create(
        titel="Tonnen",
        punkte=10,
        erstellt_von=mama,
        wiederholungsart=wiederholung.INTERVALL,
        intervall_tage=1,
        start_datum=heute + timedelta(days=1),
        fenster_von=time(18),
        fenster_bis=time(20),
    )
    services.instanzen_erzeugen()
    erste = aufgabe.instanzen.order_by("plan_datum").first()
    services.instanz_verschieben(erste, erste.plan_datum + timedelta(days=30), von=mama)
    anzahl = aufgabe.instanzen.count()

    daten = AufgabeForm(instance=aufgabe).initial | {"punkte": 20, "titel": "Tonnen raus"}
    daten = {k: v for k, v in daten.items() if v is not None}
    daten["wochentage"] = []
    form = AufgabeForm(daten, instance=aufgabe)
    assert form.is_valid(), form.errors
    services.aufgabe_speichern(form, von=mama)
    erste.refresh_from_db()  # verschobene bleibt, mit neuem Snapshot
    assert (erste.titel_snapshot, erste.punkte_snapshot) == ("Tonnen raus", 20)
    assert aufgabe.instanzen.count() == anzahl
    assert not aufgabe.instanzen.filter(plan_datum=erste.plan_datum).exclude(pk=erste.pk).exists()

    services.aufgabe_status_setzen(aufgabe, Status.PAUSIERT, von=mama)
    assert not aufgabe.instanzen.exists()
