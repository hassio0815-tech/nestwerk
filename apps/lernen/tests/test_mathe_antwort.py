"""Antwortprüfung für Mathe (SPEC 21.13): Zahlenformen, Brüche, Rest, Gleichungen, Terme."""

import random
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.lernen import pruefung
from apps.lernen.mathe import antwort, bausteine, registry, schwierigkeit, term
from apps.lernen.mathe.aufgabe import BRUCH, DEZIMAL, GANZ, GEMISCHT, Loesung


def r(gegeben, loesung):
    return antwort.pruefen(gegeben, loesung)


def ist_richtig(gegeben, loesung):
    return r(gegeben, loesung).richtig


# --- Zahlen ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "eingabe",
    [
        "1250",
        "1.250",
        "1 250",
        "1.250,0",
        "1250,00",
        "01250",
        "1250.0",
        "1,250.00",
        "1'250",
        " 1250 ",
    ],
)
def test_ganze_zahl_in_vielen_schreibweisen(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_zahl(1250))


@pytest.mark.parametrize("eingabe", ["3,5", "3.5", "3,50", "03,5", "3,500", "+3,5", " 3,5 "])
def test_dezimalzahl_komma_punkt_und_nullen(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_zahl(Fraction(7, 2)))


@pytest.mark.parametrize(
    "eingabe", ["3,6", "35", "0,35", "3,4", "3", "3,5,5", "3..5", "3,,5", "abc", ",5"]
)
def test_falsche_oder_unlesbare_zahlen(eingabe):
    assert not r(eingabe, bausteine.lsg_zahl(Fraction(7, 2))).richtig


@pytest.mark.parametrize("eingabe", ["-5", "−5", "- 5", "-5,0", "−05"])
def test_negative_zahlen(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_zahl(-5))


def test_negative_zahl_nicht_mit_positiver_verwechseln():
    assert not ist_richtig("5", bausteine.lsg_zahl(-5))
    assert not ist_richtig("-5", bausteine.lsg_zahl(5))


def test_tausenderpunkt_oder_dezimalpunkt_zaehlt_das_zur_aufgabe_passende():
    # "1.000" kann Tausend oder eins sein; richtig ist, was zur Aufgabe passt
    assert ist_richtig("1.000", bausteine.lsg_zahl(1000))
    assert ist_richtig("1.000", bausteine.lsg_zahl(1))
    assert not ist_richtig("1.000", bausteine.lsg_zahl(100))
    assert ist_richtig("1.000.000", bausteine.lsg_zahl(1_000_000))
    assert ist_richtig("12.345,67", bausteine.lsg_zahl(Fraction(1234567, 100)))
    assert ist_richtig("12,345.67", bausteine.lsg_zahl(Fraction(1234567, 100)))
    assert not ist_richtig("0.001,5", bausteine.lsg_zahl(1))


def test_unlesbare_eingabe_hat_fehlertyp():
    assert r("zwölf", bausteine.lsg_zahl(12)).fehlertyp == antwort.UNLESBAR
    assert r("", bausteine.lsg_zahl(12)) == antwort.FALSCH
    assert r("   ", bausteine.lsg_zahl(12)) == antwort.FALSCH
    assert r("1" * 200, bausteine.lsg_zahl(12)) == antwort.FALSCH


# --- Brüche und gemischte Zahlen ------------------------------------------------------------------


def test_bruch_gekuerzt_richtig_ungekuerzt_fast():
    loesung = bausteine.lsg_bruch(Fraction(3, 4))
    assert ist_richtig("3/4", loesung)
    assert ist_richtig(" 3 / 4 ", loesung)
    ungekuerzt = r("6/8", loesung)
    assert not ungekuerzt.richtig and ungekuerzt.fast
    assert ungekuerzt.fehlertyp == antwort.NICHT_GEKUERZT and "kürzen" in ungekuerzt.hinweis
    assert not r("5/8", loesung).richtig and not r("5/8", loesung).fast
    assert not r("3:4", loesung).richtig  # nur 3/4 ist ein Bruch


def test_bruch_als_dezimal_ist_nicht_erlaubt_aber_fast():
    befund = r("0,75", bausteine.lsg_bruch(Fraction(3, 4)))
    assert befund.fast and befund.fehlertyp == antwort.FALSCHE_FORM and "Bruch" in befund.hinweis


def test_gemischte_zahl_und_unechter_bruch_beide_richtig():
    loesung = bausteine.lsg_bruch(Fraction(7, 4))
    assert ist_richtig("7/4", loesung)
    assert ist_richtig("1 3/4", loesung)
    assert ist_richtig("1  3/4", loesung)
    assert r("2 6/8", loesung).richtig is False
    assert r("1 6/8", loesung).fast  # Wert stimmt, Bruchteil nicht gekürzt
    assert not r("1 4/4", loesung).richtig  # kein echter Bruchteil
    assert not r("1 3/0", loesung).richtig
    assert not r("3/0", loesung).richtig


