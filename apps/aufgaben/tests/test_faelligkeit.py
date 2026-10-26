"""Fälligkeitsberechnung (rein, ohne DB): Termine und DST-sichere Zeitfenster."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from apps.aufgaben import wiederholung
from apps.aufgaben.faelligkeit import fenster, termine
from apps.aufgaben.wiederholung import Plan, maske_aus_tagen

BERLIN = ZoneInfo("Europe/Berlin")


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_einmalig_nur_am_start():
    plan = Plan(start_datum=date(2026, 10, 28))
    assert termine(plan, date(2026, 10, 20), date(2026, 11, 5)) == [date(2026, 10, 28)]
    assert termine(plan, date(2026, 10, 29), date(2026, 11, 5)) == []
    assert termine(Plan(), date(2026, 10, 20), date(2026, 11, 5)) == []
    assert termine(Plan(), date(2026, 10, 20), date(2026, 11, 5), start=date(2026, 10, 21)) == [
        date(2026, 10, 21)
    ]


def test_woechentlich_an_wochentagen_mit_start_und_ende():
    plan = Plan(
        art=wiederholung.WOECHENTLICH,
        wochentage=maske_aus_tagen([0, 2]),  # Mo, Mi
        start_datum=date(2026, 10, 21),  # Mi
        end_datum=date(2026, 11, 2),  # Mo
    )
    assert termine(plan, date(2026, 10, 1), date(2026, 12, 31)) == [
        date(2026, 10, 21),
        date(2026, 10, 26),
        date(2026, 10, 28),
        date(2026, 11, 2),
    ]


def test_intervall_bleibt_am_start_ausgerichtet():
    plan = Plan(art=wiederholung.INTERVALL, intervall_tage=3, start_datum=date(2026, 10, 1))
    assert termine(plan, date(2026, 10, 5), date(2026, 10, 14)) == [
        date(2026, 10, 7),
        date(2026, 10, 10),
        date(2026, 10, 13),
    ]
    assert termine(plan, date(2026, 9, 1), date(2026, 10, 2)) == [date(2026, 10, 1)]


def test_fenster_ueber_herbst_umstellung():
    """25.10.2026: Ende der Sommerzeit. Lokale Uhrzeit bleibt, UTC verschiebt sich um 1 h."""
    plan = Plan(
        art=wiederholung.INTERVALL,
        intervall_tage=1,
        fenster_von=time(18, 0),
        fenster_bis=time(20, 0),
    )
    assert fenster(plan, date(2026, 10, 24), BERLIN) == (
        utc(2026, 10, 24, 16),
        utc(2026, 10, 24, 18),
    )
    assert fenster(plan, date(2026, 10, 25), BERLIN) == (
        utc(2026, 10, 25, 17),
        utc(2026, 10, 25, 19),
    )


def test_fenster_mehrtaegig_und_ohne_beginn():
    plan = Plan(fenster_von=time(18, 0), fenster_bis=time(7, 0), fenster_tage=1)
    assert fenster(plan, date(2026, 10, 24), BERLIN) == (
        utc(2026, 10, 24, 16),
        utc(2026, 10, 25, 6),
    )
    nur_frist = Plan(fenster_bis=time(20, 0))
    assert fenster(nur_frist, date(2026, 10, 26), BERLIN) == (
        utc(2026, 10, 25, 23),
        utc(2026, 10, 26, 19),
    )
    mitternacht = Plan(fenster_bis=time(0, 0))
    assert fenster(mitternacht, date(2026, 10, 26), BERLIN)[1] == utc(2026, 10, 26, 23)


def test_fenster_in_fruehjahrs_luecke():
    """28.03.2027: 02:00–03:00 gibt es nicht. 02:30 -> 03:30 Sommerzeit."""
    plan = Plan(fenster_von=time(2, 30), fenster_bis=time(4, 0))
    assert fenster(plan, date(2027, 3, 28), BERLIN) == (
        utc(2027, 3, 28, 1, 30),
        utc(2027, 3, 28, 2),
    )
    ganz_in_luecke = Plan(fenster_von=time(2, 15), fenster_bis=time(2, 45))
    beginn, ende = fenster(ganz_in_luecke, date(2027, 3, 28), BERLIN)
    assert ende > beginn
