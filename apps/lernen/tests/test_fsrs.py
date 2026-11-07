"""Etappe 12 (W-4): FSRS-Adapter, Rating-Abbildung, Fallback auf Leitner und Simulation."""

import random
from datetime import UTC, date, datetime, time, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.kern import einstellungen
from apps.lernen import fsrs_adapter as fa
from apps.lernen import wiederholung
from apps.lernen.models import Frage, Lernstand, Richtung

HEUTE = date(2026, 10, 23)

fsrs = pytest.importorskip("fsrs")


# --- Rating-Abbildung (braucht fsrs nicht) --------------------------------------------------------


def test_rating_abbildung():
    assert fa.bewertung(False, 0) == fa.AGAIN
    assert fa.bewertung(False, 4) == fa.AGAIN
    assert fa.bewertung(True, 3) == fa.HARD  # viel Hilfe
    assert fa.bewertung(True, 5) == fa.HARD
    assert fa.bewertung(True, 1) == fa.GOOD
    assert fa.bewertung(True, 2) == fa.GOOD
    assert fa.bewertung(True, 0) == fa.GOOD  # ohne Zeitangabe nie Easy
    assert fa.bewertung(True, 0, dauer_ms=2000, median_ms=5000) == fa.EASY
    assert fa.bewertung(True, 0, dauer_ms=6000, median_ms=5000) == fa.GOOD
    assert fa.bewertung(True, 1, dauer_ms=1000, median_ms=5000) == fa.GOOD  # Hilfe: nie Easy


# --- Eigenschaften ------------------------------

stab = st.floats(min_value=0.5, max_value=300, allow_nan=False)
schw = st.floats(min_value=1.0, max_value=10.0, allow_nan=False)
tage = st.integers(min_value=0, max_value=200)


@settings(max_examples=60, deadline=None)
@given(s=stab, d=schw, t=tage)
def test_eigenschaft_good_steigert_again_senkt_die_stabilitaet(s, d, t):
    # fällig oder später gelernt (Stabilität wächst nur, wenn die Karte nicht ganz frisch ist)
    gut = fa.fortschreiben(s, d, HEUTE - timedelta(days=max(t, 1)), HEUTE, fa.GOOD)
    nein = fa.fortschreiben(s, d, HEUTE - timedelta(days=max(t, 1)), HEUTE, fa.AGAIN)
    assert gut.stabilitaet >= s - 1e-9
    assert nein.stabilitaet < s
    assert nein.schwierigkeit >= gut.schwierigkeit  # Again macht sie nie leichter als Good
    assert nein.stabilitaet < gut.stabilitaet


@settings(max_examples=60, deadline=None)
@given(s=stab, d=schw, t=tage, r=st.sampled_from([fa.AGAIN, fa.HARD, fa.GOOD, fa.EASY]))
def test_eigenschaft_abstand_in_den_grenzen(s, d, t, r):
    neu = fa.fortschreiben(s, d, HEUTE - timedelta(days=t), HEUTE, r)
    assert 1 <= neu.abstand_tage <= einstellungen.wert("lernen.fsrs_hoechstabstand_tage")
    assert 1.0 <= neu.schwierigkeit <= 10.0
    assert neu.stabilitaet > 0


@settings(max_examples=40, deadline=None)
@given(s=stab, d=schw)
def test_eigenschaft_besser_bewertet_heisst_laenger(s, d):
    abstaende = [
        fa.fortschreiben(s, d, HEUTE - timedelta(days=3), HEUTE, r).stabilitaet
        for r in (fa.AGAIN, fa.HARD, fa.GOOD, fa.EASY)
    ]
    assert abstaende == sorted(abstaende)


def test_erste_bewertung_der_karte():
    gut = fa.fortschreiben(None, None, None, HEUTE, fa.GOOD)
    nein = fa.fortschreiben(None, None, None, HEUTE, fa.AGAIN)
    assert gut.abstand_tage >= 1 and nein.abstand_tage == 1  # Again: morgen wieder
    assert gut.abstand_tage > nein.abstand_tage
    assert gut.stabilitaet > nein.stabilitaet


def test_ziel_retention_aus_der_einstellung():
    s90 = fa.fortschreiben(10.0, 5.0, HEUTE - timedelta(days=10), HEUTE, fa.GOOD).abstand_tage
    einstellungen.setzen("lernen.fsrs_ziel_retention_prozent", 80, akteur=None)
    s80 = fa.fortschreiben(10.0, 5.0, HEUTE - timedelta(days=10), HEUTE, fa.GOOD).abstand_tage
    assert s80 > s90  # niedrigere Ziel-Retention: längere Abstände


def test_hoechstabstand_gilt():
    einstellungen.setzen("lernen.fsrs_hoechstabstand_tage", 20, akteur=None)
    neu = fa.fortschreiben(200.0, 3.0, HEUTE - timedelta(days=100), HEUTE, fa.EASY)
    assert neu.abstand_tage == 20


def test_nominale_abstaende_wachsen_und_sind_begrenzt():
    liste = fa.nominale_abstaende(6)
    assert len(liste) == 6
    assert liste == sorted(liste) and liste[0] >= 1
    assert max(liste) <= 60
    assert fa.nominale_abstaende(6) == liste  # deterministisch (kein Fuzzing)


# --- stand_buchen: FSRS und Fallback ------------------------------


@pytest.fixture
def frage(fach):
    return Frage.objects.filter(thema__fach=fach).first()


