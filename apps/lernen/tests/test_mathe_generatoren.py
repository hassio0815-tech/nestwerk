"""Mathe-Generatoren (SPEC 21.13): Lösung stimmt (unabhängige Gegenrechnung), Zahlenräume je
Klasse und Stufe, Determinismus, kindgerechte und eindeutige Aufgaben je Generator."""

import json
import re
from fractions import Fraction
from math import gcd, isqrt

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.lernen.mathe import antwort, registry, term
from apps.lernen.mathe.aufgabe import Aufgabe, Loesung

SEEDS = st.integers(min_value=0, max_value=2**48 - 1)
STUFEN = range(1, 6)
ALLE = sorted(registry.schluessel_alle())
HOCH = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def wert_von(text):
    """Unabhängige Gegenrechnung: wertet einen Rechenausdruck des Aufgabentexts mit exakten
    Brüchen aus (Punkt vor Strich, Klammern, Potenzen, Wurzeln)."""
    t = text.split("= ?")[0]
    if re.search(r"[A-Za-zäöüÄÖÜ]{3,}[a-zäöü]*: ", t):
        t = t.split(": ", 1)[1]
    t = t.replace("−", "-").replace("·", "*").replace(" : ", " / ")
    t = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "**" + m.group().translate(HOCH), t)
    t = re.sub(r"√\(([^)]*)\)", r"wurzel(\1)", t)
    t = re.sub(r"√(\d+(?:,\d+)?)", r"wurzel(\1)", t)
    t = t.replace(",", ".")
    t = re.sub(r"\d+(?:\.\d+)?", lambda m: f"Fraction('{m.group()}')", t)

    def wurzel(q):
        z, n = isqrt(q.numerator), isqrt(q.denominator)
        assert z * z == q.numerator and n * n == q.denominator, "keine exakte Wurzel"
        return Fraction(z, n)

    return eval(t, {"Fraction": Fraction, "wurzel": wurzel, "__builtins__": {}})  # noqa: S307


def poly_wert(text, **belegung):
    """Wert eines Terms für eine Belegung der Buchstaben (ohne ``term.lesen``)."""
    t = text.replace("−", "-").replace("·", "*")
    t = re.sub(r"([²³⁴⁵⁶])", lambda m: "**" + m.group().translate(HOCH), t)
    t = re.sub(r"(\d|\)|[a-z])\s*(?=[a-z(])", r"\1*", t)  # 3x -> 3*x, 2( -> 2*(, )( -> )*(
    t = re.sub(r"(?<![\w.])(\d+)", r"Fraction(\1)", t)
    namen = {k: Fraction(v) for k, v in belegung.items()}
    return eval(t, {"Fraction": Fraction, "__builtins__": {}}, namen)  # noqa: S307


def zahl(aufgabe):
    return aufgabe.loesung.als_bruch()


def stellen(q):
    q = Fraction(q)
    n = 0
    while (q * 10**n).denominator != 1:
        n += 1
    return n


def uebertraege(a, b):
    n, u = 0, 0
    while a or b or u:
        s = a % 10 + b % 10 + u
        u = int(s >= 10)
        n += u
        a //= 10
        b //= 10
    return n


def borgen(a, b):
    n, u = 0, 0
    while a or b:
        z = a % 10 - u - b % 10
        u = int(z < 0)
        n += u
        a //= 10
        b //= 10
    return n


def gen(schluessel, d, seed, **kontext):
    return registry.erzeugen(schluessel, d, seed, registry.Kontext(**kontext))


# --- Für jeden Generator --------------------------------------------------------------------------


def test_registry_hat_alle_klassen_und_themen():
    klassen = {g.klassenstufe for g in registry.alle().values()}
    assert klassen == {3, 6, 8}
    assert len(ALLE) >= 25
    assert all(g.thema.startswith(f"mathe_{g.klassenstufe}_") for g in registry.alle().values())
    with pytest.raises(KeyError):
        registry.holen("gibt_es_nicht")


