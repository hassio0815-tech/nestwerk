"""UI-Runde P5: Meldungen abschließen, Aktionen in Benachrichtigungen, Wochenplan löschen."""

from datetime import date, datetime, time, timedelta
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
    Status,
)
from apps.benachrichtigung import selectors as benachrichtigung_selectors
from apps.benachrichtigung.models import Benachrichtigung
from apps.ereignisse.models import Ereignis
from apps.kern.models import Einstellung
from apps.konten import services as konten
from apps.konten.tests.conftest import eltern_anmelden
from apps.punkte.models import Buchung

S = InstanzStatus
BERLIN = ZoneInfo("Europe/Berlin")
HTMX = {"HTTP_HX_REQUEST": "true"}


def lok(*args):
    return datetime(*args, tzinfo=BERLIN)


@pytest.fixture
def anlegen(mama):
    zaehler = iter(range(1, 1000))

    def _anlegen(*, tag=date(2026, 10, 20), status=S.OFFEN, **extra):
        n = next(zaehler)
        aufgabe = Aufgabe.objects.create(
            titel=f"Aufgabe {n}",
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


def serie(mama, **extra):
    werte = {
        "titel": "Bad putzen",
        "punkte": 8,
        "erstellt_von": mama,
        "start_datum": date(2026, 10, 1),
        "wiederholungsart": wiederholung.WOECHENTLICH,
        "intervall_tage": None,
        "wochentage": wiederholung.maske_aus_tagen(range(7)),
        "freigabeart": "eltern",
    }
    werte.update(extra)
    return Aufgabe.objects.create(**werte)


def gemeldet(anlegen, anna):
    instanz = anlegen(status=S.RESERVIERT, kind=anna, reserviert_bis=lok(2030, 1, 1))
    services.erledigt_melden(instanz, anna)
    instanz.refresh_from_db()
    assert instanz.status == S.GEMELDET
    return instanz


def bestaetigt(anlegen, anna, mama):
    instanz = gemeldet(anlegen, anna)
    services.bestaetigen(instanz, von=mama)
    instanz.refresh_from_db()
    assert instanz.status == S.BESTAETIGT
    return instanz


def punkte_stand():
    return list(Buchung.objects.order_by("pk").values_list("pk", "guthaben_delta"))


# --- (a) Meldungen: Abschließen ---------------------------------------------------------------


def test_abschliessen_blendet_aus_und_laesst_punkte(eltern_client, anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    vorher = punkte_stand()
    seite = eltern_client.get(reverse("aufgaben:entscheidungen")).content.decode()
    assert f'id="instanz-{instanz.pk}"' in seite
    assert reverse("aufgaben:abschliessen", args=[instanz.pk]) in seite

    antwort = eltern_client.post(reverse("aufgaben:abschliessen", args=[instanz.pk]), **HTMX)
    assert antwort.status_code == 200
    assert f'id="instanz-{instanz.pk}"' not in antwort.content.decode()
    instanz.refresh_from_db()
    assert instanz.status == S.BESTAETIGT
    assert instanz.meldung_abgeschlossen_am is not None
    assert punkte_stand() == vorher
    nachher = eltern_client.get(reverse("aufgaben:entscheidungen")).content.decode()
    assert f'id="instanz-{instanz.pk}"' not in nachher


def test_abschliessen_ist_idempotent(eltern_client, anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    url = reverse("aufgaben:abschliessen", args=[instanz.pk])
    eltern_client.post(url)
    erste = AufgabenInstanz.objects.get(pk=instanz.pk).meldung_abgeschlossen_am
    assert eltern_client.post(url).status_code == 200
    assert AufgabenInstanz.objects.get(pk=instanz.pk).meldung_abgeschlossen_am == erste


def test_nach_abschliessen_kein_bonus_und_keine_korrektur(eltern_client, anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    eltern_client.post(reverse("aufgaben:abschliessen", args=[instanz.pk]))
    vorher = punkte_stand()
    bonus = eltern_client.post(
        reverse("aufgaben:sonderpunkte", args=[instanz.pk]),
        {"sonderpunkte": "2", "begruendung": "toll"},
    )
    korrektur = eltern_client.post(
        reverse("aufgaben:korrigieren", args=[instanz.pk]), {"begruendung": "doch nicht"}
    )
    assert "abgeschlossen" in bonus.content.decode()
    assert "abgeschlossen" in korrektur.content.decode()
    assert punkte_stand() == vorher
    assert AufgabenInstanz.objects.get(pk=instanz.pk).status == S.BESTAETIGT


def test_abschliessen_nur_bestaetigte(eltern_client, anlegen, anna):
    instanz = gemeldet(anlegen, anna)
    antwort = eltern_client.post(reverse("aufgaben:abschliessen", args=[instanz.pk]))
    assert "Nur bestätigte" in antwort.content.decode()
    assert AufgabenInstanz.objects.get(pk=instanz.pk).meldung_abgeschlossen_am is None


def test_alle_abschliessen(eltern_client, anlegen, anna, mama):
    eins = bestaetigt(anlegen, anna, mama)
    zwei = bestaetigt(anlegen, anna, mama)
    vorher = punkte_stand()
    antwort = eltern_client.post(reverse("aufgaben:alle_abschliessen"), **HTMX)
    assert antwort.status_code == 200
    for instanz in (eins, zwei):
        instanz.refresh_from_db()
        assert instanz.meldung_abgeschlossen_am is not None
        assert f'id="instanz-{instanz.pk}"' not in antwort.content.decode()
    assert punkte_stand() == vorher


@pytest.mark.parametrize("name", ["abschliessen", "alle_abschliessen"])
def test_abschliessen_kind_und_anonym_abgewiesen(client, kind_client, anlegen, anna, mama, name):
    instanz = bestaetigt(anlegen, anna, mama)
    args = [instanz.pk] if name == "abschliessen" else []
    antwort = kind_client.post(reverse(f"aufgaben:{name}", args=args))
    assert antwort.status_code in (302, 403)
    assert AufgabenInstanz.objects.get(pk=instanz.pk).meldung_abgeschlossen_am is None
    kind_client.logout()
    assert client.post(reverse(f"aufgaben:{name}", args=args)).status_code in (302, 403)


def test_abschliessen_nur_per_post(eltern_client, anlegen, anna, mama):
    instanz = bestaetigt(anlegen, anna, mama)
    antwort = eltern_client.get(reverse("aufgaben:abschliessen", args=[instanz.pk]))
    assert antwort.status_code == 405


# --- (b) Benachrichtigungen mit Aktionen ------------------------------------------------------


def benachricht(ereignis_typ, mama, **filter_):
    ereignis = Ereignis.objects.filter(typ_id=ereignis_typ, **filter_).order_by("-pk").first()
    return Benachrichtigung.objects.create(
        empfaenger=mama, ereignis=ereignis, titel="Titel", text="Text", link="/eltern/meldungen/"
    )


def aktion_url(eintrag, slug):
    return reverse("benachrichtigung:aktion", args=[eintrag.pk, slug])


def mitbewerben_an():
    Einstellung.objects.update_or_create(
        schluessel="aufgaben.mitbewerben_erlaubt",
        defaults={"wert": True, "modul": "aufgaben"},
    )


def test_gemeldet_karte_hat_bestaetigen_und_ablehnen(eltern_client, anlegen, anna, mama):
    gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    seite = eltern_client.get(reverse("benachrichtigung:liste")).content.decode()
    assert aktion_url(eintrag, "bestaetigen") in seite
    assert aktion_url(eintrag, "ablehnen") in seite


def test_bestaetigen_aus_karte_bucht_und_redirect(eltern_client, anlegen, anna, mama):
    instanz = gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    antwort = eltern_client.post(aktion_url(eintrag, "bestaetigen"))
    assert antwort.status_code == 302
    assert antwort["Location"] == reverse("benachrichtigung:liste")
    instanz.refresh_from_db()
    assert instanz.status == S.BESTAETIGT
    assert Buchung.objects.filter(guthaben_delta=5).count() == 1
    eintrag.refresh_from_db()
    assert eintrag.gelesen_am is not None


def test_ablehnen_aus_karte_ohne_punkte(eltern_client, anlegen, anna, mama):
    instanz = gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    antwort = eltern_client.post(aktion_url(eintrag, "ablehnen"), **HTMX)
    assert antwort.status_code == 200
    instanz.refresh_from_db()
    assert instanz.status == S.ABGELEHNT
    assert not Buchung.objects.exists()


def test_erledigte_karte_grau_ohne_aktionen_und_nicht_ausfuehrbar(
    eltern_client, anlegen, anna, mama
):
    instanz = gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    services.bestaetigen(instanz, von=mama)  # inzwischen anderswo entschieden
    vorher = punkte_stand()
    seite = eltern_client.get(reverse("benachrichtigung:liste")).content.decode()
    assert "benachrichtigung--erledigt" in seite
    assert "Erledigt" in seite
    assert aktion_url(eintrag, "bestaetigen") not in seite
    assert aktion_url(eintrag, "ablehnen") not in seite
    antwort = eltern_client.post(aktion_url(eintrag, "ablehnen"))
    assert antwort.status_code == 409
    assert punkte_stand() == vorher
    assert AufgabenInstanz.objects.get(pk=instanz.pk).status == S.BESTAETIGT


def test_unbekannte_aktion_wird_abgelehnt(eltern_client, anlegen, anna, mama):
    gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    assert eltern_client.post(aktion_url(eintrag, "erlauben")).status_code == 409


def test_fremde_benachrichtigung_ist_404(eltern_client, anlegen, anna, mama):
    gemeldet(anlegen, anna)
    papa = konten.eltern_anlegen("Papa", rolle_label="papa")
    eintrag = benachricht(events.GEMELDET, papa)
    assert eltern_client.post(aktion_url(eintrag, "bestaetigen")).status_code == 404
    assert AufgabenInstanz.objects.get().status == S.GEMELDET


def test_aktion_kind_und_anonym_abgewiesen(client, kind_client, anlegen, anna, mama):
    gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    assert kind_client.post(aktion_url(eintrag, "bestaetigen")).status_code in (302, 403)
    kind_client.logout()
    assert client.post(aktion_url(eintrag, "bestaetigen")).status_code in (302, 403)
    assert AufgabenInstanz.objects.get().status == S.GEMELDET


def test_aktion_nur_per_post(eltern_client, anlegen, anna, mama):
    gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    assert eltern_client.get(aktion_url(eintrag, "bestaetigen")).status_code == 405


def test_aktion_verlangt_csrf(anlegen, anna, mama):
    gemeldet(anlegen, anna)
    eintrag = benachricht(events.GEMELDET, mama)
    strikt = Client(enforce_csrf_checks=True)
    eltern_anmelden(strikt, mama)
    assert strikt.post(aktion_url(eintrag, "bestaetigen")).status_code == 403
    assert AufgabenInstanz.objects.get().status == S.GEMELDET


def test_interesse_ablehnen_loest_reservierung(eltern_client, anlegen, anna, mama):
    instanz = anlegen()
    services.interesse_zeigen(instanz, anna)
    eintrag = benachricht(events.INTERESSE, mama)
    seite = eltern_client.get(reverse("benachrichtigung:liste")).content.decode()
    assert aktion_url(eintrag, "erlauben") in seite
    assert aktion_url(eintrag, "ablehnen") in seite

    eltern_client.post(aktion_url(eintrag, "ablehnen"))
    instanz.refresh_from_db()
    assert (instanz.status, instanz.kind_id) == (S.OFFEN, None)
    assert not Buchung.objects.exists()
    # nun erledigt: weder erlauben noch ablehnen
    assert eltern_client.post(aktion_url(eintrag, "erlauben")).status_code == 409


def test_interesse_erlauben_laesst_reservierung(eltern_client, anlegen, anna, mama):
    instanz = anlegen()
    services.interesse_zeigen(instanz, anna)
    eintrag = benachricht(events.INTERESSE, mama)
    assert eltern_client.post(aktion_url(eintrag, "erlauben")).status_code == 302
    instanz.refresh_from_db()
    assert (instanz.status, instanz.kind_id) == (S.RESERVIERT, anna.pk)
    eintrag.refresh_from_db()
    assert eintrag.gelesen_am is not None
    erste = benachrichtigung_selectors.liste_mit_zustand(mama)[0]
    assert erste.offen is False and erste.erledigt is True


def test_konflikt_erlauben_teilt_zu(eltern_client, anlegen, anna, ben, mama):
    mitbewerben_an()
    instanz = anlegen()
    services.interesse_zeigen(instanz, anna)
    services.interesse_zeigen(instanz, ben)
    assert AufgabenInstanz.objects.get().status == S.KONFLIKT
    eintrag = benachricht(events.KONFLIKT, mama)  # letzter Wunsch: Ben
    seite = eltern_client.get(reverse("benachrichtigung:liste")).content.decode()
    assert aktion_url(eintrag, "erlauben") in seite
    assert aktion_url(eintrag, "ablehnen") not in seite
    eltern_client.post(aktion_url(eintrag, "erlauben"))
    instanz.refresh_from_db()
    assert (instanz.status, instanz.kind_id) == (S.RESERVIERT, ben.pk)
    assert not Interesse.objects.filter(status=InteresseStatus.AKTIV).exists()


def test_andere_arten_nur_oeffnen(eltern_client, anlegen, anna, mama):
    bestaetigt(anlegen, anna, mama)
    eintrag = benachricht(events.ERLEDIGT, mama)
    erste = benachrichtigung_selectors.liste_mit_zustand(mama)[0]
    assert erste.aktionen == ()
    assert erste.offen is True  # ungelesen = offen
    assert benachrichtigung_selectors.offene_anzahl(mama) == 1
    eltern_client.post(reverse("benachrichtigung:gelesen", args=[eintrag.pk]))
    assert benachrichtigung_selectors.offene_anzahl(mama) == 0


def test_offene_zuerst_erledigte_danach(anlegen, anna, mama):
    alt = gemeldet(anlegen, anna)
    alte_karte = benachricht(events.GEMELDET, mama)
    services.bestaetigen(alt, von=mama)  # erledigt
    gemeldet(anlegen, anna)
    neue_karte = benachricht(events.GEMELDET, mama)
    Benachrichtigung.objects.filter(pk=alte_karte.pk).update(
        erstellt_am=neue_karte.erstellt_am + timedelta(hours=1)
    )
    liste = benachrichtigung_selectors.liste_mit_zustand(mama)
    assert [e.pk for e in liste] == [neue_karte.pk, alte_karte.pk]
    assert [e.offen for e in liste] == [True, False]


def test_reiter_zaehler_nur_offene_und_nur_wenn_positiv(eltern_client, anlegen, anna, mama):
    leer = eltern_client.get(reverse("aufgaben:wochenplan")).content.decode()
    assert 'data-offen="0"' in leer
    instanz = gemeldet(anlegen, anna)
    benachricht(events.GEMELDET, mama)
    assert 'data-offen="1"' in eltern_client.get(reverse("aufgaben:wochenplan")).content.decode()
    services.bestaetigen(instanz, von=mama)
    assert 'data-offen="0"' in eltern_client.get(reverse("aufgaben:wochenplan")).content.decode()
    teil = eltern_client.get(reverse("benachrichtigung:reiter_zaehler"), **HTMX).content.decode()
    assert 'data-offen="0"' in teil and " hidden" in teil


def test_reiter_zaehler_kind_abgewiesen(kind_client):
    antwort = kind_client.get(reverse("benachrichtigung:reiter_zaehler"))
    assert antwort.status_code in (302, 403)


# --- (c) Wochenplan: Löschen ------------------------------------------------------------------


def loeschen_url(instanz):
    return reverse("aufgaben:wochenplan_loeschen", args=[instanz.pk])


def woche_seite(client, tag=date(2026, 10, 20)):
    return client.get(reverse("aufgaben:wochenplan"), {"datum": tag.isoformat()}).content.decode()


def test_kreuz_nur_an_loeschbaren_karten(eltern_client, anlegen, anna, mama):
    frei = anlegen()
    fertig = bestaetigt(anlegen, anna, mama)
    offene_meldung = gemeldet(anlegen, anna)
    seite = woche_seite(eltern_client)
    assert f'data-loeschen="{loeschen_url(frei)}"' in seite
    assert 'aria-label="Löschen"' in seite
    assert f'data-loeschen="{loeschen_url(fertig)}"' not in seite
    assert f'data-loeschen="{loeschen_url(offene_meldung)}"' not in seite
    assert 'id="loeschen-dialog"' in seite


def test_einzelaufgabe_loeschen_ohne_punkte_und_aufgabe_beendet(eltern_client, anlegen):
    instanz = anlegen()
    antwort = eltern_client.post(loeschen_url(instanz), {"modus": "tag"}, **HTMX)
    assert antwort.status_code == 200
    instanz.refresh_from_db()
    assert instanz.status == S.STORNIERT and instanz.ausgelassen_am is not None
    assert instanz.aufgabe.status == Status.BEENDET
    assert f'data-loeschen="{loeschen_url(instanz)}"' not in woche_seite(eltern_client)
    assert not Buchung.objects.exists()


def test_nur_dieser_tag_generator_erzeugt_nicht_neu_zeitgebunden(eltern_client, mama):
    aufgabe = serie(mama, fenster_von=time(18, 0), fenster_bis=time(20, 0))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 8))
    ziel = aufgabe.instanzen.get(plan_datum=date(2026, 10, 20))
    anzahl = aufgabe.instanzen.count()
    eltern_client.post(loeschen_url(ziel), {"modus": "tag"})
    ziel.refresh_from_db()
    assert ziel.status == S.STORNIERT and ziel.ausgelassen_am is not None
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 9))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 20, 9))
    assert aufgabe.instanzen.filter(plan_datum=date(2026, 10, 20)).count() == 1
    assert aufgabe.instanzen.exclude(pk=ziel.pk).filter(status=S.OFFEN).exists()
    assert aufgabe.instanzen.count() >= anzahl
    aufgabe.refresh_from_db()
    assert aufgabe.status == Status.AKTIV
    # die ausgelassene Karte erscheint nicht mehr im Wochenplan
    assert f'data-id="{ziel.pk}"' not in woche_seite(eltern_client)


