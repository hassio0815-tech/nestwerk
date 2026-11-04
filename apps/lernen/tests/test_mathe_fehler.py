"""Fehleranalyse (SPEC 21.13, Etappe 10b): erkennt typische Rechenfehler regelbasiert, ohne KI, und
gibt einen Hinweis, der nie die Lösung nennt. Konstruierte falsche Antworten je Fehlertyp."""

import re
from fractions import Fraction

import pytest
from django.utils import translation

from apps.lernen import pruefung
from apps.lernen.mathe import bausteine, fehler, registry
from apps.lernen.mathe.aufgabe import Aufgabe
from apps.lernen.tests.test_mathe_hilfe import aufgaben, verraet

ALLE = registry.schluessel_alle()
ALLGEMEIN = {"um_eins", "um_zehn", "komma", "zahlendreher", "vorzeichen"}
VON_ANTWORT = {"unlesbar", "einheit", "variable"}  # erkennt schon die Antwortprüfung


def mk(generator, typ, text, lsg, **parameter):
    g = registry.holen(generator)
    return Aufgabe(
        generator=generator,
        typ=typ,
        thema=g.thema,
        klassenstufe=g.klassenstufe,
        schwierigkeit=3,
        seed=0,
        text=text,
        loesung=lsg,
        parameter=parameter,
    )


def zahl(w, **kw):
    return bausteine.lsg_zahl(w, **kw)


def add(a, b):
    return mk("add_sub_100", "add_mit_uebertrag", f"{a} + {b} = ?", zahl(a + b), a=a, b=b, op="+")


def sub(a, b):
    return mk("add_sub_100", "sub_mit_borgen", f"{a} − {b} = ?", zahl(a - b), a=a, b=b, op="-")


# --- Je Fehlertyp ein konstruiertes Beispiel -------------------------------------------------

