"""Wochenplan (AP14): Ansicht, Verschieben per Ziehen (HTMX) und Formular-Fallback."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.aufgaben import wiederholung, wochenplan
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.kern import zeit

BERLIN = ZoneInfo("Europe/Berlin")
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def aufgabe(mama):
    return Aufgabe.objects.create(
        titel="Tisch decken",
        punkte=5,
        erstellt_von=mama,
        start_datum=date(2026, 10, 1),
        wiederholungsart=wiederholung.EINMALIG,
    )


@pytest.fixture
def neue_instanz(mama):
    zaehler = iter(range(1, 1000))

    def anlegen(tag=date(2026, 10, 20), status=InstanzStatus.OFFEN, **extra):
        n = next(zaehler)
        aufgabe = Aufgabe.objects.create(
            titel=f"Aufgabe {n}",
            punkte=5,
            erstellt_von=mama,
            start_datum=date(2026, 10, 1),
            wiederholungsart=wiederholung.EINMALIG,
        )
        werte = {
            "aufgabe": aufgabe,
            "plan_datum": tag,
            "faellig_am": tag,
            "titel_snapshot": aufgabe.titel,
            "punkte_snapshot": 5,
            "freigabeart_snapshot": aufgabe.freigabeart,
            "status": status,
        }
        werte.update(extra)
        return AufgabenInstanz.objects.create(**werte)

    return anlegen


def verschieben_url(inst):
    return reverse("aufgaben:wochenplan_verschieben", args=[inst.pk])


# --- Zugriff ---------------------------------------------------------------------------------


def test_kind_bekommt_403(kind_client, neue_instanz):
    inst = neue_instanz()
    assert kind_client.get(reverse("aufgaben:wochenplan")).status_code == 403
    antwort = kind_client.post(verschieben_url(inst), {"datum": "2026-10-21"})
    assert antwort.status_code == 403
    inst.refresh_from_db()
    assert inst.faellig_am == date(2026, 10, 20)


# --- Ansicht ---------------------------------------------------------------------------------


def test_ansicht_zeigt_sieben_tage_und_karten(eltern_client, neue_instanz):
    neue_instanz(date(2026, 10, 19))  # Montag
    neue_instanz(date(2026, 10, 25))  # Sonntag
    neue_instanz(date(2026, 10, 26))  # nächste Woche
    antwort = eltern_client.get(reverse("aufgaben:wochenplan"), {"datum": "2026-10-22"})
    assert antwort.status_code == 200
    tage = antwort.context["tage"]
    assert [t["datum"] for t in tage][0] == date(2026, 10, 19)
    assert [t["datum"] for t in tage][-1] == date(2026, 10, 25)
    assert len(tage[0]["instanzen"]) == 1
    assert len(tage[6]["instanzen"]) == 1
    assert sum(len(t["instanzen"]) for t in tage) == 2
    html = antwort.content.decode()
    assert "data-wochenplan" in html
    assert "Sortable.min.js" in html


def test_navigation_ungueltiges_datum_faellt_auf_heute(eltern_client):
    antwort = eltern_client.get(reverse("aufgaben:wochenplan"), {"datum": "quatsch"})
    assert antwort.status_code == 200
    assert antwort.context["woche"] == zeit.aktuelle_woche()


def test_htmx_liefert_nur_das_brett(eltern_client):
    antwort = eltern_client.get(reverse("aufgaben:wochenplan"), **HTMX)
    html = antwort.content.decode()
    assert 'id="wochenplan"' in html
    assert "<html" not in html


def test_gesperrte_karte_ohne_ziehen_und_formular(eltern_client, neue_instanz, ben):
    neue_instanz(status=InstanzStatus.BESTAETIGT, kind=ben)
    html = eltern_client.get(
        reverse("aufgaben:wochenplan"), {"datum": "2026-10-20"}
    ).content.decode()
    assert "wochenplan__karte--gesperrt" in html
    assert "data-beweglich" not in html
    assert "Nicht verschiebbar" in html


def test_ohne_termin_wird_angezeigt(eltern_client, neue_instanz):
    neue_instanz(tag=None)
    antwort = eltern_client.get(reverse("aufgaben:wochenplan"), {"datum": "2026-10-20"})
    assert len(antwort.context["ohne_termin"]) == 1


# --- Wochengrenzen / DST -----------------------------------------------------------------------


def test_wochengrenze_jahreswechsel_iso():
    woche = wochenplan.woche_aus_datum("2026-12-31")  # Donnerstag in KW 53
    assert woche.montag == date(2026, 12, 28)
    assert woche.sonntag == date(2027, 1, 3)
    assert woche.naechste().montag == date(2027, 1, 4)


def test_wochengrenze_zeitumstellung():
    woche = wochenplan.woche_aus_datum("2026-10-27")  # Umstellung So 25.10.2026
    assert woche.montag == date(2026, 10, 26)
    davor = wochenplan.woche_aus_datum("2026-10-25")
    assert davor.sonntag == date(2026, 10, 25)
    assert len(davor.tage()) == 7


def test_verschieben_ueber_zeitumstellung_berechnet_fenster(eltern_client, aufgabe, mama):
    aufgabe.fenster_von = time(18, 0)
    aufgabe.fenster_bis = time(20, 0)
    aufgabe.save()
    inst = AufgabenInstanz.objects.create(
        aufgabe=aufgabe,
        plan_datum=date(2026, 10, 24),
        faellig_am=date(2026, 10, 24),
        fenster_start=datetime(2026, 10, 24, 18, tzinfo=BERLIN),
        fenster_ende=datetime(2026, 10, 24, 20, tzinfo=BERLIN),
        titel_snapshot="x",
        punkte_snapshot=5,
        freigabeart_snapshot=aufgabe.freigabeart,
    )
    eltern_client.post(verschieben_url(inst), {"datum": "2026-10-26"}, **HTMX)
    inst.refresh_from_db()
    assert inst.fenster_ende.astimezone(BERLIN).time() == time(20, 0)
    assert inst.fenster_ende.astimezone(BERLIN).date() == date(2026, 10, 26)
    assert inst.plan_datum == date(2026, 10, 24)


# --- Verschieben -----------------------------------------------------------------------------


def test_ziehen_aendert_datum_und_reihenfolge(eltern_client, neue_instanz):
    a = neue_instanz(date(2026, 10, 20))
    b = neue_instanz(date(2026, 10, 21))
    c = neue_instanz(date(2026, 10, 21))
    antwort = eltern_client.post(
        verschieben_url(a),
        {"datum": "2026-10-21", "reihenfolge": f"{b.pk},{a.pk},{c.pk}", "woche": "2026-10-19"},
        **HTMX,
    )
    assert antwort.status_code == 200
    for obj in (a, b, c):
        obj.refresh_from_db()
    assert a.faellig_am == date(2026, 10, 21)
    assert a.plan_datum == date(2026, 10, 20)
    assert [b.sortierung, a.sortierung, c.sortierung] == [0, 1, 2]
    assert 'id="wochenplan"' in antwort.content.decode()


def test_formular_fallback_gleiches_ergebnis(eltern_client, neue_instanz):
    a = neue_instanz(date(2026, 10, 20))
    antwort = eltern_client.post(verschieben_url(a), {"datum": "2026-10-23"})
    assert antwort.status_code == 200
    assert "<html" in antwort.content.decode()
    a.refresh_from_db()
    assert a.faellig_am == date(2026, 10, 23)


def test_verschieben_wird_protokolliert(eltern_client, neue_instanz):
    from apps.kern.models import AuditEintrag

    a = neue_instanz(date(2026, 10, 20))
    eltern_client.post(verschieben_url(a), {"datum": "2026-10-22"})
    assert AuditEintrag.objects.filter(aktion="aufgabe.instanz_verschoben").exists()


@pytest.mark.parametrize(
    "status",
    [
        InstanzStatus.GEMELDET,
        InstanzStatus.BESTAETIGT,
        InstanzStatus.ABGELEHNT,
        InstanzStatus.NICHT_UEBERNOMMEN,
        InstanzStatus.STORNIERT,
    ],
)
def test_gesperrte_zustaende_werden_abgewiesen(eltern_client, neue_instanz, ben, status):
    a = neue_instanz(status=status, kind=ben)
    antwort = eltern_client.post(verschieben_url(a), {"datum": "2026-10-23"}, **HTMX)
    assert antwort.status_code == 409
    assert "kann nicht verschoben werden" in antwort.content.decode()
    a.refresh_from_db()
    assert a.faellig_am == date(2026, 10, 20)


def test_reservierte_darf_verschoben_werden(eltern_client, neue_instanz, ben):
    a = neue_instanz(status=InstanzStatus.RESERVIERT, kind=ben)
    eltern_client.post(verschieben_url(a), {"datum": "2026-10-23"}, **HTMX)
    a.refresh_from_db()
    assert a.faellig_am == date(2026, 10, 23)
    assert a.kind == ben


def test_ungueltiges_datum_und_unbekannte_instanz(eltern_client, neue_instanz):
    a = neue_instanz()
    assert eltern_client.post(verschieben_url(a), {"datum": "kein"}, **HTMX).status_code == 400
    assert eltern_client.post(verschieben_url(a), {}, **HTMX).status_code == 400
    antwort = eltern_client.post(
        reverse("aufgaben:wochenplan_verschieben", args=[99999]), {"datum": "2026-10-21"}, **HTMX
    )
    assert antwort.status_code == 409


def test_ungueltige_reihenfolge_abgewiesen(eltern_client, neue_instanz):
    a = neue_instanz()
    antwort = eltern_client.post(
        verschieben_url(a), {"datum": "2026-10-21", "reihenfolge": "1,x"}, **HTMX
    )
    assert antwort.status_code == 409
    a.refresh_from_db()
    assert a.faellig_am == date(2026, 10, 20)


def test_get_auf_verschieben_nicht_erlaubt(eltern_client, neue_instanz):
    assert eltern_client.get(verschieben_url(neue_instanz())).status_code == 405


# --- Neue Aufgabe in Tag ---------------------------------------------------------------------


def test_neue_aufgabe_mit_vorgegebenem_datum(eltern_client):
    antwort = eltern_client.get(reverse("aufgaben:neu"), {"datum": "2026-10-22"})
    assert antwort.context["form"].initial["start_datum"] == date(2026, 10, 22)
    assert 'value="2026-10-22"' in antwort.content.decode()
    ungueltig = eltern_client.get(reverse("aufgaben:neu"), {"datum": "x"})
    assert "start_datum" not in ungueltig.context["form"].initial
