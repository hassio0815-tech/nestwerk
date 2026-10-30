"""Schnell-Knöpfe: Aufgaben "bei Bedarf" schlafen, bis jemand den Knopf drückt."""

import pytest
from django.urls import reverse

from apps.aufgaben import events, schnellknopf, services, wiederholung
from apps.aufgaben.forms import AufgabeForm
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.benachrichtigung import router
from apps.benachrichtigung.models import Benachrichtigung
from apps.ereignisse.models import Ereignis
from apps.konten import services as konten
from apps.konten.models import GeraeteTyp
from apps.konten.tests.conftest import client_fuer

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def knopf(mama):
    def anlegen(titel="Restmüll", **felder):
        werte = {
            "titel": titel,
            "punkte": 5,
            "erstellt_von": mama,
            "freigabeart": "eltern",
            "wiederholungsart": wiederholung.BEI_BEDARF,
            "emoji": "🗑️",
        }
        werte.update(felder)
        return Aufgabe.objects.create(**werte)

    return anlegen


@pytest.fixture
def tablet(db, mama):
    return konten.geraet_registrieren("Flur-Tablet", GeraeteTyp.KIOSK, registriert_von=mama)


def instanzen(aufgabe):
    return AufgabenInstanz.objects.filter(aufgabe=aufgabe)


def test_druck_legt_genau_eine_offene_instanz_an(knopf, anna, mama):
    aufgabe = knopf()
    instanz, neu = schnellknopf.druecken(aufgabe, von=mama)
    assert neu and instanzen(aufgabe).count() == 1
    assert instanz.status == InstanzStatus.OFFEN and instanz.kind is None
    assert instanz.punkte_snapshot == 5 and instanz.freigabeart_snapshot == "eltern"


def test_zweiter_druck_macht_nichts(knopf, anna, ben, mama):
    aufgabe = knopf()
    erste, _ = schnellknopf.druecken(aufgabe, von=mama)
    zweite, neu = schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    assert not neu and zweite.pk == erste.pk and instanzen(aufgabe).count() == 1
    assert [a.laeuft.pk for a in schnellknopf.knoepfe(ben)] == [erste.pk]


def test_nach_abschluss_geht_wieder_ein_druck(knopf, mama):
    aufgabe = knopf()
    instanz, _ = schnellknopf.druecken(aufgabe, von=mama)
    AufgabenInstanz.objects.filter(pk=instanz.pk).update(status=InstanzStatus.BESTAETIGT)
    _, neu = schnellknopf.druecken(aufgabe, von=mama)
    assert neu and instanzen(aufgabe).count() == 2


def test_ich_machs_reserviert_fuer_das_kind(knopf, anna):
    instanz, neu = schnellknopf.druecken(knopf(), von=anna, kind=anna)
    assert neu and instanz.status == InstanzStatus.RESERVIERT and instanz.kind == anna
    assert instanz.reserviert_bis is not None
    assert schnellknopf.knoepfe(anna)[0].laeuft.kind == anna


def test_kind_kann_nicht_fuer_anderes_kind_druecken(knopf, anna, ben):
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(knopf(), von=anna, kind=ben)
    assert not AufgabenInstanz.objects.exists()


def test_eltern_knopf_nicht_fuer_kinder(knopf, anna, mama):
    aufgabe = knopf(schnellknopf_wer="eltern")
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(aufgabe, von=anna)
    with pytest.raises(services.NichtErlaubt):
        schnellknopf.druecken(aufgabe, von=None)  # Tablet
    assert schnellknopf.knoepfe(anna) == [] and schnellknopf.knoepfe(nur_kinder_knoepfe=True) == []
    assert len(schnellknopf.knoepfe(mama)) == 1
    _, neu = schnellknopf.druecken(aufgabe, von=mama, kind=anna)
    assert neu


def test_eltern_knopf_ueber_kind_kachel_abgewiesen(knopf, kind_client, anna):
    aufgabe = knopf(schnellknopf_wer="eltern")
    antwort = kind_client.post(reverse("aufgaben:schnellknopf_kind", args=[aufgabe.pk]), **HTMX)
    assert antwort.status_code == 200 and "nur Eltern" in antwort.content.decode()
    assert not instanzen(aufgabe).exists()
    assert "Restmüll" not in kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()