FAELLE = [
    (add(47, 38), "75", "uebertrag_vergessen"),
    (add(47, 38), "95", "uebertrag_doppelt"),
    (add(68, 57), "15", "uebertrag_vergessen"),  # alle Überträge vergessen: 8+7=15, 6+5=11 -> 11 5
    (sub(63, 29), "44", "entbuendeln_vergessen"),
    (sub(63, 29), "46", "kleinere_von_groesserer"),
    (
        mk("einmaleins", "einmaleins", "6 · 7 = ?", zahl(42), a=6, b=7),
        "48",
        "reihe_verrutscht",
    ),
    (
        mk("einmaleins", "einmaleins", "6 · 7 = ?", zahl(42), a=6, b=7),
        "13",
        "andere_rechenart",
    ),
    (
        mk(
            "mult_schriftlich", "mult_2x2", "Rechne schriftlich: 23 · 14 = ?", zahl(322), a=23, b=14
        ),
        "115",
        "nullen_vergessen",
    ),
    (
        mk(
            "div_schriftlich",
            "div_mit_rest",
            "Rechne schriftlich mit Rest: 69 : 4 = ?",
            bausteine.lsg_rest(17, 1),
            dividend=69,
            teiler=4,
        ),
        "17 R 5",
        "rest_zu_gross",
    ),
    (
        mk(
            "div_schriftlich",
            "div_mit_rest",
            "Rechne schriftlich mit Rest: 69 : 4 = ?",
            bausteine.lsg_rest(17, 1),
            dividend=69,
            teiler=4,
        ),
        "17 R 3",
        "rest_falsch",
    ),
    (
        mk(
            "div_schriftlich",
            "div_ohne_rest",
            "Rechne schriftlich: 408 : 4 = ?",
            zahl(102),
            dividend=408,
            teiler=4,
        ),
        "12",
        "null_vergessen",
    ),
    (
        mk(
            "bruch_kuerzen",
            "kuerzen",
            "Kürze vollständig: 12/18",
            bausteine.lsg_bruch(Fraction(2, 3)),
            zaehler=12,
            nenner=18,
        ),
        "2/18",
        "falsch_gekuerzt",
    ),
    (
        mk(
            "bruch_erweitern",
            "erweitern",
            "Erweitere auf den neuen Nenner: 2/3 = ?/12. Wie lautet der Zähler?",
            zahl(8),
            zaehler=2,
            nenner=3,
            neuer_nenner=12,
        ),
        "6",
        "addiert_statt_multipliziert",
    ),
    (
        mk(
            "bruch_addsub",
            "add_ungleichnamig",
            "Rechne und kürze: 1/4 + 1/6 = ?",
            bausteine.lsg_bruch(Fraction(5, 12)),
            a=[1, 4],
            b=[1, 6],
            op="+",
        ),
        "2/10",
        "nenner_mitgerechnet",
    ),
    (
        mk(
            "bruch_addsub",
            "add_ungleichnamig",
            "Rechne und kürze: 1/4 + 1/6 = ?",
            bausteine.lsg_bruch(Fraction(5, 12)),
            a=[1, 4],
            b=[1, 6],
            op="+",
        ),
        "2/24",
        "zaehler_nicht_erweitert",
    ),
    (
        mk(
            "dezimal_runden",
            "runden",
            "Runde 3,47 auf Zehntel.",
            zahl(Fraction(7, 2), stellen=1),
            zahl="347/100",
            stelle=1,
        ),
        "3,4",
        "auf_ab_verwechselt",
    ),
    (
        mk(
            "dezimal_runden",
            "runden",
            "Runde 3,47 auf Zehntel.",
            zahl(Fraction(7, 2), stellen=1),
            zahl="347/100",
            stelle=1,
        ),
        "3",
        "falsche_stelle",
    ),
    (
        mk(
            "dezimal_rechnen",
            "dezimal_add",
            "2,5 + 1,75 = ?",
            zahl(Fraction(17, 4)),
            a="5/2",
            b="7/4",
            op="+",
        ),
        "20",
        "kommas_nicht_untereinander",
    ),
    (
        mk(
            "prozent_wert",
            "prozentwert",
            "Berechne 25 % von 80.",
            zahl(20),
            prozent=25,
            grundwert=80,
        ),
        "2000",
        "hundert_vergessen",
    ),
    (
        mk(
            "prozent_rechnen",
            "rabatt",
            "Ein Pullover kostet 60 €. Im Angebot gibt es 20 % Rabatt. Wie viel kostet er jetzt?",
            zahl(48, einheit="€", stellen=2),
            grundwert=60,
            prozent=20,
        ),
        "12",
        "rabatt_nicht_abgezogen",
    ),
    (
        mk(
            "prozent_rechnen",
            "rabatt",
            "Ein Pullover kostet 60 €. Im Angebot gibt es 20 % Rabatt. Wie viel kostet er jetzt?",
            zahl(48, einheit="€", stellen=2),
            grundwert=60,
            prozent=20,
        ),
        "72",
        "rabatt_addiert",
    ),
    (
        mk(
            "prozent_rechnen",
            "mehrwertsteuer",
            "Eine Ware kostet netto 100 €. Dazu kommen 19 % Mehrwertsteuer. Wie hoch ist der "
            "Bruttopreis?",
            zahl(119, einheit="€", stellen=2),
            netto=100,
            prozent=19,
        ),
        "19",
        "steuer_nicht_addiert",
    ),
    (
        mk(
            "prozent_rechnen",
            "mehrwertsteuer",
            "Eine Ware kostet netto 100 €. Dazu kommen 19 % Mehrwertsteuer. Wie hoch ist der "
            "Bruttopreis?",
            zahl(119, einheit="€", stellen=2),
            netto=100,
            prozent=19,
        ),
        "81",
        "steuer_abgezogen",
    ),
    (
        mk(
            "prozent_rechnen",
            "prozentsatz",
            "Wie viel Prozent sind 15 von 60?",
            zahl(25, prozent=True),
            grundwert=60,
            prozent=25,
        ),
        "400",
        "prozent_umgedreht",
    ),
    (
        mk(
            "prozent_rechnen",
            "aenderung_prozent",
            "Ein Preis steigt von 40 € auf 50 €. Um wie viel Prozent ist er gestiegen?",
            zahl(25, prozent=True),
            alt=40,
            prozent=25,
        ),
        "10",
        "unterschied_nicht_in_prozent",
    ),
    (
        mk(
            "zinsen",
            "monatszinsen",
            "1200 € werden 6 Monate lang mit 3 % pro Jahr verzinst. Wie hoch sind die Zinsen?",
            zahl(18, einheit="€", stellen=2),
            kapital=1200,
            prozent=3,
            monate=6,
        ),
        "36",
        "monate_vergessen",
    ),
    (
        mk(
            "zinsen",
            "zinseszins",
            "500 € werden 2 Jahre lang mit 10 % pro Jahr verzinst (Zinseszins). Wie viel Geld ist "
            "es danach?",
            zahl(605, einheit="€", stellen=2),
            kapital=500,
            prozent=10,
            jahre=2,
        ),
        "600",
        "zinseszins_vergessen",
    ),
    (
        mk(
            "zinsen",
            "zinseszins",
            "500 € werden 2 Jahre lang mit 10 % pro Jahr verzinst (Zinseszins). Wie viel Geld ist "
            "es danach?",
            zahl(605, einheit="€", stellen=2),
            kapital=500,
            prozent=10,
            jahre=2,
        ),
        "105",
        "zinsen_statt_guthaben",
    ),
    (
        mk("punkt_vor_strich", "punkt_vor_strich_1", "5 + 3 · 4 = ?", zahl(17), term="5 + 3 · 4"),
        "32",
        "punkt_vor_strich_ignoriert",
    ),
    (
        mk("klammern", "klammer_mal", "(6 + 2) · 3 = ?", zahl(24), a=6, b=2, c=3),
        "12",
        "klammer_ignoriert",
    ),
    (
        mk("potenzen", "potenz", "2³ = ?", zahl(8), basis=2, hochzahl=3),
        "6",
        "mal_statt_hoch",
    ),
    (mk("wurzeln", "wurzel", "√36 = ?", zahl(6), radikand=36), "36", "wurzel_vergessen"),
    (mk("wurzeln", "wurzel", "√36 = ?", zahl(6), radikand=36), "18", "halbiert_statt_wurzel"),
    (
        mk(
            "wurzeln",
            "wurzel_pythagoras",
            "√(9 + 16) = ?",
            zahl(5),
            a=9,
            b=16,
        ),
        "7",
        "wurzel_einzeln",
    ),
    (
        mk("negative_zahlen", "minus_klammer_neg", "4 − (−2) = ?", zahl(6), term="4 − (−2)"),
        "2",
        "minus_in_klammer_vergessen",
    ),
    (
        mk("negative_zahlen", "neg_minus_pos", "−5 − 3 = ?", zahl(-8), term="−5 − 3"),
        "2",
        "vorzeichen_vorne_vergessen",
    ),
    (
        mk(
            "gleichung_linear",
            "plus",
            "Löse die Gleichung: x + 29 = 44",
            bausteine.lsg_gleichung(15),
            gleichung="x + 29 = 44",
            loesung=15,
        ),
        "x = 73",
        "gl_vorzeichen",
    ),
    (
        mk(
            "gleichung_linear",
            "mal",
            "Löse die Gleichung: 3x = 12",
            bausteine.lsg_gleichung(4),
            gleichung="3x = 12",
            loesung=4,
        ),
        "36",
        "gl_mal_statt_geteilt",
    ),
    (
        mk(
            "gleichung_linear",
            "mal_plus",
            "Löse die Gleichung: 2x + 3 = 11",
            bausteine.lsg_gleichung(4),
            gleichung="2x + 3 = 11",
            loesung=4,
        ),
        "8",
        "gl_nicht_geteilt",
    ),
    (
        mk(
            "gleichung_linear",
            "klammer",
            "Löse die Gleichung: 3(x + 2) = 15",
            bausteine.lsg_gleichung(3),
            gleichung="3(x + 2) = 15",
            loesung=3,
        ),
        "7",
        "gl_vorzeichen",
    ),
    (
        mk(
            "term_zusammenfassen",
            "zusammenfassen_2",
            "Fasse zusammen: 4x + 2 + 3x − 5",
            bausteine.lsg_term({(("x", 1),): Fraction(7), (): Fraction(-3)}),
            term="4x + 2 + 3x − 5",
        ),
        "4x",
        "ungleichartig",
    ),
    (
        mk(
            "term_ausmultiplizieren",
            "faktor_klammer",
            "Multipliziere aus und fasse zusammen: 3(x + 4)",
            bausteine.lsg_term({(("x", 1),): Fraction(3), (): Fraction(12)}),
            term="3(x + 4)",
        ),
        "3x + 4",
        "nur_erstes_multipliziert",
    ),
    (
        mk(
            "term_ausmultiplizieren",
            "zwei_klammern",
            "Multipliziere aus und fasse zusammen: (x + 2)(x + 5)",
            bausteine.lsg_term(
                {(("x", 2),): Fraction(1), (("x", 1),): Fraction(7), (): Fraction(10)}
            ),
            term="(x + 2)(x + 5)",
        ),
        "x² + 10",
        "mittelterme_vergessen",
    ),
    (
        mk(
            "dreisatz_proportional",
            "dreisatz_prop",
            "4 kg Äpfel kosten 6,00 €. Wie viel kosten 7 kg?",
            zahl(Fraction(21, 2), einheit="€", stellen=2),
            n1=4,
            n2=7,
            einheitswert="3/2",
            szenario=1,
        ),
        "1,5",
        "nur_einheit",
    ),
    (
        mk(
            "dreisatz_antiproportional",
            "dreisatz_anti",
            "3 Arbeiter brauchen für eine Arbeit 8 Tage. Wie viele Tage brauchen 6 Arbeiter?",
            zahl(4, einheit="Tage"),
            n1=3,
            n2=6,
            t1=8,
            gesamt=24,
            szenario=0,
        ),
        "24",
        "nur_gesamtaufwand",
    ),
    (
        mk(
            "groessen_umrechnen",
            "umrechnen",
            "3,5 kg = ? g",
            zahl(3500, einheit="g"),
            wert="7/2",
            von="kg",
            nach="g",
        ),
        "0,0035",
        "richtung_vertauscht",
    ),
    (
        mk(
            "geld",
            "euro_cent_in_cent",
            "3 € 20 ct = ? ct",
            zahl(320, einheit="ct"),
            euro=3,
            cent=20,
        ),
        "300",
        "umrechnung_vergessen",
    ),
    (
        mk("umkehr", "fehlender_faktor", "? · 6 = 42", zahl(7), faktor=6, produkt=42),
        "36",
        "andere_rechenart",
    ),
    (
        mk(
            "prozent_rechnen",
            "grundwert",
            "15 sind 25 % des Grundwerts. Wie groß ist der Grundwert?",
            zahl(60),
            grundwert=60,
            prozent=25,
        ),
        "3,75",
        "prozentwert_statt_grundwert",
    ),
    (
        mk(
            "prozent_rechnen",
            "aenderung_prozent",
            "Ein Preis steigt von 40 € auf 50 €. Um wie viel Prozent ist er gestiegen?",
            zahl(25, prozent=True),
            alt=40,
            prozent=25,
        ),
        "20",
        "falscher_grundwert",
    ),
    (
        mk(
            "dreisatz_proportional",
            "dreisatz_prop",
            "4 kg Äpfel kosten 6,00 €. Wie viel kosten 8 kg?",
            zahl(12, einheit="€", stellen=2),
            n1=4,
            n2=8,
            einheitswert="3/2",
            szenario=1,
        ),
        "3",
        "falsche_richtung",
    ),
    (
        mk(
            "gleichung_linear",
            "klammer",
            "Löse die Gleichung: 3(x + 2) = 15",
            bausteine.lsg_gleichung(3),
            gleichung="3(x + 2) = 15",
            loesung=3,
        ),
        "5",
        "gl_klammer",
    ),
]