def test_ganze_zahl_als_ergebnis_einer_bruchaufgabe():
    loesung = bausteine.lsg_bruch(Fraction(2))
    assert ist_richtig("2", loesung)
    assert r("4/2", loesung).fast  # nicht gekürzt
    assert not r("2/3", loesung).richtig


def test_aequivalenter_bruch_ohne_kuerzen_verlangt_ist_richtig():
    loesung = bausteine.lsg_bruch(Fraction(3, 4), kuerzen=False)
    assert ist_richtig("6/8", loesung)
    assert ist_richtig("3/4", loesung)


# --- Rest, Gleichung, Prozent, Einheiten ----------------------------------------------------------


@pytest.mark.parametrize("eingabe", ["17 R 2", "17r2", "17 Rest 2", "17 r 2", "017 R 02"])
def test_rest_schreibweisen(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_rest(17, 2))


def test_rest_falsch_und_fast():
    loesung = bausteine.lsg_rest(17, 2)
    assert not r("17 R 3", loesung).richtig and not r("16 R 2", loesung).richtig
    ohne = r("17", loesung)
    assert ohne.fast and ohne.fehlertyp == antwort.REST_FEHLT and "Rest" in ohne.hinweis
    assert not r("blau", loesung).richtig
    assert not r("17,2", loesung).richtig


@pytest.mark.parametrize("eingabe", ["x=5", "x = 5", "X = 5", "5", "5 = x", "x=5,0", " x =  5 "])
def test_gleichungsergebnis(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_gleichung(5))


def test_gleichung_falsche_variable_oder_wert():
    loesung = bausteine.lsg_gleichung(5)
    assert not r("x=6", loesung).richtig
    falsch_var = r("y=5", loesung)
    assert not falsch_var.richtig and falsch_var.fehlertyp == antwort.VARIABLE
    assert not r("x=", loesung).richtig
    assert ist_richtig("x=-3", bausteine.lsg_gleichung(-3))
    assert ist_richtig("x = −3", bausteine.lsg_gleichung(-3))
    assert ist_richtig("a=2", bausteine.lsg_gleichung(2, "a"))


@pytest.mark.parametrize("eingabe", ["25", "25%", "25 %", "25 Prozent", "25,0 %"])
def test_prozent(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_zahl(25, prozent=True))


def test_prozentzeichen_nur_wenn_prozent_gefragt():
    assert not ist_richtig("12 %", bausteine.lsg_zahl(12))
    assert r("12 %", bausteine.lsg_zahl(12)).fehlertyp == antwort.EINHEIT


@pytest.mark.parametrize(
    "eingabe", ["5,50", "5,5", "5,50 €", "5,50€", "5,50 Euro", "5.50 EUR", "5,50 euro"]
)
def test_einheit_ist_optional_aber_muss_stimmen(eingabe):
    assert ist_richtig(eingabe, bausteine.lsg_zahl(Fraction(11, 2), einheit="€", stellen=2))


def test_falsche_einheit_ist_falsch():
    loesung = bausteine.lsg_zahl(250, einheit="cm")
    assert ist_richtig("250", loesung) and ist_richtig("250 cm", loesung)
    assert ist_richtig("250cm", loesung) and ist_richtig("250 Zentimeter", loesung)
    falsch = r("250 m", loesung)
    assert not falsch.richtig and falsch.fehlertyp == antwort.EINHEIT
    assert not r("250 xyz", loesung).richtig
    assert ist_richtig("2 m 50 cm", loesung) is False  # Mehrteiliges lesen wir nicht


def test_einheit_ohne_erwartete_einheit_wird_ignoriert_wenn_bekannt():
    assert ist_richtig("5 kg", bausteine.lsg_zahl(5))
    assert not r("5 Äpfel", bausteine.lsg_zahl(5)).richtig


def test_form_der_zahl_wenn_bruch_nicht_erlaubt():
    loesung = bausteine.lsg_zahl(Fraction(3, 4))
    befund = r("3/4", loesung)
    assert befund.fast and befund.fehlertyp == antwort.FALSCHE_FORM and "Zahl" in befund.hinweis
    assert ist_richtig("0,75", loesung)


def test_dezimal_nicht_erlaubt_wenn_nur_ganz():
    loesung = Loesung("zahl", "5", "5", erlaubt=(GANZ,))
    assert ist_richtig("5", loesung)
    assert r("5,0", loesung).fast