def test_nur_dieser_tag_generator_ungebunden(eltern_client, mama):
    aufgabe = serie(mama, wochentage=wiederholung.maske_aus_tagen([0]))  # montags
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 8))
    ziel = aufgabe.instanzen.get()
    wochenplan.auslassen(ziel.pk, von=mama, jetzt=lok(2026, 10, 19, 9))  # Uhr wie im Test
    assert eltern_client.get(loeschen_url(ziel)).status_code == 409  # nicht mehr löschbar
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 12))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 21, 12))
    assert aufgabe.instanzen.count() == 1  # nicht neu erzeugt
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 26, 8))
    assert aufgabe.instanzen.count() == 2  # nächster Montag kommt wieder


def test_ganze_serie_beendet_aufgabe_und_entfernt_offene(eltern_client, mama):
    aufgabe = serie(mama, fenster_von=time(18, 0), fenster_bis=time(20, 0))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 8))
    ziel = aufgabe.instanzen.get(plan_datum=date(2026, 10, 20))
    eltern_client.post(loeschen_url(ziel), {"modus": "serie"})
    aufgabe.refresh_from_db()
    assert aufgabe.status == Status.BEENDET
    assert not aufgabe.instanzen.filter(status=S.OFFEN).exists()
    vorher = aufgabe.instanzen.count()
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 21, 8))
    assert aufgabe.instanzen.count() == vorher


