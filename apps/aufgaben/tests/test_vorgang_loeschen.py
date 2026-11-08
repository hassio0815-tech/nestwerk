"""Vorgang löschen: „als hätte es ihn nie gegeben“ (Punkte netto 0, überall ausgeblendet)."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse

from apps.aufgaben import events, selectors, services, wiederholung, wochenplan
from apps.aufgaben.models import (
    Aufgabe,
    AufgabenInstanz,
    InstanzStatus,
    Interesse,
    InteresseStatus,
    Meldung,
    Status,
)
from apps.benachrichtigung import selectors as benachrichtigung_selectors
from apps.benachrichtigung.models import Benachrichtigung, Popup
from apps.ereignisse import services as ereignisse
from apps.ereignisse.models import Ereignis
from apps.familienziel import selectors as familienziel
from apps.kern import einstellungen, zeit
from apps.kern.models import AuditEintrag
from apps.konten.tests.conftest import PIN, eltern_anmelden, kind_anmelden
from apps.oberflaeche import selectors as oberflaeche
from apps.punkte import selectors as punkte_selectors
from apps.punkte import services as punkte
from apps.punkte.models import Art, Buchung

S = InstanzStatus
BERLIN = ZoneInfo("Europe/Berlin")
HTMX = {"HTTP_HX_REQUEST": "true"}
TITEL = "Fenster putzen Spezial"
WURZEL = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _go_live(db):
    einstellungen.setzen("allgemein.go_live_datum", "2026-11-01", akteur=None)


def lok(*args):
    return datetime(*args, tzinfo=BERLIN)


@pytest.fixture
def anlegen(mama):
    zaehler = iter(range(1, 1000))

    def _anlegen(*, tag=None, status=S.OFFEN, titel=TITEL, **extra):
        n = next(zaehler)
        tag = tag or zeit.heute()
        aufgabe = Aufgabe.objects.create(
            titel=f"{titel} {n}",
            punkte=5,
            erstellt_von=mama,
            start_datum=date(2026, 10, 1),
            wiederholungsart=wiederholung.EINMALIG,
            freigabeart="eltern",
        )
        werte = {
            "aufgabe": aufgabe,
            "plan_datum": tag,
            "faellig_am": tag,
            "titel_snapshot": aufgabe.titel,
            "punkte_snapshot": aufgabe.punkte,
            "freigabeart_snapshot": aufgabe.freigabeart,
            "status": status,
        }
        werte.update(extra)
        return AufgabenInstanz.objects.create(**werte)

    return _anlegen


def gemeldet(anlegen, anna, **extra):
    instanz = anlegen(status=S.RESERVIERT, kind=anna, reserviert_bis=lok(2030, 1, 1), **extra)
    services.erledigt_melden(instanz, anna)
    instanz.refresh_from_db()
    assert instanz.status == S.GEMELDET
    return instanz


def bestaetigt(anlegen, anna, mama, bonus=3, **extra):
    instanz = gemeldet(anlegen, anna, **extra)
    services.bestaetigen(
        instanz, von=mama, sonderpunkte=bonus, begruendung="Gründlich" if bonus else ""
    )
    instanz.refresh_from_db()
    assert instanz.status == S.BESTAETIGT
    return instanz


def konto(kind):
    saldo = punkte_selectors.salden(kind)
    return saldo.guthaben, saldo.xp


def bezogen(instanz):
    return Buchung.objects.filter(referenz_typ="aufgaben.aufgabeninstanz", referenz_id=instanz.pk)


def netto(instanz):
    return sum(b.guthaben_delta for b in bezogen(instanz)), sum(
        b.xp_delta for b in bezogen(instanz)
    )


def kind_client_neu(anna):
    client = Client()
    kind_anmelden(client, anna, PIN)
    return client


def eltern_client_neu(mama):
    client = Client()
    eltern_anmelden(client, mama)
    return client


@pytest.fixture
def vorher(anna, mama):
    """Das Kind hat schon Punkte (Anerkennung), damit „wie vorher“ etwas aussagt."""
    from apps.aufgaben import anerkennung

    anerkennung.vergeben(anna, 10, "Hat geholfen", von=mama)
    return konto(anna)


# --- Punkte ---------------------------------------------------------------------------------


def test_punkte_netto_null_inkl_bonus_und_konto_wie_vorher(anlegen, anna, mama, vorher):
    instanz = bestaetigt(anlegen, anna, mama, bonus=3)
    assert konto(anna) == (vorher[0] + 8, vorher[1] + 8)
    assert {b.art for b in bezogen(instanz)} >= {Art.AUFGABE, Art.SONDERPUNKTE}

    services.vorgang_loeschen(instanz, von=mama)

    assert netto(instanz) == (0, 0)
    assert konto(anna) == vorher
    # jede Original-Buchung hat genau eine Gegenbuchung
    originale = bezogen(instanz).exclude(art=Art.STORNO)
    assert originale.count() >= 2
    assert all(hasattr(b, "storno") for b in originale)


def test_gegenbuchung_liegt_im_selben_bezugstag_wie_das_original(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    original = bezogen(instanz).get(art=Art.AUFGABE)
    services.vorgang_loeschen(instanz, von=mama)
    assert original.storno.bezugsdatum == original.bezugsdatum


def test_familienziel_fortschritt_geht_zurueck(anlegen, anna, mama):
    iso = zeit.IsoWoche.von(zeit.heute())
    leer = familienziel.stand(iso, 100).punkte
    instanz = bestaetigt(anlegen, anna, mama, bonus=2)
    assert familienziel.stand(iso, 100).punkte == leer + 7
    services.vorgang_loeschen(instanz, von=mama)
    assert familienziel.stand(iso, 100).punkte == leer


def test_serienbonus_wird_mit_zurueckgebucht(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    punkte.buchen(
        anna,
        Art.SERIENBONUS,
        2,
        schluessel=f"aufgabe:{instanz.pk}:serienbonus:0",
        quelle_modul="aufgaben",
        referenz=instanz,
        von=mama,
    )
    services.vorgang_loeschen(instanz, von=mama)
    assert netto(instanz) == (0, 0)
    assert punkte_selectors.buchungen(anna).count() == 0


def test_verlauf_der_kinder_zeigt_buchung_und_gegenbuchung_nicht(anlegen, anna, mama, vorher):
    instanz = bestaetigt(anlegen, anna, mama, bonus=3)
    assert punkte_selectors.buchungen(anna).count() == 1 + 2
    services.vorgang_loeschen(instanz, von=mama)
    sichtbar = list(punkte_selectors.buchungen(anna))
    assert [b.art for b in sichtbar] == [Art.ANERKENNUNG]
    assert [b.art for b in oberflaeche.kind_konto(anna)["verlauf"]] == [Art.ANERKENNUNG]
    # Salden sind trotzdem die Summe aller Buchungen
    assert Buchung.objects.filter(kind=anna).count() == 1 + 4


def test_nach_korrektur_wird_nur_der_rest_zurueckgebucht(anlegen, anna, mama, vorher):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    services.korrigieren(instanz, von=mama, begruendung="Fehler")
    assert konto(anna) == vorher
    anzahl = Buchung.objects.count()
    services.vorgang_loeschen(instanz, von=mama)
    assert Buchung.objects.count() == anzahl  # keine doppelte Gegenbuchung
    assert konto(anna) == vorher
    assert punkte_selectors.buchungen(anna).count() == 1  # auch das Korrektur-Paar ist weg


# --- Keine Nachricht ---------------------------------------------------------------------------


def test_keine_nachricht_ans_kind(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=3)
    letzte = Ereignis.objects.order_by("-pk").first().pk
    services.vorgang_loeschen(instanz, von=mama)
    neu = Ereignis.objects.filter(pk__gt=letzte)
    typen = set(neu.values_list("typ_id", flat=True))
    assert events.KORRIGIERT not in typen and events.GELOEST not in typen
    assert typen <= {"punkte.gebucht", events.GELOESCHT}, typen  # GELOESCHT: intern, ohne Empfänger


def test_reservierte_karte_ohne_kind_nachricht(anlegen, anna, mama):
    instanz = anlegen()
    services.interesse_zeigen(instanz, anna)
    instanz.refresh_from_db()
    assert instanz.status == S.RESERVIERT
    letzte = Ereignis.objects.order_by("-pk").first().pk
    services.vorgang_loeschen(instanz, von=mama)
    instanz.refresh_from_db()
    assert instanz.status == S.STORNIERT and instanz.geloescht_am is not None
    assert instanz.geloescht_von == mama
    assert set(Ereignis.objects.filter(pk__gt=letzte).values_list("typ_id", flat=True)) <= {
        events.GELOESCHT
    }
    assert not Interesse.objects.filter(instanz=instanz, status=InteresseStatus.AKTIV).exists()
    assert not Buchung.objects.exists()


def test_gemeldete_karte_schliesst_die_meldung(anlegen, anna, mama):
    instanz = gemeldet(anlegen, anna)
    services.vorgang_loeschen(instanz, von=mama)
    instanz.refresh_from_db()
    assert instanz.status == S.STORNIERT
    meldung = Meldung.objects.get(instanz=instanz)
    assert meldung.status not in ("offen", "rueckfrage")
    assert meldung.nachweis_geloescht_am is not None


def test_benachrichtigungen_zum_vorgang_verschwinden(anlegen, anna, mama):
    instanz = gemeldet(anlegen, anna)
    ereignis = Ereignis.objects.filter(typ_id=events.GEMELDET, kind=anna).order_by("-pk").first()
    karte = Benachrichtigung.objects.create(
        empfaenger=mama, ereignis=ereignis, titel="Titel", text="Text", link="/eltern/meldungen/"
    )
    assert [e.pk for e in benachrichtigung_selectors.liste_mit_zustand(mama)] == [karte.pk]
    assert benachrichtigung_selectors.offene_anzahl(mama) == 1
    assert benachrichtigung_selectors.ungelesen(mama) == 1
    services.vorgang_loeschen(instanz, von=mama)
    assert benachrichtigung_selectors.liste_mit_zustand(mama) == []
    assert benachrichtigung_selectors.offene_anzahl(mama) == 0
    assert benachrichtigung_selectors.ungelesen(mama) == 0


# --- Überall ausgeblendet ---------------------------------------------------------------------


def test_nicht_mehr_in_meldungen_kind_wochenplan_und_heute_erledigt(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    eltern = eltern_client_neu(mama)
    kind = kind_client_neu(anna)
    meldungen = reverse("aufgaben:entscheidungen")
    woche = reverse("aufgaben:wochenplan")
    assert TITEL in eltern.get(meldungen).content.decode()
    assert TITEL in kind.get(reverse("aufgaben:kind")).content.decode()
    assert TITEL in eltern.get(woche).content.decode()
    assert TITEL in eltern.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert services.heute_erledigt().count() == 1

    services.vorgang_loeschen(instanz, von=mama)

    for client, url in (
        (eltern, meldungen),
        (kind, reverse("aufgaben:kind")),
        (eltern, woche),
        (eltern, reverse("oberflaeche:eltern_heim")),
        (kind, reverse("oberflaeche:kind_heim")),
    ):
        assert TITEL not in client.get(url).content.decode(), url
    assert services.heute_erledigt().count() == 0
    assert selectors.eltern_entscheidungen()["bestaetigt"] == []
    assert selectors.kind_eigene(anna) == []
    assert selectors.laufende_instanzen().count() == 0
    assert selectors.zahlen_je_kind([anna], zeit.jetzt() - timedelta(days=2), zeit.jetzt()) == {}
    assert punkte_selectors.aufgaben_anzahl(anna, zeit.heute(), zeit.heute()) == 0
    assert not AufgabenInstanz.objects.filter(pk=instanz.pk).exists()
    assert AufgabenInstanz.alle.filter(pk=instanz.pk).exists()


def test_zuletzt_bestaetigt_und_ablehnen_alle_abschnitte(anlegen, anna, mama):
    konflikt = anlegen(status=S.KONFLIKT)
    gemeldete = gemeldet(anlegen, anna)
    reserviert = anlegen(status=S.RESERVIERT, kind=anna, reserviert_bis=lok(2030, 1, 1))
    for i in (konflikt, gemeldete, reserviert):
        services.vorgang_loeschen(i, von=mama)
    daten = selectors.eltern_entscheidungen()
    assert daten["konflikte"] == [] and daten["meldungen"] == []
    assert daten["reserviert"] == [] and daten["bestaetigt"] == []
    assert selectors.offene_entscheidungen_anzahl() == 0


# --- Idempotenz, Rechte -----------------------------------------------------------------------


def test_zweimal_loeschen_ist_ok_ohne_doppelte_gegenbuchung(anlegen, anna, mama, vorher):
    instanz = bestaetigt(anlegen, anna, mama, bonus=3)
    erste = services.vorgang_loeschen(instanz, von=mama)
    anzahl, audit = Buchung.objects.count(), AuditEintrag.objects.count()
    zweite = services.vorgang_loeschen(instanz, von=mama)
    assert zweite.geloescht_am == erste.geloescht_am
    assert Buchung.objects.count() == anzahl
    assert AuditEintrag.objects.count() == audit
    assert konto(anna) == vorher


def test_audit_eintrag_geloescht(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    services.vorgang_loeschen(instanz, von=mama)
    eintrag = AuditEintrag.objects.get(aktion="aufgabe.geloescht")
    assert eintrag.details["punkte"] == 5


def test_kind_darf_nicht_loeschen(anlegen, anna):
    instanz = anlegen(status=S.BESTAETIGT, kind=anna)
    with pytest.raises(services.NichtErlaubt):
        services.vorgang_loeschen(instanz, von=anna)
    instanz.refresh_from_db()
    assert instanz.geloescht_am is None


def test_generator_erzeugt_geloeschten_plantag_nicht_neu(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    services.vorgang_loeschen(instanz, von=mama)
    aufgabe = instanz.aufgabe
    services.instanzen_erzeugen(jetzt=zeit.jetzt(), aufgaben=Aufgabe.objects.filter(pk=aufgabe.pk))
    assert AufgabenInstanz.alle.filter(aufgabe=aufgabe).count() == 1


# --- Ansichten --------------------------------------------------------------------------------


def url_loeschen(instanz):
    return reverse("aufgaben:vorgang_loeschen", args=[instanz.pk])


def test_post_loescht_htmx_und_redirect(anlegen, anna, mama, vorher):
    eltern = eltern_client_neu(mama)
    erste = bestaetigt(anlegen, anna, mama)
    antwort = eltern.post(url_loeschen(erste), **HTMX)
    assert antwort.status_code == 200
    assert TITEL not in antwort.content.decode()
    zweite = bestaetigt(anlegen, anna, mama)
    antwort = eltern.post(url_loeschen(zweite))
    assert antwort.status_code == 302 and antwort["Location"] == reverse("aufgaben:entscheidungen")
    # wiederholter Klick (zweiter Tab): kein Fehler, keine doppelte Buchung
    anzahl = Buchung.objects.count()
    assert eltern.post(url_loeschen(zweite)).status_code == 302
    assert Buchung.objects.count() == anzahl
    assert konto(anna) == vorher


def test_get_ist_405_und_frage_seite_nur_fuer_eltern(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    eltern = eltern_client_neu(mama)
    assert eltern.get(url_loeschen(instanz)).status_code == 405
    frage = eltern.get(reverse("aufgaben:vorgang_loeschen_frage", args=[instanz.pk]))
    assert frage.status_code == 200
    html = frage.content.decode()
    assert "Wirklich löschen?" in html and url_loeschen(instanz) in html
    kind = kind_client_neu(anna)
    assert (
        kind.get(reverse("aufgaben:vorgang_loeschen_frage", args=[instanz.pk])).status_code == 403
    )


def test_kind_bekommt_403_und_nichts_passiert(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    antwort = kind_client_neu(anna).post(url_loeschen(instanz))
    assert antwort.status_code == 403
    instanz.refresh_from_db()
    assert instanz.geloescht_am is None


def test_ohne_anmeldung_wird_umgeleitet(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    assert Client().post(url_loeschen(instanz)).status_code in (302, 403)
    instanz.refresh_from_db()
    assert instanz.geloescht_am is None


def test_csrf_wird_geprueft(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    client = Client(enforce_csrf_checks=True)
    eltern_anmelden(client, mama)
    assert client.post(url_loeschen(instanz)).status_code == 403
    instanz.refresh_from_db()
    assert instanz.geloescht_am is None


def test_meldungen_seite_hat_loeschen_knopf_mit_dialog(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    html = eltern_client_neu(mama).get(reverse("aufgaben:entscheidungen")).content.decode()
    assert f'data-knopf-dialog="vorgang-dialog-{instanz.pk}"' in html
    assert f'id="vorgang-dialog-{instanz.pk}"' in html
    assert "#i-x-kreis" in html and "knopf--gefahr" in html
    assert "Die Punkte werden abgezogen und der Eintrag verschwindet überall." in html
    assert "onclick" not in html.split('id="entscheidungen"')[1]  # CSP: kein Inline-JS


# --- Wochenplan -------------------------------------------------------------------------------


def woche_html(client):
    return client.get(reverse("aufgaben:wochenplan")).content.decode()


def test_wochenplan_kreuz_an_bestaetigter_karte_loescht_den_vorgang(anlegen, anna, mama, vorher):
    eltern = eltern_client_neu(mama)
    instanz = bestaetigt(anlegen, anna, mama)
    url = reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])
    html = woche_html(eltern)
    assert f'data-loeschen="{url}"' in html and 'data-vorgang="1"' in html
    assert "Ganze Serie beenden" in html  # Dialog kennt beide Wege

    antwort = eltern.post(url, {"modus": "tag"}, **HTMX)
    assert antwort.status_code == 200
    instanz.refresh_from_db()
    assert instanz.geloescht_am is not None
    assert netto(instanz) == (0, 0) and konto(anna) == vorher
    assert f'data-id="{instanz.pk}"' not in woche_html(eltern)
    assert instanz.aufgabe.status == Status.BEENDET  # einmalige Aufgabe endet mit ihrer Karte


def test_wochenplan_serie_nur_diese_karte_loeschen(mama, anna):
    aufgabe = Aufgabe.objects.create(
        titel=TITEL,
        punkte=5,
        erstellt_von=mama,
        start_datum=date(2026, 10, 1),
        wiederholungsart=wiederholung.WOECHENTLICH,
        wochentage=wiederholung.maske_aus_tagen(range(7)),
        freigabeart="eltern",
    )
    heute = zeit.heute()
    instanz = AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        plan_datum=heute,
        faellig_am=heute,
        titel_snapshot=TITEL,
        punkte_snapshot=5,
        freigabeart_snapshot="eltern",
        status=S.RESERVIERT,
        kind=anna,
        reserviert_bis=lok(2030, 1, 1),
    )
    services.erledigt_melden(instanz, anna)
    instanz.refresh_from_db()
    services.bestaetigen(instanz, von=mama)
    eltern = eltern_client_neu(mama)
    assert 'data-serie="1" data-vorgang="1"' in woche_html(eltern)

    # nur diese Karte: die Serie läuft weiter
    wochenplan.loeschen(instanz.pk, "tag", von=mama)
    aufgabe.refresh_from_db()
    assert aufgabe.status == Status.AKTIV
    assert netto(instanz) == (0, 0)


def test_wochenplan_ganze_serie_beenden_modus(mama, anna):
    aufgabe = Aufgabe.objects.create(
        titel=TITEL,
        punkte=5,
        erstellt_von=mama,
        start_datum=date(2026, 10, 1),
        wiederholungsart=wiederholung.WOECHENTLICH,
        wochentage=wiederholung.maske_aus_tagen(range(7)),
        freigabeart="eltern",
    )
    instanz = AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        plan_datum=zeit.heute(),
        faellig_am=zeit.heute(),
        titel_snapshot=TITEL,
        punkte_snapshot=5,
        freigabeart_snapshot="eltern",
        status=S.BESTAETIGT,
        kind=anna,
    )
    wochenplan.loeschen(instanz.pk, "serie", von=mama)
    aufgabe.refresh_from_db()
    assert aufgabe.status == Status.BEENDET
    assert AufgabenInstanz.alle.get(pk=instanz.pk).geloescht_am is not None


def test_wochenplan_offene_karte_behaelt_altes_verhalten(anlegen, mama):
    instanz = anlegen()
    antwort = eltern_client_neu(mama).post(
        reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk]), {"modus": "tag"}, **HTMX
    )
    assert antwort.status_code == 200
    instanz = AufgabenInstanz.alle.get(pk=instanz.pk)
    assert instanz.ausgelassen_am is not None and instanz.geloescht_am is None


def test_wochenplan_bestaetigungsseite_ohne_js_fuer_vorgang(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    antwort = eltern_client_neu(mama).get(
        reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])
    )
    assert antwort.status_code == 200
    assert "Die Punkte werden abgezogen und der Eintrag verschwindet überall." in (
        antwort.content.decode()
    )


# --- Review-Nachbesserungen -------------------------------------------------------------------


def _popup(kind, typ, daten):
    ereignis = ereignisse.veroeffentlichen(typ, kind=kind, daten=daten)
    karte = Benachrichtigung.objects.create(
        empfaenger=kind, ereignis=ereignis, titel="T", text="X", link=""
    )
    return Popup.objects.create(empfaenger=kind, benachrichtigung=karte, art=typ, titel="T")


def test_serienbonus_popup_ohne_instanz_id_verschwindet_nach_loeschen(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    bonus = punkte.buchen(
        anna,
        Art.SERIENBONUS,
        2,
        schluessel=f"aufgabe:{instanz.pk}:serienbonus:0",
        quelle_modul="aufgaben",
        referenz=instanz,
        von=mama,
    )
    popup = _popup(anna, "serienbonus.gebucht", {"buchung": bonus.pk, "punkte": 2})
    fremd = _popup(anna, "serienbonus.gebucht", {"buchung": 999999, "punkte": 1})
    assert popup in benachrichtigung_selectors.ungesehene_popups(anna)
    services.vorgang_loeschen(instanz, von=mama)
    offen = benachrichtigung_selectors.ungesehene_popups(anna)
    assert popup not in offen and fremd in offen
    popup.refresh_from_db()
    assert popup.gesehen_am is not None  # auch als gesehen markiert (Punkt 4)


def test_popups_des_kindes_zum_vorgang_gelten_als_gesehen(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    anderer = bestaetigt(anlegen, anna, mama, bonus=0)
    meins = _popup(anna, events.NACHBESSERN, {"instanz_id": instanz.pk})
    anderes = _popup(anna, events.NACHBESSERN, {"instanz_id": anderer.pk})
    services.vorgang_loeschen(instanz, von=mama)
    meins.refresh_from_db()
    anderes.refresh_from_db()
    assert meins.gesehen_am is not None and anderes.gesehen_am is None


def test_einmalige_aufgabe_wird_auf_beiden_wegen_beendet(anlegen, anna, mama):
    ueber_meldungen = bestaetigt(anlegen, anna, mama)
    services.vorgang_loeschen(ueber_meldungen, von=mama)
    assert Aufgabe.objects.get(pk=ueber_meldungen.aufgabe_id).status == Status.BEENDET
    ueber_wochenplan = bestaetigt(anlegen, anna, mama)
    wochenplan.loeschen(ueber_wochenplan.pk, "tag", von=mama)
    assert Aufgabe.objects.get(pk=ueber_wochenplan.aufgabe_id).status == Status.BEENDET


def test_schnellknopf_aufgabe_wird_beim_loeschen_nicht_beendet(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    Aufgabe.objects.filter(pk=instanz.aufgabe_id).update(wiederholungsart=wiederholung.BEI_BEDARF)
    services.vorgang_loeschen(instanz, von=mama)
    assert Aufgabe.objects.get(pk=instanz.aufgabe_id).status == Status.AKTIV


def test_serie_wird_beim_einzelnen_loeschen_nicht_beendet(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama, bonus=0)
    Aufgabe.objects.filter(pk=instanz.aufgabe_id).update(
        wiederholungsart=wiederholung.WOECHENTLICH,
        wochentage=wiederholung.maske_aus_tagen(range(7)),
    )
    services.vorgang_loeschen(instanz, von=mama)
    assert Aufgabe.objects.get(pk=instanz.aufgabe_id).status == Status.AKTIV


def test_ablauf_race_geloeschte_instanz_wird_zum_ablauffehler(anlegen, anna, mama):
    from apps.aufgaben.zustand import AblaufFehler, UngueltigerUebergang

    instanz = gemeldet(anlegen, anna)
    services.vorgang_loeschen(instanz, von=mama)  # zwischenzeitlich gelöscht (Zeile bleibt)
    with pytest.raises(UngueltigerUebergang) as fehler:
        services.bestaetigen(instanz, von=mama)
    assert isinstance(fehler.value, AblaufFehler)
    with pytest.raises(AblaufFehler):
        services.ablehnen(instanz, von=mama)


def test_wochenplan_veralteter_dialog_gibt_409_und_aendert_nichts(anlegen, anna, mama):
    instanz = anlegen()  # offen: Weg "einzeln" (Karte auslassen)
    eltern = eltern_client_neu(mama)
    url = reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])
    antwort = eltern.post(url, {"modus": "tag", "art": "vorgang"}, **HTMX)
    assert antwort.status_code == 409
    assert "Die Karte hat sich geändert, bitte neu laden." in antwort.content.decode()
    assert AufgabenInstanz.objects.filter(pk=instanz.pk).exists()
    assert AufgabenInstanz.alle.get(pk=instanz.pk).ausgelassen_am is None
    # passender Weg klappt; ohne art (alte Clients) auch
    assert eltern.post(url, {"modus": "tag", "art": "einzeln"}, **HTMX).status_code == 200


def test_wochenplan_dialog_schickt_art_mit_und_fallback_seite_traegt_sie(anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    eltern = eltern_client_neu(mama)
    seite = eltern.get(reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])).content.decode()
    assert 'name="art" value="vorgang"' in seite
    assert 'name="art"' in woche_html(eltern)
    assert (
        'art: form.querySelector("[name=art]")'
        in (WURZEL / "static" / "js" / "wochenplan.js").read_text()
    )
    # Fallback-POST mit passender Art löscht
    url = reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])
    assert eltern.post(url, {"modus": "tag", "art": "vorgang"}).status_code in (200, 302)
    assert AufgabenInstanz.alle.get(pk=instanz.pk).geloescht_am is not None


def test_aktivitaet_neuaufbau_ueberspringt_geloeschte_vorgaenge(anlegen, anna, mama):
    from apps.spielregeln import services as spielregeln
    from apps.spielregeln.models import Aktivitaet

    behalten = bestaetigt(anlegen, anna, mama, bonus=0)
    weg = bestaetigt(anlegen, anna, mama, bonus=0)
    services.vorgang_loeschen(weg, von=mama)
    assert Ereignis.objects.filter(typ_id=events.GELOESCHT, daten__instanz_id=weg.pk).exists()
    Aktivitaet.objects.filter(modul="aufgaben").delete()
    spielregeln.aktivitaeten_nachtragen()
    refs = set(Aktivitaet.objects.filter(modul="aufgaben").values_list("referenz", flat=True))
    assert refs == {str(behalten.pk)}


def test_je_kind_aufteilen_nimmt_geloeschte_instanzen_mit(mama, anna):
    from apps.konten import services as konten

    konten.kind_anlegen("Ben", PIN, akzentfarben=["#4fa0ff"])
    aufgabe = Aufgabe.objects.create(
        titel=TITEL,
        punkte=5,
        erstellt_von=mama,
        start_datum=date(2026, 10, 1),
        wiederholungsart=wiederholung.WOECHENTLICH,
        wochentage=wiederholung.maske_aus_tagen(range(7)),
        freigabeart="eltern",
    )
    letztes = [k for k in services.konten_selectors.aktive_kinder()][-1]
    instanz = AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        plan_datum=date(2026, 11, 2),
        faellig_am=date(2026, 11, 2),
        titel_snapshot=TITEL,
        punkte_snapshot=5,
        freigabeart_snapshot="eltern",
        status=S.BESTAETIGT,
        kind=letztes,
    )
    services.vorgang_loeschen(instanz, von=mama)
    services.je_kind_aufteilen(aufgabe, von=mama)
    kopie = AufgabenInstanz.alle.get(pk=instanz.pk).aufgabe
    assert kopie.pk != aufgabe.pk and kopie.zugewiesen_an_id == letztes.pk


# --- Layout (CSS / Template) --------------------------------------------------------------------


def css(name):
    return (WURZEL / "static" / "css" / name).read_text()


def test_wochenplan_titel_bricht_nur_an_wortgrenzen_kreuz_absolut():
    text = css("aufgaben.css")
    assert "flex: 1 1 0" not in text.split("Löschen-Kreuz an der Wochenplan-Karte")[1]
    assert ".wochenplan__karte { position: relative; }" in text
    kreuz = next(z for z in text.splitlines() if z.startswith(".wochenplan__x {"))
    assert "position: absolute" in kreuz and "top:" in kreuz
    titel = next(
        z
        for z in text.splitlines()
        if z.endswith(
            "> strong { flex: 0 1 auto; min-width: 0; overflow-wrap: break-word; hyphens: auto; }"
        )
    )
    assert "anywhere" not in titel
    assert "padding-inline-end" in text


def test_schnellzugriff_kachel_volle_breite(eltern_client):
    text = css("oberflaeche.css")
    assert 'data-kachel="oberflaeche.eltern_schnellzugriff"] { grid-column: 1 / -1; }' in text
    # die Regel steht im Block ab 48rem (wie die Schnell-Knöpfe)
    vor_regel = text.split('eltern_schnellzugriff"] { grid-column')[0]
    assert vor_regel.rsplit("@media", 1)[1].startswith(" (min-width: 48rem)")
    assert 'eltern_schnellknoepfe"],' in vor_regel
    html = eltern_client.get(reverse("oberflaeche:eltern_heim")).content.decode()
    assert 'data-kachel="oberflaeche.eltern_schnellzugriff"' in html
    kachel = html.split('data-kachel="oberflaeche.eltern_schnellzugriff"')[1].split("</section>")[0]
    assert kachel.count('class="reihe"') == 1  # alle Knöpfe in einer Reihe (flex-wrap)
