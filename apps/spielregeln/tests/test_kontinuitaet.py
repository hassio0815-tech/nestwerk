"""Reine Regeln: Serie, Pause/Teilpause, Tagesserie, Puffer, Woche 53, Sommerzeit, Quartal."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.kern.zeit import IsoWoche
from apps.spielregeln import kontinuitaet as k

BERLIN = ZoneInfo("Europe/Berlin")
W1 = IsoWoche(2026, 43)  # Mo 19.10.2026


def tag(woche, wochentag=1):
    return woche.montag + timedelta(days=wochentag - 1)


def wochen(n, start=W1):
    ergebnis = [start]
    for _ in range(n - 1):
        ergebnis.append(ergebnis[-1].naechste())
    return ergebnis


def serien(aktive, pausen=(), n=None, neutral_ab=1, start=W1):
    ws = wochen(n or 6, start)
    return [
        e.wochenserie_danach
        for e in k.wochen_auswerten(set(aktive), pausen, ws[0], ws[-1], neutral_ab)
    ]


def test_aktive_wochen_erhoehen_serie_inaktive_setzen_auf_null():
    w = wochen(6)
    aktive = {tag(w[0]), tag(w[1], 7), tag(w[2], 3), tag(w[4])}
    assert serien(aktive) == [1, 2, 3, 0, 1, 0]
    ergebnis = k.wochen_auswerten(aktive, [], w[0], w[-1], 1)
    assert [e.aktive_wochen_gesamt for e in ergebnis] == [1, 2, 3, 3, 4, 4]  # nie zurückgesetzt


def test_pause_macht_inaktive_woche_neutral_serie_bleibt():
    w = wochen(4)
    aktive = {tag(w[0]), tag(w[1]), tag(w[3])}
    pause = [(tag(w[2], 1), tag(w[2], 7))]
    ergebnis = k.wochen_auswerten(aktive, pause, w[0], w[-1], 1)
    assert [e.wochenserie_danach for e in ergebnis] == [1, 2, 2, 3]
    assert [e.neutral for e in ergebnis] == [False, False, True, False]
    assert ergebnis[2].pausentage == 7


def test_aufgabe_in_pause_zaehlt_normal():
    w = wochen(2)
    ergebnis = k.wochen_auswerten({tag(w[1], 3)}, [(tag(w[0]), None)], w[0], w[1], 1)
    assert [(e.aktiv, e.neutral, e.wochenserie_danach) for e in ergebnis] == [
        (False, True, 0),
        (True, False, 1),
    ]


@pytest.mark.parametrize(
    ("neutral_ab", "pausentage", "serie"),
    [(1, 1, [1, 1, 2]), (3, 2, [1, 0, 1]), (3, 3, [1, 1, 2]), (7, 6, [1, 0, 1])],
)
def test_teilpause_neutral_ab_n_pausentagen(neutral_ab, pausentage, serie):
    """K5: Woche ohne Aufgabe ist neutral ab N Pausentagen (Startwert 1)."""
    w = wochen(3)
    pause = [(tag(w[1], 7 - pausentage + 1), tag(w[1], 7))]  # Pause am Wochenende
    aktive = {tag(w[0]), tag(w[2])}
    assert serien(aktive, pause, n=3, neutral_ab=neutral_ab) == serie
    assert k.pausentage(w[1], pause) == pausentage


def test_ueberlappende_pausen_zaehlen_als_vereinigung():
    w = W1
    pausen = [(tag(w, 1), tag(w, 3)), (tag(w, 2), tag(w, 4)), (tag(w, 7), None)]
    assert k.pausentage(w, pausen) == 5


def test_pause_ueber_wochengrenze_und_offen():
    w = wochen(3)
    pause = [(tag(w[0], 6), tag(w[1], 2))]
    assert [k.pausentage(x, pause) for x in w] == [2, 2, 0]
    assert [k.pausentage(x, [(tag(w[1], 7), None)]) for x in w] == [0, 1, 7]


def test_woche_53_und_jahreswechsel():
    """2026 hat 53 ISO-Wochen; Serie läuft über W53 ins neue Jahr."""
    w52 = IsoWoche(2026, 52)
    w = wochen(3, w52)
    assert [str(x) for x in w] == ["2026-W52", "2026-W53", "2027-W01"]
    aktive = {date(2026, 12, 21), date(2026, 12, 31), date(2027, 1, 4)}
    assert serien(aktive, n=3, start=w52) == [1, 2, 3]
    # 31.12.2026 und 03.01.2027 liegen in derselben ISO-Woche 2026-W53
    assert IsoWoche.von(date(2027, 1, 3)) == IsoWoche(2026, 53)
    assert serien({date(2026, 12, 21), date(2027, 1, 3)}, n=2, start=w52) == [1, 2]


# --- Tagesserie -------------------------------------------------------------------------------


def test_tagesserie_laufender_tag_bricht_nie():
    heute = date(2026, 10, 22)
    aktive = {date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)}
    assert k.tagesserie(aktive, [], heute) == k.TagesStand(3, 3)
    assert k.tagesserie(aktive | {heute}, [], heute) == k.TagesStand(4, 4)
    # Lücke gestern bricht
    assert k.tagesserie({date(2026, 10, 19), date(2026, 10, 20)}, [], heute) == k.TagesStand(0, 2)


def test_tagesserie_pausentage_neutral_aktive_pausentage_zaehlen():
    heute = date(2026, 10, 25)
    aktive = {date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 23), date(2026, 10, 24)}
    pause = [(date(2026, 10, 21), date(2026, 10, 23))]
    assert k.tagesserie(aktive, pause, heute) == k.TagesStand(4, 4)
    assert k.tagesserie(aktive, [], heute) == k.TagesStand(2, 2)


def test_tagesserie_ignoriert_zukunft_und_rekord_bleibt():
    aktive = {date(2026, 10, d) for d in (1, 2, 3, 4, 5, 10, 11)} | {date(2026, 11, 1)}
    assert k.tagesserie(aktive, [], date(2026, 10, 11)) == k.TagesStand(2, 5)
    assert k.tagesserie(set(), [], date(2026, 10, 11)) == k.TagesStand(0, 0)


# --- Puffer (K1) und Sommerzeit ---------------------------------------------------------------


def test_finalisierung_nach_24h_puffer():
    assert k.finalisiert_ab(W1, 24, BERLIN) == datetime(2026, 10, 26, 23, 0, tzinfo=UTC)
    assert k.finalisiert_ab(W1, 0, BERLIN) == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def test_finalisierung_ueber_zeitumstellung():
    """So 25.10.2026 endet die Sommerzeit: Woche W43 endet Mo 26.10. 00:00 MEZ (= 23:00 UTC
    am So). Puffer in Wanduhrzeit: Di 27.10. 00:00 MEZ."""
    assert k.finalisiert_ab(W1, 24, BERLIN) == datetime(2026, 10, 27, 0, 0, tzinfo=BERLIN)
    # Frühjahr: So 29.03.2026 beginnt die Sommerzeit (W13), Abschluss Di 31.03. 00:00 MESZ
    assert k.finalisiert_ab(IsoWoche(2026, 13), 24, BERLIN) == datetime(
        2026, 3, 30, 22, 0, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("bestaetigt", "erwartet"),
    [
        (datetime(2026, 10, 26, 20, 0, tzinfo=BERLIN), date(2026, 10, 25)),  # Mo: im Puffer
        (datetime(2026, 10, 26, 23, 59, tzinfo=BERLIN), date(2026, 10, 25)),  # letzte Minute
        (datetime(2026, 10, 27, 0, 0, tzinfo=BERLIN), date(2026, 10, 27)),  # Di: abgeschlossen
        (datetime(2026, 11, 3, 9, 0, tzinfo=BERLIN), date(2026, 11, 3)),
    ],
)
def test_meldedatum_zaehlt_spaete_bestaetigung_zaehlt_fuer_bestaetigungswoche(bestaetigt, erwartet):
    gemeldet = date(2026, 10, 25)  # Sonntag (Tag der Zeitumstellung)
    assert k.wirksames_datum(gemeldet, bestaetigt, 24, BERLIN) == erwartet


def test_meldung_sonntag_spaet_zaehlt_fuer_sonntag_trotz_utc_montag():
    """So 23:30 MEZ ist UTC schon 22:30 – aber Mo 00:30 MEZ ist UTC noch So 23:30."""
    from apps.kern import zeit

    assert zeit.heute(datetime(2026, 10, 25, 23, 30, tzinfo=BERLIN), BERLIN) == date(2026, 10, 25)
    assert zeit.heute(datetime(2026, 10, 25, 23, 30, tzinfo=UTC), BERLIN) == date(2026, 10, 26)


# --- Quartal ----------------------------------------------------------------------------------


def test_quartal_nach_donnerstag():
    assert k.quartal(IsoWoche(2026, 53)) == (2026, 4)
    assert k.quartal(IsoWoche(2027, 1)) == (2027, 1)
    q4 = k.quartal_wochen(2026, 4)
    assert (str(q4[0]), str(q4[-1]), len(q4)) == ("2026-W40", "2026-W53", 14)
    assert len(k.quartal_wochen(2027, 1)) == 12  # erster Donnerstag 07.01., letzter 25.03.
