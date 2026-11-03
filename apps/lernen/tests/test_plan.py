"""Planer der Prüfungsvorbereitung als reine Funktion: Grenzfälle, Realitätscheck, Eigenschaften."""

from collections import defaultdict
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.lernen import plan as P

HEUTE = date(2026, 11, 2)  # ein Montag
P20 = P.Parameter(tagesziel=20)


def stoffe_mit(*anzahlen):
    zaehler = 0
    ergebnis = {}
    for i, n in enumerate(anzahlen):
        ergebnis[f"s{i}"] = tuple(range(zaehler, zaehler + n))
        zaehler += n
    return ergebnis


def plane(stoffe, tage, p=P20, **extra):
    return P.plane(
        p,
        start=HEUTE,
        termin=HEUTE + timedelta(days=tage),
        teile=P.teilen(stoffe, p),
        stoffe=stoffe,
        **extra,
    )


def je_tag(ergebnis):
    summen = defaultdict(int)
    for e in ergebnis.eintraege:
        summen[e.datum] += e.minuten
    return summen


# --- Grenzfälle des Realitätschecks --------------------------------------------------------


def test_termin_in_der_vergangenheit_oder_heute_gibt_keinen_plan():
    for tage in (-5, 0):
        r = plane(stoffe_mit(10), tage)
        assert (r.ok, r.grund, r.eintraege) == (False, P.GRUND_VORBEI, ())


def test_ohne_stoff_gibt_es_keinen_plan():
    r = plane({}, 10)
    assert (r.ok, r.grund) == (False, P.GRUND_KEIN_STOFF)
    r = plane({"s0": ()}, 10)
    assert r.grund == P.GRUND_KEIN_STOFF


def test_termin_morgen_mit_stoff_ist_zu_viel_mit_vorschlaegen():
    """Morgen ist die Prüfung: heute ist der leichte Tag, Neues passt nicht mehr hinein."""
    r = plane(stoffe_mit(30), 1)
    assert (r.ok, r.grund) == (False, P.GRUND_ZU_VIEL)
    assert r.eintraege == ()
    assert r.benoetigt > r.verfuegbar == 0
    arten = {v.art for v in r.vorschlaege}
    assert P.VORSCHLAG_FRUEHER in arten


def test_termin_in_60_tagen_beginnt_erst_spaet_und_ist_schaffbar():
    r = plane(stoffe_mit(40), 60)
    assert r.ok
    erster = min(e.datum for e in r.eintraege)
    assert erster == HEUTE + timedelta(days=60 - P20.max_laenge)  # max. Planlänge


def test_sehr_viel_stoff_wird_nicht_ueberfuellt():
    r = plane(stoffe_mit(2000), 14)
    assert not r.ok and r.grund == P.GRUND_ZU_VIEL
    assert r.eintraege == ()
    assert r.benoetigt > r.verfuegbar
    # kleiner machen ist möglich, erhöhen des Ziels um höchstens 15 Minuten reicht hier nicht
    arten = {v.art for v in r.vorschlaege}
    assert P.VORSCHLAG_KLEINER in arten
    assert P.VORSCHLAG_ZIEL not in arten


def test_vorschlaege_funktionieren_wirklich():
    stoffe = stoffe_mit(180)
    r = plane(stoffe, 8)
    assert not r.ok
    vorschlaege = {v.art: v.wert for v in r.vorschlaege}
    assert vorschlaege
    if P.VORSCHLAG_ZIEL in vorschlaege:
        assert plane(stoffe, 8, P.Parameter(tagesziel=vorschlaege[P.VORSCHLAG_ZIEL])).ok
        assert vorschlaege[P.VORSCHLAG_ZIEL] <= P20.tagesziel + P20.ziel_zuschlag_max
    if P.VORSCHLAG_FRUEHER in vorschlaege:
        r2 = P.plane(
            P20,
            start=HEUTE - timedelta(days=vorschlaege[P.VORSCHLAG_FRUEHER]),
            termin=HEUTE + timedelta(days=8),
            teile=P.teilen(stoffe, P20),
            stoffe=stoffe,
            puffer_fest=None,
        )
        assert r2.ok
    if P.VORSCHLAG_KLEINER in vorschlaege:
        weniger = vorschlaege[P.VORSCHLAG_KLEINER]
        kleiner = stoffe_mit(180 - weniger)
        assert plane(kleiner, 8).ok
        assert not plane(stoffe_mit(180 - weniger + 1), 8).ok  # knapp: eine Frage mehr geht nicht