@pytest.mark.parametrize(
    ("a", "eingabe", "erwartet"),
    FAELLE,
    ids=[f"{a.generator}-{e}-{t}" for a, e, t in FAELLE],
)
def test_konstruierte_fehler_werden_erkannt(a, eingabe, erwartet):
    typ = fehler.analysiere(a, eingabe)
    assert typ == erwartet
    hinweis = fehler.hinweis_text(typ, a)
    assert hinweis and hinweis != fehler.hinweis_text("neutral")
    assert not verraet(hinweis, a)


def test_jeder_fehlertyp_hat_einen_konstruierten_fall():
    belegt = {t for _a, _e, t in FAELLE}
    allgemein_und_antwort = ALLGEMEIN | VON_ANTWORT
    assert set(fehler.typen()) - allgemein_und_antwort - belegt == set()


def test_allgemeine_regeln():
    a = mk("umkehr", "fehlender_faktor", "? · 8 = 56", zahl(7), faktor=8, produkt=56)
    assert fehler.analysiere(a, "-7") == "vorzeichen"
    assert fehler.analysiere(a, "8") == "um_eins"
    assert fehler.analysiere(a, "17") == "um_zehn"
    assert fehler.analysiere(a, "70") == "komma"
    assert fehler.analysiere(a, "0,7") == "komma"
    b = mk("umkehr", "ergaenzen_100", "Ergänze: 15 + ? = 100", zahl(85), a=15, ziel=100)
    assert fehler.analysiere(b, "58") == "zahlendreher"