@pytest.mark.parametrize("schluessel", ALLE)
@pytest.mark.parametrize("d", STUFEN)
@settings(max_examples=40, deadline=None)
@given(seed=SEEDS)
def test_aufgabe_ist_vollstaendig_und_geht_selbst_durch_die_pruefung(schluessel, d, seed):
    a = gen(schluessel, d, seed)
    assert isinstance(a, Aufgabe) and a.generator == schluessel and a.schwierigkeit == d
    assert a.klassenstufe == registry.holen(schluessel).klassenstufe
    assert 0 < len(a.text) <= 300 and a.text.strip() == a.text
    assert a.typ and a.thema == registry.holen(schluessel).thema
    json.dumps(a.to_dict())  # alles als Daten speicherbar
    assert Loesung.from_dict(a.to_dict()["loesung"]) == a.loesung
    # die berechnete Lösung wird in ihrer Anzeige-Schreibweise als richtig erkannt
    assert antwort.pruefen(a.loesung.anzeige, a.loesung).richtig, (a.text, a.loesung.anzeige)
    assert antwort.pruefen(a.loesung.anzeige, a.to_dict()["loesung"]).richtig


@pytest.mark.parametrize("schluessel", ALLE)
@pytest.mark.parametrize("d", STUFEN)
@settings(max_examples=25, deadline=None)
@given(seed=SEEDS)
def test_gleicher_seed_gleiche_aufgabe(schluessel, d, seed):
    assert gen(schluessel, d, seed) == gen(schluessel, d, seed)


@pytest.mark.parametrize("schluessel", ALLE)
def test_verschiedene_seeds_geben_verschiedene_aufgaben(schluessel):
    texte = {gen(schluessel, d, s).text for d in STUFEN for s in range(40)}
    assert len(texte) >= 20  # Abwechslung, nicht immer dieselbe Aufgabe


@pytest.mark.parametrize("schluessel", ALLE)
@pytest.mark.parametrize("d", STUFEN)
@settings(max_examples=20, deadline=None)
@given(seed=SEEDS)
def test_analoge_aufgabe_hat_andere_zahlen(schluessel, d, seed):
    a = gen(schluessel, d, seed)
    b = registry.analog(a)
    assert (b.generator, b.schwierigkeit) == (a.generator, a.schwierigkeit)
    assert b.parameter != a.parameter and b.seed != a.seed


def test_schwierigkeit_wird_begrenzt():
    assert registry.erzeugen("einmaleins", 99, 1).schwierigkeit == 5
    assert registry.erzeugen("einmaleins", -3, 1).schwierigkeit == 1


@pytest.mark.parametrize("schluessel", ALLE)
@settings(max_examples=10, deadline=None)
@given(seed=SEEDS)
def test_schwere_stufen_sind_nicht_leichter_als_leichte(schluessel, seed):
    # keine harte Regel, aber die Texte der Stufe 5 sind im Schnitt nicht kürzer als die der Stufe 1
    kurz = sum(len(gen(schluessel, 1, seed + i).text) for i in range(8))
    lang = sum(len(gen(schluessel, 5, seed + i).text) for i in range(8))
    assert lang >= kurz * 0.6


@pytest.mark.parametrize("schluessel", ALLE)
def test_obergrenze_der_eltern_wird_parameter_und_reproduzierbar(schluessel):
    a = gen(schluessel, 3, 7, grenze=50)
    assert a.parameter["grenze"] == 50
    assert registry.analog(a).parameter["grenze"] == 50
    assert gen(schluessel, 3, 7, grenze=50) == a


# --- Klasse 3 -------------------------------------------------------------------------------------


@given(seed=SEEDS)
@settings(max_examples=60, deadline=None)
def test_k3_plus_minus_rechnet_nur_im_zahlenraum_ohne_negative(seed):
    for schluessel, grenze in (("add_sub_100", 100), ("add_sub_1000", 1000)):
        for d in STUFEN:
            a = gen(schluessel, d, seed)
            p = a.parameter
            erwartet = p["a"] + p["b"] if p["op"] == "+" else p["a"] - p["b"]
            assert zahl(a) == erwartet == wert_von(a.text)
            assert 0 < p["a"] <= grenze and 0 < p["b"] <= grenze
            assert 0 <= erwartet <= grenze
            if a.typ == "add_ohne_uebertrag":
                assert uebertraege(p["a"], p["b"]) == 0
            if a.typ == "add_mit_uebertrag":
                assert uebertraege(p["a"], p["b"]) >= 1
            if a.typ == "sub_ohne_borgen":
                assert borgen(p["a"], p["b"]) == 0
            if a.typ == "sub_mit_borgen":
                assert borgen(p["a"], p["b"]) >= 1 and p["a"] > p["b"]