# --- Terme ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "eingabe",
    ["x^2+5x+6", "x² + 5x + 6", "6 + 5x + x^2", "x*x+5*x+6", "x·x + 5·x + 6", "x^2 + 5 x + 6"],
)
def test_term_aequivalente_schreibweisen(eingabe):
    loesung = bausteine.lsg_term(term.lesen("(x+2)(x+3)"))
    assert ist_richtig(eingabe, loesung)


def test_term_falsch_unlesbar_und_nicht_vereinfacht():
    loesung = bausteine.lsg_term(term.lesen("(x+2)(x+3)"))
    assert not r("x^2+6x+5", loesung).richtig
    assert r("x^2+5x+", loesung).fehlertyp == antwort.UNLESBAR
    assert r("(x+2)(x+3)", loesung).fehlertyp == antwort.NICHT_VEREINFACHT
    assert r("x^2+2x+3x+6", loesung).fast
    summe = bausteine.lsg_term(term.lesen("3x+5x"))
    assert ist_richtig("8x", summe) and ist_richtig("8*x", summe)
    assert r("3x+5x", summe).fast
    assert r("7x", summe) == antwort.FALSCH


def test_term_mit_zwei_variablen_und_vorzeichen():
    loesung = bausteine.lsg_term(term.lesen("2a+6b-3"))
    assert ist_richtig("6b + 2a − 3", loesung)
    assert ist_richtig("-3+2a+6b", loesung)
    assert not ist_richtig("2a+6b+3", loesung)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "x^99",
        "((",
        "x " + "y " * 50,
        "3 4",
        "x$",
    ],
)
def test_term_lesen_wirft_bei_unsinn(text):
    with pytest.raises(term.TermFehler):
        term.lesen(text)


def test_term_format_und_summanden():
    p = term.lesen("-2x²+3x-1")
    assert term.format_term(p) == "−2x² + 3x − 1"
    assert term.format_term(p, anzeige=False) == "-2x^2+3x-1"
    assert term.format_term({}) == "0"
    assert term.summanden("3x + 4x - 2") == 3 and term.summanden("2(x+1)") == 1
    assert term.hat_klammern("2(x+1)") and not term.hat_klammern("2x")
    assert term.gleich(term.lesen("x+x"), term.lesen("2x"))


# --- Pruefung (Anbindung) -------------------------------------------------------------------------


def test_pruefung_pruefen_mathe_gibt_pruefergebnis_mit_hinweis_und_typ():
    loesung = bausteine.lsg_bruch(Fraction(3, 4))
    ok = pruefung.pruefen_mathe("3/4", loesung)
    assert ok.richtig and ok.treffer == "3/4" and not ok.hinweis and not ok.fehlertyp
    fast = pruefung.pruefen_mathe("6/8", loesung.to_dict())
    assert fast.fast and not fast.richtig and fast.hinweis and fast.fehlertyp == "nicht_gekuerzt"
    assert fast.treffer == "3/4"


def test_vokabelpruefung_bleibt_unveraendert():
    assert pruefung.pruefen("Hund", "Hund").richtig
    assert pruefung.pruefen("dog ", "dog / hound").richtig
    ergebnis = pruefung.pruefen("hoose", "house")
    assert ergebnis.fast and ergebnis.hinweis == "" and ergebnis.fehlertyp == ""


# --- Eigenschaften --------------------------------------------------------------------------------


@given(st.integers(-(10**9), 10**9))
def test_jede_ganze_zahl_wird_gelesen(n):
    loesung = bausteine.lsg_zahl(n)
    assert ist_richtig(str(n), loesung)
    assert ist_richtig(str(n).replace("-", "−"), loesung)
    assert not ist_richtig(str(n + 1), loesung)


@given(st.integers(-(10**6), 10**6), st.integers(0, 3))
def test_dezimalzahlen_mit_komma_und_punkt(zaehler, nachkomma):
    wert = Fraction(zaehler, 10**nachkomma)
    loesung = bausteine.lsg_zahl(wert)
    text = bausteine.dezimal_text(wert, nachkomma or None).replace("−", "-")
    assert ist_richtig(text, loesung)
    assert ist_richtig(text.replace(",", "."), loesung)


@given(st.integers(1, 200), st.integers(2, 200))
def test_brueche_nur_gekuerzt_richtig(z, n):
    wert = Fraction(z, n)
    loesung = bausteine.lsg_bruch(wert)
    assert ist_richtig(bausteine.bruch_text(wert), loesung)
    k = 3
    unge = f"{wert.numerator * k}/{wert.denominator * k}"
    befund = r(unge, loesung)
    assert not befund.richtig and befund.fast
    assert not ist_richtig(f"{wert.numerator + 1}/{wert.denominator}", loesung)