def test_stand_buchen_mit_fsrs(kind_a, frage):
    assert wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    s = Lernstand.objects.get()
    assert s.stabilitaet and s.schwierigkeit
    assert s.faellig_am >= HEUTE + timedelta(days=1)
    erste = s.faellig_am
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, erste, None)
    assert s.faellig_am - erste >= erste - HEUTE  # Abstand wächst
    tag = s.faellig_am
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, False, tag, None)
    assert s.box == 0 and s.versuche == 3 and s.faellig_am == tag + timedelta(days=1)


def test_falsch_kommt_morgen_wieder(kind_a, frage):
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, False, HEUTE, None)
    assert s.faellig_am == HEUTE + timedelta(days=1)


def test_viel_hilfe_ist_hard_und_rueckt_weniger_vor(kind_a, frage):
    a = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    frage2 = Frage.objects.filter(thema__fach=frage.thema.fach).exclude(pk=frage.pk).first()
    b = wiederholung.stand_buchen(kind_a, frage2, Richtung.DE_EN, True, HEUTE, None, hilfestufe=4)
    assert b.stabilitaet < a.stabilitaet
    assert b.box == 0  # Leitner-Zähler für Stolperstellen bleibt: keine Box vor mit viel Hilfe


def test_leitner_als_einstellung(kind_a, frage):
    einstellungen.setzen("lernen.wiederholung_algorithmus", "leitner", akteur=None)
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    assert (s.box, s.faellig_am) == (1, HEUTE + timedelta(days=3))
    assert s.stabilitaet is None


def test_ohne_bibliothek_greift_leitner(kind_a, frage, monkeypatch):
    monkeypatch.setattr(fa, "fsrs", None)
    assert fa.algorithmus() == "leitner"
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    assert (s.box, s.faellig_am) == (1, HEUTE + timedelta(days=3))


def test_bestehender_leitner_stand_startet_aus_der_box(kind_a, frage):
    """Wer vor dem Umstieg in Box 3 war (14 Tage), startet nicht bei null."""
    Lernstand.objects.create(
        kind=kind_a,
        frage=frage,
        richtung=Richtung.DE_EN,
        box=3,
        faellig_am=HEUTE,
        versuche=5,
        richtige=5,
        zuletzt=None,
    )
    s = wiederholung.stand_buchen(kind_a, frage, Richtung.DE_EN, True, HEUTE, None)
    assert s.faellig_am - HEUTE >= timedelta(days=14)


# --- Simulation über 8 Wochen ------------------------------


def _simulieren(algorithmus, n_karten=40, tage_gesamt=56, seed=3):
    """Ein Lerner, dessen Gedächtnis dem FSRS-Modell folgt (Wahrscheinlichkeit = Abruf). Zählt
    Wiederholungen und die mittlere Abrufwahrscheinlichkeit am Ende. Gleiche Würfe für beide."""
    zufall = random.Random(seed)
    wuerfe = [[zufall.random() for _ in range(tage_gesamt + 1)] for _ in range(n_karten)]
    modell = fsrs.Scheduler(
        learning_steps=(), relearning_steps=(), enable_fuzzing=False, maximum_interval=36500
    )
    von = HEUTE
    start = datetime.combine(von, time(), tzinfo=UTC)
    abstaende = [1, 3, 7, 14]
    karten = []
    for _ in range(n_karten):
        karten.append(
            {"gedaechtnis": fsrs.Card(), "faellig": 0, "stab": None, "schw": None, "box": 0}
        )
        karten[-1]["zuletzt"] = None
    wdh = 0
    for tag in range(tage_gesamt + 1):
        jetzt = start + timedelta(days=tag)
        for i, k in enumerate(karten):
            if k["faellig"] > tag:
                continue
            wdh += 1
            g = k["gedaechtnis"]
            if g.last_review is None:
                richtig = True  # erstes Lernen: die Karte wird gezeigt und eingeprägt
            else:
                richtig = wuerfe[i][tag] < modell.get_card_retrievability(g, jetzt)
            g, _log = modell.review_card(
                g, fsrs.Rating.Good if richtig else fsrs.Rating.Again, jetzt
            )
            k["gedaechtnis"] = g
            heute = von + timedelta(days=tag)
            if algorithmus == "fsrs":
                neu = fa.fortschreiben(
                    k["stab"], k["schw"], k["zuletzt"], heute, fa.GOOD if richtig else fa.AGAIN
                )
                k["stab"], k["schw"], k["zuletzt"] = neu.stabilitaet, neu.schwierigkeit, heute
                k["faellig"] = tag + neu.abstand_tage
            else:
                k["box"] = min(k["box"] + 1, 3) if richtig else 0
                k["faellig"] = tag + abstaende[k["box"]]
    ende = start + timedelta(days=tage_gesamt)
    retention = (
        sum(modell.get_card_retrievability(k["gedaechtnis"], ende) for k in karten) / n_karten
    )
    return wdh, retention


def test_simulation_8_wochen_weniger_wiederholungen_bei_ausreichender_retention():
    """FSRS zielt auf 90 % Behalten, Leitner wiederholt dafür viel öfter und bleibt darüber. Der
    faire Vergleich: deutlich weniger Wiederholungen und die Ziel-Retention (Plan: >= 85 %)
    gehalten. Gleiche Retention wie Leitner ist nicht das Ziel von FSRS."""
    wdh_f, ret_f = _simulieren("fsrs")
    wdh_l, ret_l = _simulieren("leitner")
    assert wdh_f < wdh_l
    assert wdh_f <= 0.6 * wdh_l  # mindestens 40 % weniger Wiederholungen
    assert ret_f >= 0.85
    # Wiederholungen je behaltener Karte (Plan-Metrik) sinken
    assert wdh_f / ret_f < wdh_l / ret_l