def test_k3_plus_minus_stufen_zeigen_uebertrag_erst_spaeter():
    typen = lambda d: {gen("add_sub_100", d, s).typ for s in range(60)}  # noqa: E731
    assert typen(1) <= {"add_ohne_uebertrag", "sub_ohne_borgen"}
    assert typen(3) == {"add_mit_uebertrag"}
    assert typen(4) == {"sub_mit_borgen"}


@given(seed=SEEDS)
@settings(max_examples=60, deadline=None)
def test_k3_obergrenze_gilt_fuer_zahlenraum(seed):
    a = gen("add_sub_1000", 4, seed, grenze=100)
    assert a.parameter["a"] <= 100 and a.parameter["b"] <= 100
    assert zahl(a) <= 100


@given(seed=SEEDS)
@settings(max_examples=60, deadline=None)
def test_k3_einmaleins_umkehr_division(seed):
    for d in STUFEN:
        e = gen("einmaleins", d, seed)
        assert zahl(e) == wert_von(e.text)
        assert e.parameter["a"] * e.parameter["b"] == zahl(e)
        assert min(e.parameter["a"], e.parameter["b"]) >= 1
        if d < 5:
            assert max(e.parameter["a"], e.parameter["b"]) <= 100
        v = gen("division_ohne_rest", d, seed)
        p = v.parameter
        assert p["dividend"] % p["teiler"] == 0 and zahl(v) == p["dividend"] // p["teiler"]
        assert p["dividend"] <= 100 and zahl(v) == wert_von(v.text)
        u = gen("umkehr", d, seed)
        if u.typ == "fehlender_faktor":
            assert zahl(u) * u.parameter["faktor"] == u.parameter["produkt"]
            assert u.parameter["produkt"] <= 100
        else:
            assert zahl(u) + u.parameter["a"] == u.parameter["ziel"] and zahl(u) > 0


def test_k3_einmaleins_stufe_1_hat_nur_leichte_reihen():
    for s in range(80):
        p = gen("einmaleins", 1, s).parameter
        assert p["a"] in (2, 5, 10) or p["b"] in (2, 5, 10)


@given(seed=SEEDS)
@settings(max_examples=60, deadline=None)
def test_k3_geld_und_laengen_sind_nicht_negativ_und_haben_einheit(seed):
    for d in STUFEN:
        g = gen("geld", d, seed)
        assert zahl(g) > 0 and g.loesung.einheit in ("ct", "€")
        if g.loesung.einheit == "€":
            assert stellen(zahl(g)) <= 2
            assert g.loesung.anzeige.endswith("€") and re.search(r",\d\d €$", g.loesung.anzeige)
        l = gen("laenge", d, seed)  # noqa: E741
        assert zahl(l) > 0 and l.loesung.einheit in ("cm", "m", "mm")
        assert zahl(l).denominator == 1
    assert zahl(gen("geld", 4, seed)) < 20  # Wechselgeld bleibt unter dem Betrag


def test_k3_wechselgeld_ist_positiv_und_kleiner_als_gezahlt():
    for s in range(200):
        a = gen("geld", 4, s)
        assert 0 < zahl(a) < a.parameter["bezahlt"]
        assert zahl(a) == a.parameter["bezahlt"] - Fraction(a.parameter["kosten"])


# --- Klasse 6 -------------------------------------------------------------------------------------


@given(seed=SEEDS)
@settings(max_examples=60, deadline=None)
def test_k6_schriftlich_multiplikation_und_division(seed):
    for d in STUFEN:
        m = gen("mult_schriftlich", d, seed)
        assert zahl(m) == m.parameter["a"] * m.parameter["b"] == wert_von(m.text)
        assert m.parameter["a"] >= 10 and m.parameter["b"] >= 2
        v = gen("div_schriftlich", d, seed)
        p = v.parameter
        if v.typ == "div_ohne_rest":
            assert p["dividend"] % p["teiler"] == 0 and zahl(v) == p["dividend"] // p["teiler"]
        elif v.typ == "div_mit_rest":
            q, r = divmod(p["dividend"], p["teiler"])
            assert 0 < r < p["teiler"] and zahl(v) == q and v.loesung.rest == r
            assert v.loesung.anzeige == f"{q} R {r}"
        else:
            assert v.typ == "div_dezimal"
            assert zahl(v) == Fraction(p["dividend"], p["teiler"])
            assert zahl(v).denominator != 1 and stellen(zahl(v)) <= 3
            assert "Dezimalzahl" in v.text