def test_unbekannter_fehler_und_unlesbares_ergibt_keinen_typ():
    a = add(47, 38)
    assert fehler.analysiere(a, "7") == ""
    assert fehler.analysiere(a, "") == ""
    assert fehler.analysiere(a, "abc") == ""
    assert fehler.analysiere(a, "1/0") == ""
    assert fehler.analysiere(a, "9" * 500) == ""
    assert "Schritt für Schritt" in fehler.hinweis_text("neutral")
    assert fehler.hinweis_text("") == ""


def test_pruefen_mathe_setzt_typ_und_hinweis_nur_bei_falsch():
    a = add(47, 38)
    soll = a.loesung.to_dict()
    r = pruefung.pruefen_mathe("75", soll, a)
    assert not r.richtig and r.fehlertyp == "uebertrag_vergessen" and "Übertrag" in r.hinweis
    r = pruefung.pruefen_mathe("85", soll, a)
    assert r.richtig and r.fehlertyp == "" and r.hinweis == ""
    r = pruefung.pruefen_mathe("7", soll, a)
    assert not r.richtig and r.fehlertyp == "" and "Schritt für Schritt" in r.hinweis
    r = pruefung.pruefen_mathe("abc", soll, a)
    assert r.fehlertyp == "unlesbar" and "als Zahl lesen" in r.hinweis
    assert pruefung.pruefen_mathe("75", soll).hinweis == ""  # ohne Aufgabe wie bisher


