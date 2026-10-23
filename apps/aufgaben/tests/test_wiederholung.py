from datetime import date, time

import pytest
from django.core.exceptions import ValidationError

from apps.aufgaben.models import Aufgabe
from apps.aufgaben.wiederholung import Plan, maske_aus_tagen, pruefen, tage_aus_maske


def test_maske_roundtrip():
    assert maske_aus_tagen([2]) == 0b100
    assert tage_aus_maske(maske_aus_tagen([0, 2, 6])) == [0, 2, 6]
    with pytest.raises(ValueError):
        maske_aus_tagen([7])


@pytest.mark.parametrize(
    ("plan", "feld"),
    [
        (Plan(art="woechentlich"), "wochentage"),
        (Plan(art="einmalig", wochentage=1), "wochentage"),
        (Plan(art="intervall"), "intervall_tage"),
        (Plan(art="intervall", intervall_tage=0), "intervall_tage"),
        (Plan(art="einmalig", intervall_tage=3), "intervall_tage"),
        (Plan(start_datum=date(2026, 5, 2), end_datum=date(2026, 5, 1)), "end_datum"),
        (Plan(fenster_von=time(8)), "fenster_bis"),
        (Plan(fenster_von=time(9), fenster_bis=time(8)), "fenster_bis"),
        (Plan(fenster_tage=1), "fenster_tage"),
        (Plan(limit_anzahl=1), "limit_anzahl"),
        (Plan(limit_zeitraum="woche"), "limit_anzahl"),
        (Plan(limit_anzahl=0, limit_zeitraum="woche"), "limit_anzahl"),
        (Plan(art="quatsch"), "wiederholungsart"),
    ],
)
def test_ungueltige_plaene(plan, feld):
    assert feld in pruefen(plan)


def test_gueltige_plaene():
    assert pruefen(Plan()) == {}
    assert pruefen(Plan(art="woechentlich", wochentage=0b100, fenster_bis=time(20))) == {}
    # Mi 18:00 bis Do 07:00
    assert pruefen(Plan(fenster_von=time(18), fenster_bis=time(7), fenster_tage=1)) == {}
    assert (
        pruefen(Plan(art="intervall", intervall_tage=3, limit_anzahl=1, limit_zeitraum="woche"))
        == {}
    )


def test_json_roundtrip_und_beschreibung():
    plan = Plan(
        art="woechentlich",
        wochentage=maske_aus_tagen([2]),
        fenster_bis=time(20),
        limit_anzahl=1,
        limit_zeitraum="woche",
    )
    assert Plan.aus_json(plan.als_json()) == plan
    text = plan.beschreiben()
    assert "Mi" in text and "20:00" in text and "pro Woche" in text
    assert Plan.aus_json(None) == Plan()


@pytest.mark.django_db
def test_modell_clean_wiederholung(mama):
    a = Aufgabe(titel="X", punkte=5, erstellt_von=mama, wiederholungsart="woechentlich")
    with pytest.raises(ValidationError) as exc:
        a.full_clean()
    assert "wochentage" in exc.value.message_dict
    a.wochentage = 0b1
    a.full_clean()
    assert a.plan.wochentage_liste == [0]