def test_wochenplan_erzeugung_ignoriert_bei_bedarf(knopf):
    aufgabe = knopf(start_datum="2026-01-01")
    ergebnis = services.instanzen_erzeugen()
    assert ergebnis["aufgaben"] == 0 and not instanzen(aufgabe).exists()
    assert aufgabe.plan.art == wiederholung.BEI_BEDARF and not aufgabe.zeitgebunden


def test_nur_melden_benachrichtigt_kinder_in_ihrer_sprache(knopf, anna, ben, mama):
    konten.sprache_setzen(ben, "en")
    schnellknopf.druecken(knopf(), von=mama)
    ereignisse = Ereignis.objects.filter(typ_id=events.SCHNELLKNOPF)
    assert ereignisse.count() == 2
    for e in ereignisse:
        router.router(e)
    assert Benachrichtigung.objects.get(empfaenger=anna).titel == "Restmüll: wer macht's?"
    assert Benachrichtigung.objects.get(empfaenger=ben).titel == "General waste: who's up for it?"
    assert not Benachrichtigung.objects.filter(empfaenger=mama).exists()


def test_ich_machs_und_zweiter_druck_ohne_schnellknopf_meldung(knopf, anna, ben):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=anna, kind=anna)
    schnellknopf.druecken(aufgabe, von=ben)
    assert not Ereignis.objects.filter(typ_id=events.SCHNELLKNOPF).exists()


def test_drueckendes_kind_bekommt_keine_eigene_meldung(knopf, anna, ben):
    schnellknopf.druecken(knopf(), von=anna)
    assert [e.kind for e in Ereignis.objects.filter(typ_id=events.SCHNELLKNOPF)] == [ben]


# --- Tablet -----------------------------------------------------------------------------------


def test_tablet_kachel_nur_auf_dem_kiosk_geraet(knopf, anna, tablet):
    knopf()
    url = reverse("oberflaeche:tablet_teil")
    assert "Restmüll" in client_fuer(tablet).get(url).content.decode()
    assert "Restmüll" not in client_fuer().get(url).content.decode()


def test_tablet_druck_ohne_pin_fuer_kind(knopf, anna, tablet):
    aufgabe = knopf()
    c = client_fuer(tablet)
    wahl = c.get(reverse("aufgaben:schnellknopf_tablet_waehlen", args=[aufgabe.pk]), **HTMX)
    assert wahl.status_code == 200 and "Nur melden" in wahl.content.decode()
    antwort = c.post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"kind_id": str(anna.pk)},
        **HTMX,
    )
    assert antwort.status_code == 200 and "reserviert" in antwort.content.decode()
    instanz = instanzen(aufgabe).get()
    assert instanz.status == InstanzStatus.RESERVIERT and instanz.kind == anna


def test_tablet_nur_melden(knopf, anna, tablet):
    aufgabe = knopf()
    antwort = client_fuer(tablet).post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"modus": "melden"},
        **HTMX,
    )
    assert antwort.status_code == 200 and instanzen(aufgabe).get().kind is None


def test_tablet_ohne_registriertes_geraet_abgewiesen(knopf, anna, tablet, mama):
    aufgabe = knopf()
    url = reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk])
    assert client_fuer().post(url, {"kind_id": str(anna.pk)}).status_code == 403
    persoenlich = konten.geraet_registrieren("Handy", GeraeteTyp.PERSOENLICH, registriert_von=mama)
    assert client_fuer(persoenlich).post(url, {"kind_id": str(anna.pk)}).status_code == 403
    waehlen = reverse("aufgaben:schnellknopf_tablet_waehlen", args=[aufgabe.pk])
    assert client_fuer().get(waehlen).status_code == 403
    assert not instanzen(aufgabe).exists()


def test_tablet_verlangt_csrf(knopf, anna, tablet):
    aufgabe = knopf()
    c = client_fuer(tablet, enforce_csrf_checks=True)
    url = reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk])
    assert c.post(url, {"kind_id": str(anna.pk)}).status_code == 403
    assert not instanzen(aufgabe).exists()