def test_bestehende_hinweise_bleiben_bei_fast():
    a = mk(
        "bruch_kuerzen",
        "kuerzen",
        "Kürze vollständig: 12/18",
        bausteine.lsg_bruch(Fraction(2, 3)),
        zaehler=12,
        nenner=18,
    )
    r = pruefung.pruefen_mathe("4/6", a.loesung.to_dict(), a)
    assert r.fast and r.fehlertyp == "nicht_gekuerzt" and "kürzen" in r.hinweis


def test_einheit_und_variable_haben_hinweise():
    a = mk(
        "geld",
        "euro_in_cent",
        "Wie viele Cent sind 3 €?",
        zahl(300, einheit="ct"),
        euro=3,
    )
    r = pruefung.pruefen_mathe("300 €", a.loesung.to_dict(), a)
    assert r.fehlertyp == "einheit" and "Einheit" in r.hinweis
    g = mk(
        "gleichung_linear",
        "plus",
        "Löse die Gleichung: x + 1 = 5",
        bausteine.lsg_gleichung(4),
        gleichung="x + 1 = 5",
        loesung=4,
    )
    r = pruefung.pruefen_mathe("y = 4", g.loesung.to_dict(), g)
    assert r.fehlertyp == "variable" and "Buchstaben" in r.hinweis