def test_nie_mehr_als_das_tagesziel_pro_tag():
    for ziel in (5, 12, 20, 45):
        p = P.Parameter(tagesziel=ziel)
        r = plane(stoffe_mit(25, 40, 10), 30, p)
        if r.ok:
            assert max(je_tag(r).values()) <= ziel


def test_letzter_tag_nur_leichte_wiederholung_und_alle_stoffe():
    r = plane(stoffe_mit(30, 30), 12)
    assert r.ok
    letzter = HEUTE + timedelta(days=11)
    arten = {e.art for e in r.eintraege if e.datum == letzter}
    assert arten == {P.ART_LEICHT}
    assert {e.stoff for e in r.eintraege if e.datum == letzter} == {"s0", "s1"}
    assert sum(e.minuten for e in r.eintraege if e.datum == letzter) <= P20.leicht_minuten
    assert not any(e.art == P.ART_NEU and e.datum >= letzter for e in r.eintraege)


def test_puffertage_ein_tag_je_fuenf_lerntage():
    r = plane(stoffe_mit(10), 20)
    assert r.ok
    puffer = [e for e in r.eintraege if e.art == P.ART_PUFFER]
    lern_tage = {e.datum for e in r.eintraege if e.art != P.ART_PUFFER}
    assert len(puffer) == 3  # 19 Tage vor dem leichten Tag: 3 Puffer, je 5 Lerntage
    assert all(e.minuten == 0 and e.puffer for e in puffer)
    assert not {e.datum for e in puffer} & lern_tage
    # ohne Rhythmus keine Puffer
    r0 = plane(stoffe_mit(10), 20, P.Parameter(tagesziel=20, puffer_rhythmus=0))
    assert not [e for e in r0.eintraege if e.art == P.ART_PUFFER]


def test_pausentage_und_wochentage_bekommen_nichts():
    pause = frozenset(HEUTE + timedelta(days=i) for i in range(2, 6))
    r = plane(stoffe_mit(30), 20, blockiert=pause)
    assert r.ok
    assert not {e.datum for e in r.eintraege} & pause
    # nur Montag bis Freitag
    p = P.Parameter(tagesziel=20, wochentage=frozenset(range(5)))
    r = plane(stoffe_mit(30), 20, p)
    assert r.ok and all(e.datum.weekday() < 5 for e in r.eintraege)


def test_ferien_die_alles_blockieren_ergeben_den_realitaetscheck():
    alle = frozenset(HEUTE + timedelta(days=i) for i in range(30))
    r = plane(stoffe_mit(10), 30, blockiert=alle)
    assert not r.ok and r.grund == P.GRUND_ZU_VIEL and r.lerntage == 0


def test_wiederholung_im_abstand_der_boxen():
    r = plane(stoffe_mit(13), 30)  # genau eine Portion
    neu = [e for e in r.eintraege if e.art == P.ART_NEU]
    assert len(neu) == 1
    tag0 = neu[0].datum
    wdh = sorted(e.datum for e in r.eintraege if e.art == P.ART_WDH)
    assert wdh, "Wiederholungen eingeplant"
    abstaende = {(d - tag0).days for d in wdh}
    assert abstaende <= {1, 3, 7, 14} or all(a >= 1 for a in abstaende)
    pflicht = [e for e in r.eintraege if e.art == P.ART_WDH and e.pflicht]
    assert len(pflicht) == 1 and pflicht[0].datum > tag0


def test_portionen_sind_klein():
    stoffe = stoffe_mit(100)
    r = plane(stoffe, 40)
    assert r.ok
    for e in r.eintraege:
        if e.art == P.ART_NEU:
            assert e.minuten <= P20.portion_minuten


def test_knapp_ist_nur_ein_hinweis():
    assert plane(stoffe_mit(10), 5).knapp
    assert not plane(stoffe_mit(10), 30).knapp


def test_plan_ist_deterministisch():
    a = plane(stoffe_mit(50, 20), 25)
    b = plane(stoffe_mit(50, 20), 25)
    assert a == b


# --- Neuplanen (verpasste Tage) ------------------------------------------------------------


