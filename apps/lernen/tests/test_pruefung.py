"""Antwortprüfung: normalisieren, Alternativen, "fast richtig" (SPEC 21.2)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.lernen.pruefung import (
    alternativen,
    anzeige_antwort,
    erlaubter_abstand,
    normalisieren,
    pruefen,
)


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("  Dog  ", "dog"),
        ("DOG!", "dog"),
        ("ice-cream", "ice cream"),
        ("I'm", "im"),
        ("I’m", "im"),
        ("café", "cafe"),
        ("Straße", "strasse"),
        ("schön", "schön"),
        ("a   b\tc", "a b c"),
        ("...", ""),
        ("", ""),
    ],
)
def test_normalisieren(roh, erwartet):
    assert normalisieren(roh) == erwartet


def test_umlaut_bleibt_unterschied():
    assert normalisieren("schön") != normalisieren("schon")
    assert normalisieren("Äpfel") != normalisieren("Apfel")


def test_alternativen_trennen_und_klammern():
    assert alternativen("to be / be") == ["to be", "be"]
    assert alternativen("a; b") == ["a", "b"]
    assert alternativen("cousin (female)") == ["cousin (female)", "cousin"]
    assert alternativen(" / ; ") == []
    assert alternativen("x / x") == ["x"]


def test_anzeige_antwort():
    assert anzeige_antwort("cousin (female) / kin") == "cousin (female)"
    assert anzeige_antwort("") == ""


def test_richtig_mit_alternativen():
    assert pruefen("BE", "to be / be").richtig
    assert pruefen("To  Be.", "to be / be").treffer == "to be"
    assert pruefen("cousin", "cousin (female)").richtig


def test_fast_bei_kleinem_tippfehler():
    ergebnis = pruefen("elephnat", "elephant")  # vertauschte Nachbarn
    assert not ergebnis.richtig
    assert ergebnis.fast
    assert ergebnis.treffer == "elephant"
    assert pruefen("hrose", "horse").fast
    assert pruefen("horsee", "horse").fast


def test_kurze_woerter_kein_fast():
    assert not pruefen("cot", "cat").fast
    assert not pruefen("cot", "cat").richtig


def test_lange_woerter_zwei_tippfehler():
    assert erlaubter_abstand(3) == 0
    assert erlaubter_abstand(4) == 1
    assert erlaubter_abstand(10) == 2
    assert pruefen("refridgerator", "refrigerator").fast
    assert pruefen("refridgeratar", "refrigerator").fast
    assert not pruefen("refridgeratas", "refrigerators x").fast


def test_falsch_und_leer():
    assert not pruefen("dragon", "horse").richtig
    assert not pruefen("dragon", "horse").fast
    leer = pruefen("  ", "horse")
    assert not leer.richtig
    assert not leer.fast


def test_leere_variante_wird_uebersprungen():
    assert not pruefen("x", "()").richtig


def test_bestes_fast_gewinnt():
    assert pruefen("bluu", "blue / bleu").treffer == "blue"


@given(st.text(max_size=40))
def test_normalisieren_ist_idempotent(text):
    einmal = normalisieren(text)
    assert normalisieren(einmal) == einmal


@given(
    st.lists(st.from_regex(r"[a-z]{2,8}", fullmatch=True), min_size=1, max_size=3),
    st.booleans(),
)
def test_exakte_antwort_ist_immer_richtig(woerter, gross):
    antwort = " ".join(woerter)
    eingabe = f"  {antwort.upper() if gross else antwort}!! "
    ergebnis = pruefen(eingabe, antwort)
    assert ergebnis.richtig
    assert not ergebnis.fast


@given(st.text(max_size=20), st.text(max_size=20))
def test_nie_richtig_und_fast_zugleich(eingabe, erwartet):
    ergebnis = pruefen(eingabe, erwartet)
    assert not (ergebnis.richtig and ergebnis.fast)
    if not normalisieren(eingabe):
        assert not ergebnis.richtig
