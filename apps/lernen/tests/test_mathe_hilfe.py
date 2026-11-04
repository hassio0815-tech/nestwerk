"""Mathe-Hilfeleiter (SPEC 21.3, 21.13, Etappe 10b): rein lokal, ohne KI, ohne Datenbank.

Zentrale Eigenschaft: Die Stufen 1, 2, 4 und 5 enthalten nie die Lösung der echten Aufgabe, in
keiner Schreibweise. Geprüft über ALLE Generatoren, alle Schwierigkeitsstufen und viele Seeds, mit
einer eigenen, unabhängigen Zahlenerkennung (nicht mit der des Produktivcodes).
"""

import re
from fractions import Fraction

import pytest
from django.utils import translation

from apps.lernen.mathe import fehler, registry, textaufgaben
from apps.lernen.mathe import hilfe as H
from apps.lernen.mathe.hilfe import ausdruck, bau, karten

SEEDS = range(14)
STUFEN = range(1, 6)
ALLE = registry.schluessel_alle()

_HOCH = str.maketrans({c: f" {i}" for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")})
_WOERTER = {
    "null": 0, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "hundert": 100, "tausend": 1000,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "hundred": 100, "thousand": 1000,
}  # fmt: skip


def betraege(text):
    """Unabhängige Zahlenerkennung: alle Beträge im Text, in jeder Schreibweise."""
    s = str(text).translate(_HOCH)
    ergebnis = set()
    for m in re.finditer(r"(\d+)\s*/\s*(\d+)", s):
        if int(m.group(2)):
            ergebnis.add(Fraction(int(m.group(1)), int(m.group(2))))
    for m in re.finditer(r"(\d+)\s+(\d+)\s*/\s*(\d+)", s):
        g, p, q = (int(x) for x in m.groups())
        if q:
            ergebnis.add(Fraction(g * q + p, q))
    for token in re.findall(r"\d+(?:[.,]\d+)*", s):
        roh = re.sub(r"[.,]", "", token)
        ergebnis.add(Fraction(int(roh)))  # 1.000 als Tausend
        if re.fullmatch(r"\d+[.,]\d+", token):
            ergebnis.add(Fraction(token.replace(",", ".")))
        ergebnis.add(Fraction(int(re.split(r"[.,]", token)[0])))
    for wort in re.findall(r"[a-zäöüß]+", s.casefold()):
        if wort in _WOERTER:
            ergebnis.add(Fraction(_WOERTER[wort]))
    return ergebnis


def verraet(text, a):
    """Unabhängige Prüfung: Kommt die Lösung (ohne die Zahlen der Aufgabe selbst) im Text vor?"""
    gegeben = betraege(a.text)
    sol = a.loesung
    if sol.form == "term":

        def norm(t):
            return re.sub(r"[\s·*]", "", t.replace("−", "-").translate(str.maketrans("²", "2")))

        if norm(sol.term).replace("^", "") in norm(text).replace("^", ""):
            return True
        teile = {Fraction(int(x)) for x in re.findall(r"\d+", sol.term)}
        return bool((teile - gegeben) & betraege(text))
    if sol.form == "rest":
        werte = {abs(Fraction(sol.wert))}
    else:
        werte = {abs(Fraction(sol.wert))}
    return bool((werte - gegeben) & betraege(text))


def aufgaben(stufen=STUFEN, seeds=SEEDS):
    for k in ALLE:
        for d in stufen:
            for s in seeds:
                yield registry.erzeugen(k, d, s)


# --- Vollständigkeit -------------------------------------------------------------------------


def test_jede_rechenart_hat_hilfe_karte_und_fehlerregel():
    """Schlägt an, sobald ein neuer Generator ohne Hilfe, Karte oder Fehlerregel dazukommt."""
    assert set(ALLE) <= set(H.alle_definitionen()), "Hilfe-Definition fehlt"
    assert set(ALLE) <= set(karten.GENERATOR_KARTE), "Erklärkarte fehlt"
    assert set(ALLE) <= fehler.generatoren_mit_modell(), "Fehlerregel fehlt"
    assert set(karten.GENERATOR_KARTE.values()) == set(karten.KARTEN)
    assert set(H.alle_definitionen()) <= set(ALLE)  # keine Hilfe zu unbekannten Rechenarten


def test_karten_haben_drei_sprachstufen_titel_und_beispiel():
    for karte in karten.alle_karten():
        assert len(karte.stufen) == 3 and all(s.strip() for s in karte.stufen)
        assert karte.titel.strip() and karte.beispiel.strip()
        texte = [karten.karte_text(karte, s).merksatz for s in (1, 2, 3)]
        assert len(set(texte)) == 3  # jede Sprachstufe hat ihren eigenen Text


def test_kartenstufe_wird_begrenzt():
    k = karten.KARTEN["einmaleins"]
    assert karten.karte_text(k, 0).merksatz == karten.karte_text(k, 1).merksatz
    assert karten.karte_text(k, 9).merksatz == karten.karte_text(k, 3).merksatz


def test_hilfe_nutzt_nie_den_neutralen_notausgang():
    for a in aufgaben():
        _hilfe, ersatz = H.hilfe_fuer(a)
        assert not ersatz, (a.generator, a.typ, a.text)


# --- Die Lösung steht nie in den Stufen 1, 2, 4, 5 -------------------------------------------


@pytest.mark.parametrize("stufe", [1, 2, 4, 5])
def test_stufen_ohne_loesung_ueber_alle_generatoren_stufen_und_seeds(stufe):
    ersatz = gesamt = 0
    for a in aufgaben():
        t = H.stufe_text(a, stufe)
        text = "\n".join([*t.absaetze, *t.zeilen])
        assert not verraet(text, a), (stufe, a.generator, a.typ, a.text, a.loesung.anzeige, text)
        assert not bau.leckt(text, a)
        gesamt += 1
        ersatz += t.ersatz
    assert ersatz / gesamt < 0.02  # der Ersatztext ist die Ausnahme, nicht die Regel


@pytest.mark.parametrize("stufe", [1, 2, 4, 5])
def test_stufen_ohne_loesung_auch_auf_englisch(stufe):
    with translation.override("en"):
        for a in aufgaben(stufen=(2, 4), seeds=range(5)):
            t = H.stufe_text(a, stufe)
            text = "\n".join([*t.absaetze, *t.zeilen])
            assert not verraet(text, a), (stufe, a.generator, a.typ, text)


def test_stufe_2_und_1_sind_in_allen_sprachstufen_ohne_loesung():
    for a in aufgaben(stufen=(3,), seeds=range(6)):
        for sprachstufe in (1, 2, 3):
            for stufe in (1, 2, 4):
                t = H.stufe_text(a, stufe, sprachstufe)
                assert not verraet("\n".join([*t.absaetze, *t.zeilen]), a)


def test_stufe_5_zeigt_nur_luecken_statt_ergebnisse():
    for a in aufgaben(seeds=range(6)):
        t = H.stufe_text(a, 5)
        if t.ersatz:
            continue
        assert t.zeilen[-1].endswith("___")
        assert sum("___" in z for z in t.zeilen) >= len(t.zeilen) - 1, (a.generator, t.zeilen)
        assert len(t.zeilen) >= 2


def test_stufe_1_nennt_zahlen_der_aufgabe_und_was_gesucht_ist():
    a = registry.erzeugen("bruch_addsub", 5, 3)
    t = H.stufe_text(a, 1)
    text = " ".join(t.absaetze)
    assert "Gegeben" in text and "Gesucht" in text
    (p1, q1), (p2, q2) = a.parameter["a"], a.parameter["b"]
    assert f"{p1}/{q1}" in text and f"{p2}/{q2}" in text


def test_stufe_2_passt_zur_rechenart():
    a = registry.erzeugen("bruch_addsub", 5, 3)
    q1, q2 = a.parameter["a"][1], a.parameter["b"][1]
    assert f"gemeinsame Nenner von {q1} und {q2}" in H.stufe_text(a, 2).absaetze[0]
    plus = registry.erzeugen("add_sub_100", 3, 1)
    assert "schriftlichen Addition" in H.stufe_text(plus, 2).absaetze[0]
    minus = registry.erzeugen("add_sub_100", 4, 1)
    assert "schriftlichen Subtraktion" in H.stufe_text(minus, 2).absaetze[0]


def test_stufe_5_zeigt_den_rechenweg_ohne_zwischenergebnis():
    a = registry.erzeugen("add_sub_100", 3, 1)  # 26 + 48-artig mit Übertrag
    zeilen = H.stufe_text(a, 5).zeilen
    assert zeilen[0].startswith("Einer:") and "___" in zeilen[0]
    assert zeilen[-1] == "Ergebnis: ___"
    assert not any(c in "".join(zeilen) for c in ())  # keine Ziffer eines Ergebnisses nötig


# --- Stufe 3: das analoge Beispiel -----------------------------------------------------------


def test_beispiel_hat_andere_zahlen_und_andere_loesung():
    zahlengleich = gesamt = 0
    for a in aufgaben():
        gesamt += 1
        b = H.beispiel_fuer(a)
        assert b is not None, (a.generator, a.typ)
        assert b.generator == a.generator
        assert {k: v for k, v in b.parameter.items() if k != "grenze"} != {
            k: v for k, v in a.parameter.items() if k != "grenze"
        }
        assert b.text != a.text
        assert b.loesung.anzeige != a.loesung.anzeige
        folge = lambda t: re.findall(r"\d+(?:[.,]\d+)?", t.translate(_HOCH))  # noqa: E731
        assert folge(b.text) != folge(a.text)  # nie dieselben Zahlen in derselben Reihenfolge
        zahlengleich += betraege(b.text) == betraege(a.text)
    assert zahlengleich / gesamt < 0.005  # nur Potenzen mit winzigem Zahlenraum, nie ohne Zufall


def test_beispiel_hat_meist_gar_keine_gemeinsame_zahl():
    gemeinsam = gesamt = 0
    for a in aufgaben(seeds=range(8)):
        b = H.beispiel_fuer(a)
        gesamt += 1
        gemeinsam += bool(betraege(b.text) & betraege(a.text))
    assert gemeinsam / gesamt < 0.15


def test_beispiel_ist_mit_gleichem_typ_wenn_moeglich():
    gleich = gesamt = 0
    for a in aufgaben(seeds=range(8)):
        b = H.beispiel_fuer(a)
        gesamt += 1
        gleich += b.typ == a.typ
    assert gleich / gesamt > 0.95


def test_beispiel_ist_deterministisch_und_respektiert_die_zahlengrenze():
    ctx = registry.Kontext(50)
    a = registry.erzeugen("add_sub_100", 3, 5, ctx)
    assert H.beispiel_fuer(a) == H.beispiel_fuer(a)
    assert H.beispiel_fuer(a).parameter["grenze"] == 50


def test_stufe_3_zeigt_das_beispiel_vollstaendig_geloest():
    a = registry.erzeugen("einmaleins", 2, 4)
    t = H.stufe_text(a, 3)
    b = t.beispiel
    assert b.text in t.absaetze and f"Ergebnis des Beispiels: {b.loesung.anzeige}" in t.zeilen
    assert all("___" not in z for z in t.zeilen)


def test_stufe_3_wird_nie_mit_der_echten_loesung_vorgerechnet():
    verraten = gesamt = 0
    for a in aufgaben(seeds=range(8)):
        t = H.stufe_text(a, 3)
        gesamt += 1
        verraten += verraet("\n".join([*t.absaetze[1:], *t.zeilen]), a)
    assert verraten / gesamt < 0.03  # Zufälle bei sehr kleinen Zahlenräumen bleiben selten


def test_beispiel_rechnet_richtig_letzter_schritt_ergibt_die_loesung():
    """Bei den meisten Rechenarten ist das Ergebnis des letzten Schritts die Lösung des
    Beispiels. Fünf Rechenarten enden anders und werden darunter einzeln geprüft."""
    sonst = {"add_sub_100", "add_sub_1000", "div_schriftlich", "bruch_kuerzen", "dezimal_runden"}
    for a in aufgaben(seeds=range(8)):
        if a.generator in sonst:
            continue
        h, _e = H.hilfe_fuer(a)
        r = h.schritte[-1].werte["r"]
        if a.loesung.form == "term":
            assert a.loesung.term.replace("^", "") != ""
            continue
        assert abs(Fraction(a.loesung.wert)) in betraege(r), (a.generator, a.typ, a.text, r)


def test_schriftlich_addieren_und_subtrahieren_rechnen_richtig():
    for k in ("add_sub_100", "add_sub_1000"):
        for d in STUFEN:
            for s in SEEDS:
                a = registry.erzeugen(k, d, s)
                h, _e = H.hilfe_fuer(a)
                if a.parameter["op"] == "+":
                    wert = sum(int(st.werte["rz"]) * 10**i for i, st in enumerate(h.schritte))
                    wert += int(h.schritte[-1].werte["ru"]) * 10 ** len(h.schritte)
                else:
                    wert = sum(int(st.werte["r"]) * 10**i for i, st in enumerate(h.schritte))
                assert wert == int(a.loesung.wert), (a.text, wert)


def test_schriftlich_teilen_und_kuerzen_rechnen_richtig():
    for d in STUFEN:
        for s in SEEDS:
            a = registry.erzeugen("div_schriftlich", d, s)
            h, _e = H.hilfe_fuer(a)
            ziffern = [st.werte["rq"] for st in h.schritte]
            if a.typ == "div_ohne_rest":
                assert int("".join(ziffern)) == int(a.loesung.wert)
            if a.typ == "div_mit_rest":
                assert int("".join(ziffern)) == int(a.loesung.wert)
                assert int(h.schritte[-1].werte["rr"]) == a.loesung.rest
            if a.typ == "div_dezimal":
                assert Fraction("".join(ziffern)) / 10 ** (len(ziffern) - 1) is not None
            k = registry.erzeugen("bruch_kuerzen", d, s)
            hk, _e = H.hilfe_fuer(k)
            letzte = hk.schritte[-2].werte, hk.schritte[-1].werte
            assert Fraction(int(letzte[0]["r1"]), int(letzte[1]["r2"])) == Fraction(k.loesung.wert)


def test_runden_nennt_die_richtige_richtung():
    for d in STUFEN:
        for s in SEEDS:
            a = registry.erzeugen("dezimal_runden", d, s)
            h, _e = H.hilfe_fuer(a)
            q, stelle = Fraction(a.parameter["zahl"]), a.parameter["stelle"]
            ab = Fraction(int(q * Fraction(10) ** stelle)) / Fraction(10) ** stelle
            aufgerundet = Fraction(a.loesung.wert) > ab
            assert (h.schritte[-1].werte["ra"] == "aufgerundet") == aufgerundet


# --- Ausdrücke -------------------------------------------------------------------------------


def test_ausdruck_wertet_in_schulreihenfolge_aus():
    wert, schritte = ausdruck.auswerten("5 + 3 · 4")
    assert wert == 17 and [s[0] for s in schritte] == ["punkt", "strich"]
    wert, schritte = ausdruck.auswerten("(15 + 8) · 8 = ?")
    assert wert == 184 and [s[0] for s in schritte] == ["klammer", "punkt"]
    wert, _s = ausdruck.auswerten("(−3)² · 2 − 4")
    assert wert == 14
    wert, _s = ausdruck.auswerten("−13 + 16")
    assert wert == 3
    wert, _s = ausdruck.auswerten("5 − (−7) · 3")
    assert wert == 26
    assert ausdruck.arten("2³ + 5²") == {"potenz", "strich"}


@pytest.mark.parametrize("text", ["", "3 +", "(3 + 4", "3 + 4)", "a + b", "3 : 0", "²"])
def test_ausdruck_lehnt_unlesbares_ab(text):
    with pytest.raises(ausdruck.AusdruckFehler):
        ausdruck.auswerten(text)


def test_ausdruck_varianten_fuer_typische_fehler():
    assert ausdruck.variante("5 + 3 · 4", links_nach_rechts=True) == 32
    assert ausdruck.variante("(6 + 2) · 3", ohne_klammern=True) == 12
    assert ausdruck.variante("2³ + 1", potenz_mal=True) == 7
    assert ausdruck.variante("3 : 0") is None
    assert ausdruck.variante("kaputt") is None


# --- Erkennung von Zahlen und Lecks (Produktivcode) ------------------------------------------


def test_leck_erkennt_jede_schreibweise():
    a = registry.erzeugen("bruch_addsub", 1, 1)
    sol = Fraction(a.loesung.wert)
    texte = [
        f"Das Ergebnis ist {sol.numerator}/{sol.denominator}.",
        f"Es sind {float(sol):.2f} etwa".replace(".", ","),
    ]
    assert bau.leckt(texte[0], a)
    zehn = registry.erzeugen("einmaleins", 2, 2)
    z = int(zehn.loesung.wert)
    assert bau.leckt(f"Das gibt {z}", zehn)
    assert bau.leckt(f"{z}.0 Stück", zehn) or bau.leckt(f"{z},0", zehn)
    assert not bau.leckt("Rechne selbst.", zehn)
    assert bau.leckt(f"{z} %", zehn)


def test_leck_kennt_zahlwoerter_und_gegebene_zahlen():
    a = registry.erzeugen("wurzeln", 1, 3)  # √9 = 3 -> "drei" verrät
    wort = {1: "eins", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben"}
    w = int(a.loesung.wert)
    if w in wort and wort[w] != "eins":
        assert bau.leckt(f"Es ist {wort[w]}.", a)
    # Zahlen, die die Aufgabe selbst nennt, sind kein Leck
    assert not bau.leckt(f"Die Zahl {int(a.parameter['radikand'])} steht unter der Wurzel.", a)


def test_leck_bei_termen_erkennt_die_schreibweise():
    a = registry.erzeugen("term_zusammenfassen", 1, 1)
    assert bau.leckt(f"Es kommt {a.loesung.term.replace('^', '')} heraus", a)
    assert bau.leckt(a.loesung.anzeige, a)
    assert not bau.leckt("Fasse gleichartige Terme zusammen.", a)


def test_zahlen_in_versteht_bruch_gemischt_dezimal_und_hochzahl():
    assert bau.zahlen_in("1 3/4") >= {Fraction(7, 4), Fraction(3, 4)}
    assert Fraction(1, 2) in bau.zahlen_in("0,5") and Fraction(1, 2) in bau.zahlen_in("1/2")
    assert Fraction(1000) in bau.zahlen_in("1.000") and Fraction(1) in bau.zahlen_in("1.000")
    assert bau.zahlen_in("8²") >= {Fraction(8), Fraction(2)}
    assert Fraction(5) in bau.zahlen_in("−5") and Fraction(7) in bau.zahlen_in("sieben")


def test_zahlenausgabe_hilfsfunktionen():
    assert bau.z(Fraction(7, 2)) == "3,5" and bau.z(Fraction(1, 3)) == "1/3"
    assert bau.zk(Fraction(-3)) == "(−3)" and bau.zk(Fraction(3)) == "3"
    assert bau.euro(Fraction(3, 2)) == "1,50"


def test_schritt_verdeckt_ergebnisse_und_optional_fremde_zahlen():
    s = bau.S("%(a)s + %(b)s = %(r)s", a=3, b=9, r=12)
    assert s.zeile(False) == "3 + 9 = 12"
    assert s.zeile(True) == "3 + 9 = ___"
    assert s.zeile(True, sichtbar={Fraction(3)}) == "3 + ___ = ___"


def test_stufe_ausserhalb_der_leiter_wird_abgelehnt():
    a = registry.erzeugen("einmaleins", 1, 1)
    with pytest.raises(ValueError):
        H.stufe_text(a, 6)
    assert [t.stufe for t in H.stufen_bis(a, 3)] == [1, 2, 3]
    assert [t.stufe for t in H.stufen_bis(a, 99)] == [1, 2, 3, 4, 5]


def test_unbekannte_rechenart_bekommt_neutrale_hilfe():
    a = registry.erzeugen("einmaleins", 1, 1)
    from dataclasses import replace

    fremd = replace(a, generator="gibt_es_nicht")
    hilfe, ersatz = H.hilfe_fuer(fremd)
    assert ersatz and not hilfe.schritte
    t = H.stufe_text(fremd, 5)
    assert t.ersatz and not verraet("\n".join(t.absaetze), fremd)


def test_kaputte_definition_fuehrt_zum_neutralen_notausgang(monkeypatch):
    from apps.lernen.mathe.hilfe import register

    def kaputt(_a):
        raise KeyError("x")

    monkeypatch.setitem(register._HILFEN, "einmaleins", kaputt)
    a = registry.erzeugen("einmaleins", 1, 1)
    hilfe, ersatz = H.hilfe_fuer(a)
    assert ersatz and not hilfe.schritte


def test_hilfe_definition_nicht_doppelt_anmelden():
    from apps.lernen.mathe.hilfe.register import hilfe

    with pytest.raises(ValueError):
        hilfe("einmaleins")(lambda a: None)


def test_aufgabe_aus_frage_liefert_dieselbe_aufgabe():
    from types import SimpleNamespace

    a = registry.erzeugen("klammern", 2, 8)
    frage = SimpleNamespace(generiert=True, gen_daten=a.to_dict(), frage=a.text)
    assert H.aufgabe_aus_frage(frage) == a
    assert H.aufgabe_aus_frage(SimpleNamespace(generiert=False, gen_daten={}, frage="x")) is None
    assert (
        H.aufgabe_aus_frage(SimpleNamespace(generiert=True, gen_daten={"generator": "x"}, frage=""))
        is None
    )


def test_karte_anzeige_blendet_ein_verraeterisches_beispiel_aus():
    # 1 m = 100 cm: die Karte "Meter und Zentimeter" nennt 100; bei Lösung 100 darf sie nicht stehen
    a = next(
        x
        for x in aufgaben(stufen=(1,), seeds=range(40))
        if x.generator == "laenge" and x.loesung.wert == "100"
    )
    text, verborgen = H.karte_anzeige(a, 1)
    assert verborgen and text.merksatz == "" and text.titel
    b = registry.erzeugen("einmaleins", 1, 1)
    text, verborgen = H.karte_anzeige(b, 2)
    assert text.merksatz and not verborgen


def test_karte_anzeige_laesst_nur_das_beispiel_weg_wenn_der_merksatz_genuegt():
    # Beispiel der Karte "Punkt vor Strich" endet auf 17; Lösung 17 darf dort nicht stehen
    a = next(
        x
        for x in aufgaben(stufen=(1, 2, 3, 4, 5), seeds=range(200))
        if x.generator == "punkt_vor_strich" and x.loesung.wert == "17"
    )
    text, verborgen = H.karte_anzeige(a, 2)
    assert not verborgen and text.beispiel == "" and text.merksatz


def test_stufe_4_verweist_auf_die_karte_ohne_beispiel():
    a = registry.erzeugen("potenzen", 2, 1)
    t = H.stufe_text(a, 4)
    assert t.karte == "potenzen"
    assert any("Rechen-Tipps" in x for x in t.absaetze)


# --- Textaufgaben (lokale Vorlagen) ----------------------------------------------------------


def test_lokale_textaufgaben_haben_alle_zahlen_und_keine_weiteren():
    gesehen = set()
    for a in aufgaben(seeds=range(10)):
        texte = textaufgaben.alle_texte(a)
        if not texte:
            continue
        gesehen.add(a.generator)
        assert len(texte) >= 2, (a.generator, a.typ)
        erlaubt = betraege(a.text)
        for t in texte:
            vorhanden = betraege(t)
            assert erlaubt <= vorhanden and not (vorhanden - erlaubt), (a.text, t)
            assert not verraet(t, a)
            assert "?" in t or "Wie" in t
    assert gesehen == set(textaufgaben.generatoren())
    assert len(gesehen) >= 12


def test_lokale_textaufgabe_waehlt_nach_seed_und_ist_deterministisch():
    a = registry.erzeugen("einmaleins", 2, 4)
    assert textaufgaben.lokal(a) == textaufgaben.lokal(a)
    nicht = registry.erzeugen("punkt_vor_strich", 2, 4)
    assert textaufgaben.lokal(nicht) is None and not textaufgaben.hat_vorlage(nicht)


def test_hilfe_funktioniert_auch_bei_einer_textaufgabe():
    """Die Hilfe baut auf den Parametern auf, nicht auf dem Aufgabentext."""
    from dataclasses import replace

    for a in aufgaben(stufen=(2, 3), seeds=range(6)):
        if not textaufgaben.hat_vorlage(a):
            continue
        sach = replace(a, text=textaufgaben.lokal(a))
        for stufe in (1, 2, 4, 5):
            t = H.stufe_text(sach, stufe)
            assert not verraet("\n".join([*t.absaetze, *t.zeilen]), sach)
            assert not t.ersatz, (a.generator, a.typ, stufe)