def test_serie_popup_bietet_beide_wege(eltern_client, mama):
    serie(mama, fenster_von=time(18, 0), fenster_bis=time(20, 0))
    services.instanzen_erzeugen(jetzt=lok(2026, 10, 19, 8))
    seite = woche_seite(eltern_client)
    assert "data-serie" in seite
    assert "Nur diesen Tag" in seite and "Ganze Serie" in seite


def test_bestaetigte_nicht_loeschbar_serverseitig(eltern_client, anlegen, anna, mama):
    fertig = bestaetigt(anlegen, anna, mama)
    vorher = punkte_stand()
    for modus in ("tag", "serie"):
        antwort = eltern_client.post(loeschen_url(fertig), {"modus": modus}, **HTMX)
        assert antwort.status_code == 409
    fertig.refresh_from_db()
    assert fertig.status == S.BESTAETIGT and fertig.ausgelassen_am is None
    assert fertig.aufgabe.status == Status.AKTIV
    assert punkte_stand() == vorher


@pytest.mark.parametrize("status", [S.GEMELDET, S.ABGELEHNT, S.STORNIERT, S.NACHBESSERN])
def test_weitere_status_nicht_loeschbar(eltern_client, anlegen, status):
    instanz = anlegen(status=status)
    assert eltern_client.post(loeschen_url(instanz), {"modus": "tag"}).status_code == 409
    instanz.refresh_from_db()
    assert instanz.status == status and instanz.ausgelassen_am is None