def test_tablet_eltern_knopf_nicht_erreichbar(knopf, anna, tablet):
    aufgabe = knopf(schnellknopf_wer="eltern")
    c = client_fuer(tablet)
    assert (
        c.get(reverse("aufgaben:schnellknopf_tablet_waehlen", args=[aufgabe.pk])).status_code == 404
    )
    antwort = c.post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"modus": "melden"},
        **HTMX,
    )
    assert "nur Eltern" in antwort.content.decode() and not instanzen(aufgabe).exists()


def test_tablet_gesperrtes_kind_nicht_waehlbar(knopf, anna, tablet):
    from datetime import timedelta

    from apps.kern import zeit

    anna.kindprofil.pin_gesperrt_bis = zeit.jetzt() + timedelta(minutes=10)
    anna.kindprofil.save()
    aufgabe = knopf()
    antwort = client_fuer(tablet).post(
        reverse("aufgaben:schnellknopf_tablet_druecken", args=[aufgabe.pk]),
        {"kind_id": str(anna.pk)},
    )
    assert antwort.status_code == 404 and not instanzen(aufgabe).exists()


# --- Kacheln und Formular ---------------------------------------------------------------------


def test_eltern_kachel_zeigt_knopf_und_druck(eltern_client, knopf, anna):
    aufgabe = knopf()
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert "Restmüll" in html and "Anna macht&#x27;s" in html or "Anna macht's" in html
    antwort = eltern_client.post(
        reverse("aufgaben:schnellknopf_eltern", args=[aufgabe.pk]),
        {"kind_id": str(anna.pk)},
        **HTMX,
    )
    assert "läuft schon" in antwort.content.decode()
    assert instanzen(aufgabe).get().kind == anna


def test_kind_kachel_ich_machs(kind_client, knopf, anna):
    aufgabe = knopf()
    assert "Restmüll" in kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    antwort = kind_client.post(
        reverse("aufgaben:schnellknopf_kind", args=[aufgabe.pk]), {"modus": "ich"}, **HTMX
    )
    assert "Anna" in antwort.content.decode()
    assert instanzen(aufgabe).get().kind == anna


def test_englische_kachel_zeigt_englischen_titel(kind_client, knopf):
    knopf()  # Titel ist die deutsche Msgid aus den Startwerten
    kind_client.cookies["nestwerk_sprache"] = "en"
    html = kind_client.get(reverse("oberflaeche:kind_heim")).content.decode()
    assert "General waste" in html and "Quick buttons" in html


def test_formular_bei_bedarf_leert_zeitplan(eltern_client, mama):
    form = AufgabeForm(
        {
            "titel": "Altglas",
            "punkte": 5,
            "freigabeart": "eltern",
            "wiederholungsart": wiederholung.BEI_BEDARF,
            "wochentage": ["0"],
            "fenster_bis": "20:00",
            "emoji": "🍾",
            "schnellknopf_wer": "eltern",
        }
    )
    assert form.is_valid(), form.errors
    aufgabe = services.aufgabe_speichern(form, von=mama)
    assert aufgabe.wochentage is None and aufgabe.fenster_bis is None
    assert aufgabe.emoji == "🍾" and aufgabe.schnellknopf_wer == "eltern"
    html = eltern_client.get(reverse("aufgaben:liste")).content.decode()
    assert "Schnell-Knopf" in html
    assert "Bei Bedarf" in eltern_client.get(reverse("aufgaben:neu")).content.decode()


def test_aufgabe_aendern_behaelt_gedrueckten_knopf(knopf, mama):
    aufgabe = knopf()
    instanz, _ = schnellknopf.druecken(aufgabe, von=mama)
    aufgabe.punkte = 8
    services.offene_entfernen(aufgabe, verschobene_behalten=True)
    instanz.refresh_from_db()
    assert instanz.punkte_snapshot == 8


def test_pause_entfernt_offenen_knopf(knopf, mama):
    aufgabe = knopf()
    schnellknopf.druecken(aufgabe, von=mama)
    services.aufgabe_status_setzen(aufgabe, "pausiert", von=mama)
    assert not instanzen(aufgabe).exists()