def test_k6_div_mit_rest_hat_keine_dezimalloesung_und_nur_ab_stufe_3():
    for s in range(80):
        assert gen("div_schriftlich", 1, s).typ == "div_ohne_rest"
        assert gen("div_schriftlich", 2, s).typ == "div_ohne_rest"
        assert gen("div_schriftlich", 3, s).typ == "div_mit_rest"


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k6_brueche_sind_am_ende_gekuerzt_und_eindeutig(seed):
    for d in STUFEN:
        k = gen("bruch_kuerzen", d, seed)
        z, n = k.parameter["zaehler"], k.parameter["nenner"]
        assert gcd(z, n) > 1 and z != n  # die Aufgabe ist wirklich zu kürzen
        soll = zahl(k)
        assert soll == Fraction(z, n) and soll.denominator > 1  # kein Ganzes
        assert k.loesung.kuerzen and k.loesung.anzeige == f"{soll.numerator}/{soll.denominator}"
        e = gen("bruch_erweitern", d, seed)
        p = e.parameter
        assert zahl(e) == p["zaehler"] * (p["neuer_nenner"] // p["nenner"])
        assert p["neuer_nenner"] % p["nenner"] == 0 and gcd(p["zaehler"], p["nenner"]) == 1
        s = gen("bruch_addsub", d, seed)
        (az, an), (bz, bn) = s.parameter["a"], s.parameter["b"]
        a, b = Fraction(az, an), Fraction(bz, bn)
        ziel = a + b if s.parameter["op"] == "+" else a - b
        assert zahl(s) == ziel > 0
        assert s.loesung.kuerzen and f"{az}/{an}" in s.text and f"{bz}/{bn}" in s.text
        if d <= 3:
            assert an == bn
        if d == 4:
            assert max(an, bn) % min(an, bn) == 0 and an != bn
        if d == 5:
            assert an != bn and max(an, bn) % min(an, bn) != 0


def test_k6_bruch_addsub_stufe_3_ergibt_unechte_brueche():
    for s in range(60):
        a = gen("bruch_addsub", 3, s)
        assert zahl(a) > 1


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k6_dezimalzahlen_sind_exakt(seed):
    for d in STUFEN:
        r = gen("dezimal_runden", d, seed)
        q, stelle = Fraction(r.parameter["zahl"]), r.parameter["stelle"]
        ergebnis = zahl(r)
        assert abs(ergebnis - q) <= Fraction(1, 2) * Fraction(10) ** (-stelle)
        assert (ergebnis * Fraction(10) ** stelle).denominator == 1  # auf die Stelle gerundet
        c = gen("dezimal_rechnen", d, seed)
        p = c.parameter
        if c.typ in ("dezimal_add", "dezimal_sub"):
            a, b = Fraction(p["a"]), Fraction(p["b"])
            assert zahl(c) == (a + b if p["op"] == "+" else a - b) > 0
        assert zahl(c) == wert_von(c.text) or c.typ == "dezimal_durch_ganz"
        assert stellen(zahl(c)) <= 3


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k6_prozent_und_groessen_geben_glatte_ergebnisse(seed):
    for d in STUFEN:
        a = gen("prozent_anteil", d, seed)
        assert zahl(a).denominator == 1 and 0 < zahl(a) < 100 and a.loesung.prozent
        w = gen("prozent_wert", d, seed)
        assert zahl(w) == Fraction(w.parameter["prozent"] * w.parameter["grundwert"], 100)
        assert zahl(w).denominator == 1 and zahl(w) > 0
        g = gen("groessen_umrechnen", d, seed)
        assert g.loesung.einheit and stellen(zahl(g)) <= 3 and zahl(g) > 0


def test_k6_prozentanteil_stimmt_gegen_grundwert():
    for s in range(100):
        a = gen("prozent_anteil", 4, s)
        if a.typ == "anteil_von_grundwert":
            assert zahl(a) * a.parameter["grundwert"] == 100 * a.parameter["anteil"]


def test_k6_groessen_einheiten_stimmen():
    faktor = {
        ("m", "cm"): 100,
        ("cm", "m"): Fraction(1, 100),
        ("kg", "g"): 1000,
        ("g", "kg"): Fraction(1, 1000),
    }
    for s in range(200):
        a = gen("groessen_umrechnen", 2, s)
        p = a.parameter
        f = faktor.get((p["von"], p["nach"]))
        if f is not None:
            assert zahl(a) == Fraction(p["wert"]) * f
        assert a.loesung.einheit == p["nach"]


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k6_punkt_vor_strich_und_klammern_ganzzahlig_und_nicht_negativ(seed):
    for d in STUFEN:
        for schluessel in ("punkt_vor_strich", "klammern"):
            a = gen(schluessel, d, seed)
            soll = wert_von(a.text)
            assert zahl(a) == soll and soll.denominator == 1 and soll >= 0
    a = gen("punkt_vor_strich", 3, seed)
    assert " : " in a.text and "(" not in a.text  # Punktrechnung ohne Klammern


def test_k6_klammer_division_geht_auf_und_vorteilhaft_ist_wirklich_rund():
    for s in range(100):
        k = gen("klammern", 3, s)
        assert (k.parameter["a"] + k.parameter["x"]) % k.parameter["c"] == 0
        v = gen("klammern", 4, s)
        assert "vorteilhaft" in v.typ and "Rechne vorteilhaft" in v.text


# --- Klasse 8 -------------------------------------------------------------------------------------


def _gleichung_hat_loesung(text, x):
    links, rechts = text.split("=")
    return poly_wert(links, x=x) == poly_wert(rechts, x=x)


@given(seed=SEEDS)
@settings(max_examples=100, deadline=None)
def test_k8_gleichungen_haben_genau_eine_ganzzahlige_loesung(seed):
    for d in STUFEN:
        a = gen("gleichung_linear", d, seed)
        x = zahl(a)
        assert x.denominator == 1 and a.loesung.form == "gleichung"
        gleichung = a.parameter["gleichung"]
        assert _gleichung_hat_loesung(gleichung, x)
        # genau eine Lösung: links minus rechts ist in x linear und nicht konstant
        links, rechts = gleichung.split("=")
        f = lambda v, li=links, re_=rechts: poly_wert(li, x=v) - poly_wert(re_, x=v)  # noqa: E731
        steigung = f(Fraction(1)) - f(Fraction(0))
        assert steigung != 0 and f(x) == 0 and f(x + 1) != 0
        assert a.loesung.anzeige == f"x = {str(x).replace('-', '−')}"


@given(seed=SEEDS)
@settings(max_examples=100, deadline=None)
def test_k8_terme_stimmen_an_vielen_stellen(seed):
    for d in STUFEN:
        for schluessel in ("term_zusammenfassen", "term_ausmultiplizieren"):
            a = gen(schluessel, d, seed)
            quelle, ergebnis = a.parameter["term"], a.loesung.anzeige
            for x, y in ((0, 0), (1, 2), (-3, 5), (7, -2), (11, 13)):
                werte = {"x": x, "a": x, "b": y}
                assert poly_wert(quelle, **werte) == poly_wert(ergebnis, **werte), (
                    quelle,
                    ergebnis,
                )
            assert a.loesung.vereinfacht
            # schon die Aufgabe selbst ist nicht fertig vereinfacht
            assert not antwort.pruefen(quelle, a.loesung).richtig


def test_k8_ausmultiplizieren_arbeitet_nicht_mit_nullkoeffizienten_in_der_loesung():
    for s in range(100):
        for d in STUFEN:
            p = term.lesen(gen("term_ausmultiplizieren", d, s).loesung.term)
            assert p and all(c != 0 for c in p.values())


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k8_prozent_zinsen_und_dreisatz_haben_hoechstens_zwei_nachkommastellen(seed):
    for d in STUFEN:
        for schluessel in ("prozent_rechnen", "zinsen", "dreisatz_proportional"):
            a = gen(schluessel, d, seed)
            assert zahl(a) > 0 and stellen(zahl(a)) <= 2, (a.text, a.loesung.anzeige)
        t = gen("dreisatz_antiproportional", d, seed)
        p = t.parameter
        assert p["n1"] != p["n2"] and p["n1"] * p["t1"] == p["gesamt"]
        assert zahl(t) * p["n2"] == p["gesamt"] and zahl(t).denominator == 1
        s = gen("dreisatz_proportional", d, seed)
        assert zahl(s) == s.parameter["n2"] * Fraction(s.parameter["einheitswert"])
        assert s.parameter["n1"] != s.parameter["n2"]


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k8_prozent_und_zinsen_stimmen_gegen_die_formel(seed):
    for d in STUFEN:
        a = gen("prozent_rechnen", d, seed)
        p = a.parameter
        if a.typ == "prozentwert":
            assert zahl(a) == Fraction(p["grundwert"] * p["prozent"], 100)
        elif a.typ == "prozentsatz":
            assert zahl(a) == p["prozent"]
        elif a.typ == "grundwert":
            assert zahl(a) == p["grundwert"]
        elif a.typ == "rabatt":
            assert zahl(a) == Fraction(p["grundwert"] * (100 - p["prozent"]), 100)
        elif a.typ == "mehrwertsteuer":
            assert zahl(a) == Fraction(p["netto"] * 119, 100)
        else:
            assert a.typ == "aenderung_prozent" and zahl(a) == p["prozent"]
        z = gen("zinsen", d, seed)
        p = z.parameter
        k = p["kapital"]
        if z.typ == "jahreszinsen":
            assert zahl(z) == Fraction(k * p["prozent"], 100)
        elif z.typ == "jahreszinsen_dezimal":
            assert zahl(z) == k * Fraction(p["prozent"]) / 100
        elif z.typ == "zinssatz":
            assert zahl(z) == p["prozent"]
        elif z.typ == "kapital":
            assert zahl(z) == k
        elif z.typ == "monatszinsen":
            assert zahl(z) == Fraction(k * p["prozent"] * p["monate"], 1200)
        else:
            assert z.typ == "zinseszins"
            assert zahl(z) == k * Fraction(100 + p["prozent"], 100) ** 2


@given(seed=SEEDS)
@settings(max_examples=80, deadline=None)
def test_k8_potenzen_wurzeln_und_negative_zahlen(seed):
    for d in STUFEN:
        for schluessel in ("potenzen", "wurzeln", "negative_zahlen"):
            a = gen(schluessel, d, seed)
            if a.typ == "quadrat_umkehren":
                assert zahl(a) ** 2 == a.parameter["quadrat"] and zahl(a) > 0
                continue
            assert zahl(a) == wert_von(a.text), (a.text, a.loesung.anzeige)
            assert stellen(zahl(a)) <= 1
    assert zahl(gen("wurzeln", 3, seed)) * 10 == int(zahl(gen("wurzeln", 3, seed)) * 10)


def test_k8_negative_zahlen_haben_negative_ergebnisse_und_schreiben_minus():
    ergebnisse = [zahl(gen("negative_zahlen", d, s)) for d in STUFEN for s in range(60)]
    assert min(ergebnisse) < 0 < max(ergebnisse)
    a = gen("negative_zahlen", 2, 3)
    assert zahl(a) < 0 and a.loesung.anzeige.startswith("−")
    assert antwort.pruefen("-" + a.loesung.anzeige[1:], a.loesung).richtig  # ASCII-Minus geht auch


def test_k3_ergebnisse_sind_nie_negativ():
    for schluessel in ALLE:
        if registry.holen(schluessel).klassenstufe != 3:
            continue
        for d in STUFEN:
            for s in range(80):
                assert zahl(gen(schluessel, d, s)) >= 0


def test_k3_und_k6_haben_keine_krummen_ergebnisse_ausser_gewollt():
    dezimal_erlaubt = {"geld", "dezimal_rechnen", "dezimal_runden", "groessen_umrechnen"}
    for g in registry.alle().values():
        if g.klassenstufe == 8:
            continue
        for d in STUFEN:
            for s in range(60):
                a = gen(g.schluessel, d, s)
                if (
                    g.schluessel in dezimal_erlaubt
                    or a.typ in ("div_dezimal", "kuerzen")
                    or g.schluessel in ("bruch_addsub",)
                ):
                    continue
                assert zahl(a).denominator == 1, (g.schluessel, a.text)