def test_reservierte_karte_loesen_und_ausblenden(eltern_client, anlegen, anna):
    instanz = anlegen()
    services.interesse_zeigen(instanz, anna)
    assert eltern_client.post(loeschen_url(instanz), {"modus": "tag"}).status_code == 200
    instanz.refresh_from_db()
    assert instanz.status == S.STORNIERT and instanz.ausgelassen_am is not None
    assert Ereignis.objects.filter(typ_id=events.GELOEST, kind=anna).exists()


def test_ausgelassene_nicht_beim_kind_sichtbar(anlegen, anna):
    instanz = anlegen(kind=anna, status=S.STORNIERT, abgeschlossen_am=lok(2026, 10, 20, 8))
    assert instanz in selectors.kind_eigene(anna, jetzt=lok(2026, 10, 21))
    AufgabenInstanz.objects.filter(pk=instanz.pk).update(ausgelassen_am=lok(2026, 10, 20, 9))
    assert instanz not in selectors.kind_eigene(anna, jetzt=lok(2026, 10, 21))


def test_loeschen_ohne_js_bestaetigungsseite(eltern_client, anlegen):
    instanz = anlegen()
    seite = eltern_client.get(loeschen_url(instanz), {"woche": "2026-10-19"})
    assert seite.status_code == 200
    html = seite.content.decode()
    assert "Wirklich löschen?" in html and "csrfmiddlewaretoken" in html
    assert AufgabenInstanz.objects.get().status == S.OFFEN  # GET löscht nie
    erledigt = eltern_client.post(loeschen_url(instanz), {"modus": "tag", "woche": "2026-10-19"})
    assert erledigt.status_code == 200
    assert AufgabenInstanz.objects.get().status == S.STORNIERT


def test_loeschen_kind_und_anonym_abgewiesen(client, kind_client, anlegen):
    instanz = anlegen()
    assert kind_client.post(loeschen_url(instanz), {"modus": "tag"}).status_code in (302, 403)
    assert kind_client.get(loeschen_url(instanz)).status_code in (302, 403)
    kind_client.logout()
    assert client.post(loeschen_url(instanz), {"modus": "tag"}).status_code in (302, 403)
    assert AufgabenInstanz.objects.get().status == S.OFFEN


def test_loeschen_verlangt_csrf(anlegen, mama):
    instanz = anlegen()
    strikt = Client(enforce_csrf_checks=True)
    eltern_anmelden(strikt, mama)
    assert strikt.post(loeschen_url(instanz), {"modus": "tag"}).status_code == 403
    assert AufgabenInstanz.objects.get().status == S.OFFEN


def test_unbekannter_modus(eltern_client, anlegen):
    instanz = anlegen()
    assert eltern_client.post(loeschen_url(instanz), {"modus": "alles"}).status_code == 409
    assert AufgabenInstanz.objects.get().status == S.OFFEN