def test_hinweis_wird_neutral_wenn_er_die_loesung_verriete(monkeypatch):
    a = add(47, 38)
    monkeypatch.setitem(fehler.HINWEISE, "komma", "Das Ergebnis ist 85, prüfe es.")
    assert fehler.hinweis_text("komma", a) == fehler.hinweis_text("neutral")
    assert fehler.hinweis_text("komma") == "Das Ergebnis ist 85, prüfe es."


# --- Eigenschaftstests über alle Generatoren -------------------------------------------------


def _eingabe(a, kandidat):
    if a.loesung.form == "term":
        from apps.lernen.mathe import term

        return term.format_term(kandidat, anzeige=False)
    q = Fraction(kandidat)
    text = bausteine.zahl_text(q) if bausteine.ist_endlich(q) else bausteine.bruch_text(q)
    return f"x = {text}" if a.loesung.form == "gleichung" else text


def test_jede_modellvorhersage_wird_erkannt_und_der_hinweis_verraet_nichts():
    erkannt = gesamt = 0
    typen = set()
    for a in aufgaben(seeds=range(10)):
        for funktion in fehler._MODELLE.get(a.generator, ()):
            for _typ, kandidat in funktion(a):
                if kandidat is None:
                    continue
                if a.loesung.form != "term" and Fraction(kandidat) == Fraction(a.loesung.wert):
                    continue
                if a.loesung.form == "rest":
                    continue
                gesamt += 1
                got = fehler.analysiere(a, _eingabe(a, kandidat))
                if got:
                    erkannt += 1
                    typen.add(got)
                    assert got in fehler.HINWEISE
                    hinweis = fehler.hinweis_text(got, a)
                    assert not verraet(hinweis, a), (a.text, got, hinweis)
    assert gesamt > 1000 and erkannt == gesamt
    assert len(typen) >= 35  # die Modelle liefern die allermeisten Typen


def test_hinweise_aller_typen_enthalten_keine_ziffern_und_keine_zahlwoerter():
    for typ in fehler.typen():
        text = fehler.hinweis_text(typ)
        assert not re.search(r"\d", text), typ
    with translation.override("en"):
        for typ in fehler.typen():
            assert not re.search(r"\d", fehler.hinweis_text(typ)), typ


def test_hinweise_sind_auch_auf_englisch_vorhanden():
    with translation.override("en"):
        for typ in fehler.typen():
            text = fehler.hinweis_text(typ)
            assert text and text != fehler.HINWEISE[typ], typ  # übersetzt, nicht das Deutsche


def test_zufaellige_falsche_antworten_stuerzen_nie_ab_und_verraten_nichts():
    import random

    rng = random.Random(7)
    for a in aufgaben(seeds=range(4)):
        for _i in range(3):
            eingabe = str(rng.choice([rng.randint(-50, 5000), rng.random() * 100, "x", "−3/4"]))
            typ = fehler.analysiere(a, eingabe)
            assert typ == "" or typ in fehler.HINWEISE
            assert not verraet(fehler.hinweis_text(typ, a), a)


def test_rest_form_wird_analysiert():
    a = mk(
        "div_schriftlich",
        "div_mit_rest",
        "Rechne schriftlich mit Rest: 69 : 4 = ?",
        bausteine.lsg_rest(17, 1),
        dividend=69,
        teiler=4,
    )
    assert fehler.analysiere(a, "17 R 1") == ""  # richtig: keine Analyse nötig
    assert fehler.analysiere(a, "12 R 1") == ""
    assert fehler.analysiere(a, "17") == ""
