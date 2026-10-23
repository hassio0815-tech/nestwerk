"""Eigenschaftstests (Hypothesis, ARCHITECTURE 10): Neuberechnung aus der Historie trifft den
gespeicherten Stand exakt – über zufällige Folgen aus Aktivitäten, Stornos, Pausen (Kind und
Familie, offen/befristet, rückwirkend) und Job-Läufen zu beliebigen Zeitpunkten."""

from datetime import date, timedelta

from django.db import transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.kern import zeit
from apps.kern.zeit import IsoWoche
from apps.spielregeln import kontinuitaet as k
from apps.spielregeln import services
from apps.spielregeln.models import Aktivitaet, KindStand, Wochenauswertung

from .conftest import GO_LIVE, lok

KIND = st.sampled_from([0, 1, None])  # None = Familie (nur Pausen)

AKTIV = st.tuples(st.just("aktiv"), st.integers(0, 1), st.integers(0, 3))
schritt = st.one_of(
    AKTIV,
    AKTIV,  # Aktivitäten doppelt gewichtet
    st.tuples(st.just("storno"), st.integers(0, 50)),
    st.tuples(
        st.just("pause"), KIND, st.integers(-12, 6), st.one_of(st.none(), st.integers(0, 12))
    ),
    st.tuples(st.just("pause_aus"), KIND),
    st.tuples(
        st.just("job"),
    ),
)
folge = st.lists(st.tuples(st.integers(1, 80), schritt), min_size=15, max_size=60)


def _ausfuehren(kinder, mama, uhr, schritte):
    nr = 0
    for stunden, (art, *werte) in schritte:
        jetzt = uhr.weiter(hours=stunden)
        heute = zeit.heute(jetzt)
        if art == "aktiv":
            kind, zurueck = kinder[werte[0]], werte[1]
            meldedatum = max(GO_LIVE, heute - timedelta(days=zurueck))
            nr += 1
            with transaction.atomic():
                services.aktivitaet_erfassen(
                    kind, meldedatum, modul="p", referenz=str(nr), erfasst_am=jetzt
                )
        elif art == "storno":
            offen = list(Aktivitaet.objects.filter(storniert=False).order_by("id"))
            if offen:
                ziel = offen[werte[0] % len(offen)]
                services.aktivitaet_stornieren(
                    modul=ziel.modul, referenz=ziel.referenz, jetzt=jetzt
                )
        elif art == "pause":
            kind = None if werte[0] is None else kinder[werte[0]]
            ab = max(GO_LIVE, heute + timedelta(days=werte[1]))
            bis = None if werte[2] is None else ab + timedelta(days=werte[2])
            try:
                services.pause_setzen(kind, von=mama, ab=ab, bis=bis, jetzt=jetzt)
            except services.SpielregelnFehler:
                pass
        elif art == "pause_aus":
            kind = None if werte[0] is None else kinder[werte[0]]
            services.pausen_beenden_fuer(kind, von=mama, jetzt=jetzt)
        else:
            services.wochen_sicherstellen(jetzt=jetzt)
            assert services.neu_berechnen() == []


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(schritte=folge)
def test_neuberechnung_trifft_gespeicherten_stand(anna, ben, mama, uhr, schritte):
    with transaction.atomic():
        uhr.stellen(lok(2026, 10, 19, 8))
        _ausfuehren([anna, ben], mama, uhr, schritte)
        services.wochen_sicherstellen(jetzt=uhr.weiter(hours=1))
        assert services.neu_berechnen() == []
        # Gespeicherter Stand ist in sich konsistent
        for kind in (anna, ben):
            stand = KindStand.objects.get(kind=kind)
            finale = list(
                Wochenauswertung.objects.filter(kind=kind, finalisiert_am__isnull=False).order_by(
                    "montag"
                )
            )
            if finale:
                assert stand.wochenserie == finale[-1].wochenserie_danach
                assert stand.aktive_wochen_gesamt == sum(w.aktiv for w in finale)
            gesamt = [w.aktive_wochen_gesamt for w in finale]
            assert gesamt == sorted(gesamt)  # nie zurückgesetzt
        transaction.set_rollback(True)


# --- Reine Regeln gegen eine naive Referenz ---------------------------------------------------


def _referenz_serie(aktive, pausen, wochen, neutral_ab):
    """Naiv, Tag für Tag, ohne Hilfsfunktionen des Moduls."""
    serie, ergebnis = 0, []
    for w in wochen:
        tage = [w.montag + timedelta(days=i) for i in range(7)]
        ist_aktiv = any(t in aktive for t in tage)
        pausiert = sum(1 for t in tage if any(v <= t and (b is None or t <= b) for v, b in pausen))
        if ist_aktiv:
            serie += 1
        elif pausiert < neutral_ab:
            serie = 0
        ergebnis.append(serie)
    return ergebnis


tage = st.sets(st.integers(0, 69), max_size=30)
pausen = st.lists(
    st.tuples(st.integers(0, 69), st.one_of(st.none(), st.integers(0, 15))), max_size=4
)


@given(tage=tage, pausen=pausen, neutral_ab=st.integers(1, 7))
def test_wochenserie_wie_referenz(tage, pausen, neutral_ab):
    start = date(2026, 12, 14)  # über Woche 53 und Jahreswechsel
    aktive = {start + timedelta(days=t) for t in tage}
    p = [
        (start + timedelta(days=v), None if n is None else start + timedelta(days=v + n))
        for v, n in pausen
    ]
    wochen = [IsoWoche.von(start + timedelta(days=7 * i)) for i in range(10)]
    ergebnis = k.wochen_auswerten(aktive, p, wochen[0], wochen[-1], neutral_ab)
    assert [e.wochenserie_danach for e in ergebnis] == _referenz_serie(
        aktive, p, wochen, neutral_ab
    )


@given(tage=tage, pausen=pausen, heute=st.integers(0, 69))
def test_tagesserie_wie_referenz(tage, pausen, heute):
    start = date(2026, 10, 19)
    aktive = {start + timedelta(days=t) for t in tage}
    p = [
        (start + timedelta(days=v), None if n is None else start + timedelta(days=v + n))
        for v, n in pausen
    ]
    stichtag = start + timedelta(days=heute)

    def serie_am(tag):  # rückwärts zählen
        n, t = (1 if tag in aktive else 0), tag - timedelta(days=1)
        while t >= start:
            if t in aktive:
                n += 1
            elif not any(v <= t and (b is None or t <= b) for v, b in p):
                break
            t -= timedelta(days=1)
        return n

    ergebnis = k.tagesserie(aktive, p, stichtag)
    assert ergebnis.tagesserie == serie_am(stichtag)
    rekord = max(
        (serie_am(start + timedelta(days=i)) for i in range(heute + 1)
         if start + timedelta(days=i) in aktive),
        default=0,
    )  # fmt: skip
    assert ergebnis.rekord == rekord