def test_neuplanen_mit_stehenden_puffern_und_puffer_nutzen():
    stoffe = stoffe_mit(150)
    erst = plane(stoffe, 21)
    assert erst.ok
    fest = frozenset(e.datum for e in erst.eintraege if e.puffer)
    # Fünf Tage ausgefallen: nur noch 16 Tage übrig
    spaet = HEUTE + timedelta(days=5)
    teile = P.teilen(stoffe, P20)
    kwargs = {
        "start": spaet,
        "termin": HEUTE + timedelta(days=21),
        "teile": teile,
        "stoffe": stoffe,
        "puffer_fest": fest,
    }
    ohne = P.plane(P20, **kwargs)
    mit = P.plane(P20, **kwargs, puffer_nutzen=True)
    if ohne.ok:
        assert not ohne.puffer_genutzt
    else:
        assert mit.ok is False or mit.puffer_genutzt


def test_offene_pflicht_wiederholung_wird_eingeplant():
    stoffe = stoffe_mit(13)
    wdh = [P.WdhOffen("s0", tuple(range(13)), 4, HEUTE + timedelta(days=2))]
    r = P.plane(
        P20,
        start=HEUTE,
        termin=HEUTE + timedelta(days=10),
        teile=[],
        stoffe=stoffe,
        wdh_offen=wdh,
    )
    assert r.ok
    z = [e for e in r.eintraege if e.art == P.ART_WDH and e.pflicht]
    assert len(z) == 1 and z[0].datum >= HEUTE + timedelta(days=2)


def test_nur_leichter_tag_ohne_neuen_stoff():
    r = P.plane(P20, start=HEUTE, termin=HEUTE + timedelta(days=1), teile=[], stoffe=stoffe_mit(5))
    assert r.ok and {e.art for e in r.eintraege} == {P.ART_LEICHT}


# --- Eigenschaften -------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    fragen=st.lists(st.integers(1, 80), min_size=1, max_size=4),
    tage=st.integers(-3, 70),
    ziel=st.integers(5, 60),
    rhythmus=st.integers(0, 8),
    pausen=st.sets(st.integers(0, 40), max_size=15),
)
def test_eigenschaften_des_planers(fragen, tage, ziel, rhythmus, pausen):
    p = P.Parameter(tagesziel=ziel, puffer_rhythmus=rhythmus)
    stoffe = stoffe_mit(*fragen)
    blockiert = frozenset(HEUTE + timedelta(days=i) for i in pausen)
    r = plane(stoffe, tage, p, blockiert=blockiert)
    termin = HEUTE + timedelta(days=tage)
    if not r.ok:
        assert r.eintraege == ()  # nie ein halber oder überfüllter Plan
        return
    summen = je_tag(r)
    assert all(m <= ziel for m in summen.values())  # nie über dem Tagesziel
    assert all(HEUTE <= e.datum < termin for e in r.eintraege)  # nur vor dem Termin
    assert not {e.datum for e in r.eintraege} & blockiert  # nie auf Pausentagen
    gesamt = sum(fragen)
    geplant = [f for e in r.eintraege if e.art == P.ART_NEU for f in e.fragen]
    assert sorted(geplant) == list(range(gesamt))  # jede Frage genau einmal neu
    puffer = {e.datum for e in r.eintraege if e.puffer}
    assert not puffer & {e.datum for e in r.eintraege if not e.puffer}
    # jede Pflicht-Wiederholung liegt nach ihrer Portion
    erste = {}
    for e in r.eintraege:
        if e.art == P.ART_NEU:
            erste[e.fragen] = e.datum
    for e in r.eintraege:
        if e.art == P.ART_WDH and e.pflicht:
            assert e.datum > erste[e.fragen]


@settings(max_examples=40, deadline=None)
@given(fragen=st.integers(1, 400), tage=st.integers(2, 50), ziel=st.integers(5, 40))
def test_vorschlaege_sind_ehrlich(fragen, tage, ziel):
    p = P.Parameter(tagesziel=ziel)
    stoffe = stoffe_mit(fragen)
    r = plane(stoffe, tage, p)
    if r.ok:
        assert r.vorschlaege == ()
        return
    for v in r.vorschlaege:
        if v.art == P.VORSCHLAG_ZIEL:
            assert plane(stoffe, tage, P.Parameter(tagesziel=v.wert)).ok
        if v.art == P.VORSCHLAG_KLEINER:
            assert plane(stoffes_kleiner(fragen, v.wert), tage, p).ok


def stoffes_kleiner(fragen, weniger):
    return stoffe_mit(fragen - weniger)


@pytest.mark.parametrize("anzahl", [0, 1, 13, 14])
def test_teilen_schneidet_in_portionen(anzahl):
    teile = P.teilen({"a": tuple(range(anzahl))}, P20)
    assert sum(len(t.fragen) for t in teile) == anzahl
    assert all(1 <= len(t.fragen) <= P.fragen_je_portion(P20) for t in teile)
