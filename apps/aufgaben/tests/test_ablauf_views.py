"""Kinder- und Eltern-UI des Kinderablaufs (HTMX), Rechte."""

import pytest
from django.urls import reverse

from apps.aufgaben import services, wiederholung
from apps.aufgaben.models import Aufgabe, AufgabenInstanz, InstanzStatus
from apps.konten.tests.conftest import angemeldet
from apps.punkte import selectors as punkte_selectors

HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def neu(mama):
    def anlegen(titel="Spülmaschine", freigabeart="eltern", **felder):
        aufgabe = Aufgabe.objects.create(
            titel=titel,
            punkte=10,
            erstellt_von=mama,
            freigabeart=freigabeart,
            wiederholungsart=wiederholung.EINMALIG,
            **felder,
        )
        return AufgabenInstanz.objects.create(
            aufgabe=aufgabe,
            titel_snapshot=titel,
            punkte_snapshot=10,
            freigabeart_snapshot=freigabeart,
        )

    return anlegen


def test_kind_waehlt_und_meldet(client, anna, neu):
    instanz = neu()
    angemeldet(client, anna)
    seite = client.get(reverse("aufgaben:kind"))
    assert seite.status_code == 200 and "Spülmaschine" in seite.content.decode()
    antwort = client.post(reverse("aufgaben:kind_waehlen", args=[instanz.pk]), **HTMX)
    inhalt = antwort.content.decode()
    assert antwort.status_code == 200 and "Die Aufgabe gehört dir" in inhalt
    assert "Erledigt melden" in inhalt
    antwort = client.post(
        reverse("aufgaben:kind_melden", args=[instanz.pk]), {"text": "fertig"}, **HTMX
    )
    assert "Gemeldet" in antwort.content.decode()
    instanz.refresh_from_db()
    assert instanz.status == InstanzStatus.GEMELDET


def test_fachfehler_als_hinweis(client, anna, ben, neu):
    instanz = neu()
    services.interesse_zeigen(instanz, ben)
    services.erledigt_melden(instanz, ben)
    angemeldet(client, anna)
    antwort = client.post(reverse("aufgaben:kind_waehlen", args=[instanz.pk]), **HTMX)
    assert antwort.status_code == 404  # fremde, gemeldete Instanz: unsichtbar


def test_kind_sieht_fremd_zugewiesene_nicht(client, anna, ben, neu):
    neu(titel="Nur für Ben", zugewiesen_an=ben)
    angemeldet(client, anna)
    assert "Nur für Ben" not in client.get(reverse("aufgaben:kind")).content.decode()


def test_limit_hinweis(client, anna, neu, mama):
    instanz = neu(limit_anzahl=1, limit_zeitraum="woche")
    services.interesse_zeigen(instanz, anna)
    zweite = AufgabenInstanz.objects.create(
        aufgabe=instanz.aufgabe,
        plan_datum=None,
        titel_snapshot="x",
        punkte_snapshot=10,
        freigabeart_snapshot="eltern",
        fenster_ende=instanz.aufgabe.erstellt_am.replace(year=2099),
    )
    angemeldet(client, anna)
    antwort = client.post(reverse("aufgaben:kind_waehlen", args=[zweite.pk]), **HTMX)
    assert "höchstens 1× pro Woche" in antwort.content.decode()


def test_eltern_bestaetigen_mit_sonderpunkten(client, anna, mama, neu):
    instanz = neu()
    services.interesse_zeigen(instanz, anna)
    services.erledigt_melden(instanz, anna, text="Alles sauber")
    angemeldet(client, mama)
    seite = client.get(reverse("aufgaben:entscheidungen")).content.decode()
    assert "Alles sauber" in seite and "max. 5" in seite
    url = reverse("aufgaben:bestaetigen", args=[instanz.pk])
    zu_viel = client.post(url, {"sonderpunkte": "9", "begruendung": "x"}, **HTMX)
    assert "Höchstens 5" in zu_viel.content.decode()
    ok = client.post(url, {"sonderpunkte": "3", "begruendung": "gründlich"}, **HTMX)
    assert "Bestätigt" in ok.content.decode()
    doppelt = client.post(url, {"sonderpunkte": "3", "begruendung": "gründlich"}, **HTMX)
    assert doppelt.status_code == 200
    assert punkte_selectors.guthaben(anna) == 13
    client.logout()
    angemeldet(client, anna)
    kind = client.get(reverse("aufgaben:kind")).content.decode()
    assert "+3 Bonus: gründlich" in kind


def test_eltern_konflikt_zuteilen_und_korrektur(client, anna, ben, mama, neu):
    instanz = neu()
    services.interesse_zeigen(instanz, anna)
    services.interesse_zeigen(instanz, ben)
    angemeldet(client, mama)
    assert "Konflikte" in client.get(reverse("aufgaben:entscheidungen")).content.decode()
    client.post(reverse("aufgaben:zuteilen", args=[instanz.pk, ben.pk]), **HTMX)
    instanz.refresh_from_db()
    assert (instanz.status, instanz.kind) == (InstanzStatus.RESERVIERT, ben)

    vertrauen = neu(titel="Müll", freigabeart="vertrauen")
    services.interesse_zeigen(vertrauen, anna)
    services.erledigt_melden(vertrauen, anna)
    antwort = client.post(
        reverse("aufgaben:korrigieren", args=[vertrauen.pk]),
        {"begruendung": "nicht gemacht"},
        **HTMX,
    )
    assert "Korrigiert" in antwort.content.decode()
    assert punkte_selectors.guthaben(anna) == 0


@pytest.mark.parametrize(
    ("name", "args"),
    [("aufgaben:entscheidungen", []), ("aufgaben:loesen", [1]), ("aufgaben:bestaetigen", [1])],
)
def test_kind_kann_keine_eltern_urls(client, anna, name, args):
    angemeldet(client, anna)
    methode = client.get if not args else client.post
    assert methode(reverse(name, args=args)).status_code == 403


def test_eltern_koennen_keine_kind_urls(client, mama, neu):
    instanz = neu()
    angemeldet(client, mama)
    assert client.get(reverse("aufgaben:kind")).status_code == 403
    assert client.post(reverse("aufgaben:kind_waehlen", args=[instanz.pk])).status_code == 403
