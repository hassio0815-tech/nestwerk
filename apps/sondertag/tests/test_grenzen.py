"""Sondertag-Grenzen ohne DB (AP27): Abstand, App-Jahr, Warteschlange, Szenarien."""

import random
from datetime import date, timedelta

import pytest

from apps.kern import zeit
from apps.sondertag import grenzen

GO_LIVE = date(2026, 10, 19)
R = grenzen.Regeln(go_live=GO_LIVE, max_pro_jahr=2, abstand=150)


def tag(n):
    """Tag n nach Go-live."""
    return GO_LIVE + timedelta(days=n)


def test_ohne_historie_sofort():
    assert grenzen.einloesbar_ab(tag(10), [], R) == tag(10)


def test_abstand_zum_letzten_sondertag():
    assert grenzen.einloesbar_ab(tag(10), [tag(0)], R) == tag(150)
    assert grenzen.einloesbar_ab(tag(200), [tag(0)], R) == tag(200)


def test_abstand_auch_zu_spaeter_datierter_korrektur():
    # Korrigiertes Bezugsdatum liegt nach dem frühesten Datum: auch davor 150 Tage Abstand
    assert grenzen.einloesbar_ab(tag(10), [tag(100)], R) == tag(250)


def test_max_zwei_pro_app_jahr():
    angenommen = [tag(0), tag(150)]
    # Tag 300 hätte genug Abstand, aber App-Jahr 1 ist voll -> Beginn App-Jahr 2
    assert grenzen.einloesbar_ab(tag(300), angenommen, R) == date(2027, 10, 19)


def test_sondertag_vor_go_live_zaehlt_nur_fuer_abstand():
    vorher = GO_LIVE - timedelta(days=30)
    assert grenzen.einloesbar_ab(GO_LIVE, [vorher], R) == vorher + timedelta(days=150)
    assert grenzen.erlaubt(tag(200), [vorher, tag(120)], R) is False  # Abstand zu tag(120)
    assert grenzen.erlaubt(tag(270), [vorher, tag(120)], R) is True


def test_schaltjahr_go_live_29_februar():
    r = grenzen.Regeln(go_live=date(2028, 2, 29), max_pro_jahr=2, abstand=150)
    voll = [date(2028, 3, 1), date(2028, 8, 1)]
    assert grenzen.einloesbar_ab(date(2029, 1, 10), voll, r) == date(2029, 2, 28)


def test_warteschlange_fifo_mit_geplanten_daten():
    heute = tag(60)
    ab = grenzen.plan([tag(20), tag(40), tag(50)], [], R, heute)
    assert ab[0] == tag(20)  # schon einlösbar
    assert ab[1] == tag(60 + 150)  # erster frühestens heute angenommen
    assert ab[2] == date(2027, 10, 19)  # App-Jahr 1 voll
    for a, b in zip(ab, ab[1:], strict=False):
        assert b >= a


def _simulieren(verdient, r, *, verzug=0, seed=None, vorher=()):
    """Ansprüche zu den Tagen ``verdient``; jeder wird angenommen, sobald er einlösbar ist
    (optional zufälliger Verzug). Gibt (Annahmedaten, noch offene Ansprüche) zurück."""
    rnd = random.Random(seed)
    angenommen, offen = list(vorher), []
    heute = r.go_live
    ende = max(verdient) + timedelta(days=365 * 6)
    kommend = sorted(verdient)
    while heute <= ende and (offen or kommend):
        while kommend and kommend[0] <= heute:
            offen.append(kommend.pop(0))
        if offen:
            ab = grenzen.plan(offen, angenommen, r, heute)[0]
            if ab <= heute:
                assert grenzen.erlaubt(heute, angenommen, r)
                angenommen.append(heute)
                offen.pop(0)
                if verzug:
                    heute += timedelta(days=rnd.randint(0, verzug))
        heute += timedelta(days=1)
    return angenommen, offen


def _pruefen(angenommen, r):
    daten = sorted(angenommen)
    for a, b in zip(daten, daten[1:], strict=False):
        assert (b - a).days >= r.abstand, (a, b)
    je_jahr = {}
    for d in daten:
        if d >= r.go_live:
            nummer = zeit.app_jahr(d, go_live=r.go_live).nummer
            je_jahr[nummer] = je_jahr.get(nummer, 0) + 1
    assert all(n <= r.max_pro_jahr for n in je_jahr.values()), je_jahr
    return je_jahr


def test_52_wochen_szenario_vier_raenge_in_einem_jahr():
    """Schnelles Kind: Ausbaustufe 6 in Rang 2-5 innerhalb von 52 Wochen."""
    verdient = [tag(7 * 8), tag(7 * 20), tag(7 * 34), tag(7 * 50)]
    angenommen, offen = _simulieren(verdient, R)
    assert not offen
    je_jahr = _pruefen(angenommen, R)
    assert je_jahr[1] == 2  # nie mehr als 2 im ersten App-Jahr
    assert angenommen[0] == verdient[0]
    assert angenommen[1] == verdient[0] + timedelta(days=150)
    # die übrigen bleiben verdient und werden im 2. App-Jahr einlösbar (nicht verloren)
    assert len(angenommen) == 4
    assert angenommen[2] == date(2027, 10, 19)
    assert angenommen[3] == angenommen[2] + timedelta(days=150)


@pytest.mark.parametrize("seed", range(12))
def test_mehrjahres_szenario_nie_mehr_als_zwei_nie_unter_150_tage(seed):
    rnd = random.Random(seed)
    verdient, t = [], 0
    while t < 365 * 7:
        t += rnd.randint(20, 200)
        verdient.append(tag(t))
    angenommen, offen = _simulieren(verdient, R, verzug=40, seed=seed)
    je_jahr = _pruefen(angenommen, R)
    # nichts geht verloren: was nicht eingelöst ist, wartet noch (FIFO)
    assert len(angenommen) + len(offen) == len(verdient)
    assert offen == sorted(offen)
    assert sum(je_jahr.values()) >= 1


def test_mehrjahres_szenario_mit_vorgeschichte_und_anderen_grenzen():
    r = grenzen.Regeln(go_live=date(2028, 2, 29), max_pro_jahr=3, abstand=90)
    vorher = [date(2027, 12, 24)]
    verdient = [date(2028, 3, 1) + timedelta(days=45 * i) for i in range(30)]
    angenommen, _ = _simulieren(verdient, r, vorher=vorher)
    je_jahr = _pruefen(angenommen, r)
    assert max(je_jahr.values()) == 3
    assert (angenommen[1] - vorher[0]).days >= 90