@given(st.integers(0, 10**5), st.integers(1, 99), st.integers(0, 98))
def test_rest_eigenschaft(q, teiler, rest):
    rest = rest % teiler
    loesung = bausteine.lsg_rest(q, rest)
    assert ist_richtig(f"{q} R {rest}", loesung)
    assert not ist_richtig(f"{q} R {rest + 1}", loesung)
    assert not ist_richtig(f"{q + 1} R {rest}", loesung)


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=120))
def test_beliebige_eingaben_stuerzen_nie_ab(text):
    for loesung in (
        bausteine.lsg_zahl(5),
        bausteine.lsg_bruch(Fraction(3, 4)),
        bausteine.lsg_rest(17, 2),
        bausteine.lsg_gleichung(5),
        bausteine.lsg_term(term.lesen("x+1")),
        bausteine.lsg_zahl(5, einheit="€", stellen=2),
    ):
        befund = antwort.pruefen(text, loesung)
        assert isinstance(befund.richtig, bool)
        assert not (befund.richtig and befund.fast)


@pytest.mark.parametrize("schluessel", sorted(registry.schluessel_alle()))
@settings(max_examples=15, deadline=None)
@given(seed=st.integers(0, 2**48 - 1))
def test_eine_geaenderte_antwort_ist_nicht_richtig(schluessel, seed):
    a = registry.erzeugen(schluessel, 3, seed)
    if a.loesung.form in ("zahl", "gleichung"):
        falsch = a.loesung.als_bruch() + 7
        if falsch.denominator != 1 and not bausteine.ist_endlich(falsch):
            return
        assert not antwort.pruefen(bausteine.bruch_text(falsch), a.loesung).richtig


def test_formnamen_sind_stabil():
    assert (GANZ, DEZIMAL, BRUCH, GEMISCHT) == ("ganz", "dezimal", "bruch", "gemischt")


def test_schwierigkeit_modul_konstanten():
    assert schwierigkeit.HOECHSTE == {"grund": 4, "erweitert": 5}


# --- Bausteine ------------------------------------------------------------------------------------


def test_zahlen_schreiben():
    assert bausteine.dezimal_text(Fraction(7, 2)) == "3,5"
    assert bausteine.dezimal_text(Fraction(-7, 2)) == "−3,5"
    assert bausteine.dezimal_text(Fraction(1, 20), 3) == "0,050"
    assert bausteine.dezimal_text(5) == "5"
    assert bausteine.zahl_text(-4) == "−4" and bausteine.zahl_text(5, 2) == "5,00"
    with pytest.raises(ValueError):
        bausteine.dezimal_text(Fraction(1, 3))
    with pytest.raises(ValueError):
        bausteine.dezimal_text(Fraction(1, 8), 2)
    assert (
        bausteine.bruch_text(Fraction(6, 3)) == "2"
        and bausteine.bruch_text(Fraction(3, 4)) == "3/4"
    )
    assert bausteine.gemischt_text(Fraction(7, 4)) == "1 3/4"
    assert bausteine.gemischt_text(Fraction(3, 4)) == "3/4" and bausteine.gemischt_text(3) == "3"
    assert bausteine.klammer_neg(-3) == "(−3)" and bausteine.klammer_neg(3) == "3"


def test_runden_kaufmaennisch():
    assert bausteine.runden(Fraction(25, 10), 0) == 3
    assert bausteine.runden(Fraction(-25, 10), 0) == -3
    assert bausteine.runden(Fraction(3478, 1000), 2) == Fraction(348, 100)
    assert bausteine.runden(3482, -2) == 3500


def test_waehle_nimmt_den_fallback():
    assert bausteine.waehle(random.Random(1), lambda: 1, lambda x: False, "ersatz", 5) == "ersatz"


def test_obergrenze_kontext():
    k = registry.Kontext(50)
    assert k.lim(1000) == 50 and k.lim(30) == 30 and registry.Kontext(5).lim(1000) == 20
    assert registry.Kontext().lim(1000) == 1000
    assert registry.band(None) == 6 and registry.band(2) == 3 and registry.band(9) == 8
    assert (
        registry.niveau("Erweiterungsniveau") == "erweitert"
        and registry.niveau("E-Kurs") == "erweitert"
    )
    assert registry.niveau("") == "grund" and registry.niveau("Grundniveau") == "grund"
    assert registry.generatoren_fuer(klassenstufe=3) and registry.generatoren_fuer(
        thema="mathe_8_terme"
    )


def test_generator_darf_nicht_doppelt_angemeldet_werden():
    with pytest.raises(ValueError):
        registry.generator("einmaleins", "x", thema="t", klassenstufe=3)(lambda *a: None)
