"""Wochenvorschau der Anmeldeseite: nur wiederkehrende Aufgaben, 7 Tage ab heute."""

from datetime import date, timedelta

import pytest

from apps.aufgaben import selectors
from apps.aufgaben.models import Aufgabe, Status
from apps.konten import services as konten
from apps.konten.tests.conftest import PASSWORT

HEUTE = date(2026, 10, 23)  # Freitag


@pytest.fixture
def mama(db):
    benutzer = konten.eltern_anlegen("Mama", rolle_label="mama")
    konten.eltern_passwort_setzen(PASSWORT, von=benutzer)
    return benutzer


def neu(mama, titel, **kw):
    kw.setdefault("punkte", 5)
    kw.setdefault("start_datum", HEUTE - timedelta(days=30))
    return Aufgabe.objects.create(titel=titel, erstellt_von=mama, **kw)


def titel_je_tag(woche):
    return {t["datum"]: [a.titel for a in t["aufgaben"]] for t in woche}


def test_sieben_tage_ab_heute_heute_markiert(mama):
    woche = selectors.start_woche(heute=HEUTE)
    assert [t["datum"] for t in woche] == [HEUTE + timedelta(days=i) for i in range(7)]
    assert [t["heute"] for t in woche] == [True] + [False] * 6


def test_woechentlich_nur_an_den_gewaehlten_tagen(mama):
    neu(mama, "Müll", wiederholungsart="woechentlich", wochentage=0b0000101)  # Mo, Mi
    tage = titel_je_tag(selectors.start_woche(heute=HEUTE))
    # Fr 23.10. ... Do 29.10.: Mo 26., Mi 28.
    assert [d.day for d, t in tage.items() if t] == [26, 28]


def test_intervall_zaehlt_ab_startdatum(mama):
    neu(
        mama,
        "Bad",
        wiederholungsart="intervall",
        intervall_tage=3,
        start_datum=HEUTE - timedelta(days=1),
    )
    tage = titel_je_tag(selectors.start_woche(heute=HEUTE))
    assert [d.day for d, t in tage.items() if t] == [25, 28]


def test_enddatum_und_pausiert_werden_beachtet(mama):
    neu(
        mama,
        "Endet",
        wiederholungsart="intervall",
        intervall_tage=1,
        end_datum=HEUTE + timedelta(days=1),
    )
    neu(mama, "Pause", wiederholungsart="intervall", intervall_tage=1, status=Status.PAUSIERT)
    tage = titel_je_tag(selectors.start_woche(heute=HEUTE))
    assert [d.day for d, t in tage.items() if t] == [23, 24]
    assert all("Pause" not in t for t in tage.values())


def test_einmalige_und_bei_bedarf_fehlen(mama):
    neu(mama, "Einmal", wiederholungsart="einmalig", start_datum=HEUTE)
    neu(mama, "Knopf", wiederholungsart="bei_bedarf")
    assert not any(t["aufgaben"] for t in selectors.start_woche(heute=HEUTE))


def test_ohne_startdatum_gilt_anlagetag(mama):
    from datetime import UTC, datetime

    a = neu(mama, "Täglich", wiederholungsart="intervall", intervall_tage=1, start_datum=None)
    Aufgabe.objects.filter(pk=a.pk).update(erstellt_am=datetime(2026, 10, 25, 12, tzinfo=UTC))
    tage = titel_je_tag(selectors.start_woche(heute=HEUTE))
    assert [d.day for d, t in tage.items() if t] == [25, 26, 27, 28, 29]


def test_wenige_abfragen(mama, django_assert_max_num_queries):
    for i in range(6):
        neu(mama, f"A{i}", wiederholungsart="woechentlich", wochentage=127)
    with django_assert_max_num_queries(2):
        woche = selectors.start_woche(heute=HEUTE)
        for t in woche:
            for a in t["aufgaben"]:
                str(a.zugewiesen_an)


def test_aufgaben_je_kind_erscheinen_einzeln_mit_kind(mama):
    from apps.konten import services as k

    anna = k.kind_anlegen("Anna", "1234", akzentfarben=["#ff4fa0"])
    ben = k.kind_anlegen("Ben", "4321", akzentfarben=["#3377ff"])
    for kind in (anna, ben):
        neu(
            mama,
            "Zimmer aufräumen",
            wiederholungsart="woechentlich",
            wochentage=0b0000001,
            zugewiesen_an=kind,
        )
    montag = next(t for t in selectors.start_woche(heute=HEUTE) if t["datum"].day == 26)
    assert sorted(a.zugewiesen_an.rufname for a in montag["aufgaben"]) == ["Anna", "Ben"]
