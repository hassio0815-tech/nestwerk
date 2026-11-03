"""Szenario über mehrere Wochen: Üben, Lücke, Schonung, Anpassung, Serie.

Zeigt die Zusage aus SPEC 21.2: Eine gerissene Serie löscht nie Punkte, das Ziel sinkt ohne
Vorwurf, Erhöhung gibt es nur als Vorschlag, Schonung hält die Serie."""

from datetime import time, timedelta

from apps.kern import zeit
from apps.lernen import selectors, services, tagesziel
from apps.lernen.models import Lernpause, Lernziel
from apps.punkte import selectors as punkte


def tag_ueben(kind, fach, uhr, tag, minuten):
    """Ein Übungstag: Uhr auf 12:00 des Tages, dann ``minuten`` aktive Zeit."""
    uhr.jetzt = zeit.lokal_zu_utc(tag, time(12, 0))
    s = services.sitzung_starten(kind, fach)
    for _i in range(minuten * 60 // 100):
        uhr.jetzt += timedelta(seconds=100)
        services.frage_stellen(s)
    services.sitzung_beenden(s)
    return s


def test_drei_wochen_serie_luecke_schonung(kind_a, fach, uhr):
    montag = zeit.heute() - timedelta(days=zeit.heute().weekday())
    start = montag  # Montag der laufenden Woche, Uhr wird gestellt
    # Woche 1: drei Tage geübt, davon einmal das ganze Ziel (20 Minuten)
    tag_ueben(kind_a, fach, uhr, start, 21)
    tag_ueben(kind_a, fach, uhr, start + timedelta(days=1), 6)
    tag_ueben(kind_a, fach, uhr, start + timedelta(days=2), 6)
    guthaben = punkte.guthaben(kind_a)
    assert guthaben == 5  # ein Tagesziel, fester Betrag, nicht pro Antwort
    # Danach war die Familie unterwegs und krank: Pause bis zum Ende der zweiten Woche
    Lernpause.objects.create(
        kind=kind_a,
        von=start + timedelta(days=3),
        bis=start + timedelta(weeks=1, days=6),
        grund="krank",
    )
    # Woche 3: wieder geübt
    drei = start + timedelta(weeks=2)
    for i in range(3):
        tag_ueben(kind_a, fach, uhr, drei + timedelta(days=i), 6)
    uhr.jetzt = zeit.lokal_zu_utc(drei + timedelta(days=3), time(12, 0))
    heute = zeit.heute()
    s = tagesziel.serie(kind_a, heute)
    assert s.wochen == 2  # Woche 2 geschont: zählt nicht mit, bricht aber nicht
    # Wer nur den Mindesttag übt, bekommt ein kleineres Ziel (ohne Vorwurf). Schonungstage
    # zählen nie als verfehlt, die Pause hat das Ziel nicht gesenkt.
    ziel = Lernziel.objects.get(kind=kind_a).ziel_minuten
    assert 5 <= ziel < 20

    # Woche 4: Lücke ohne Schonung -> Ziel wird gesenkt, die Serie reißt später, Punkte bleiben
    vier = start + timedelta(weeks=3)
    uhr.jetzt = zeit.lokal_zu_utc(vier + timedelta(days=3), time(12, 0))
    anpassung = services.tag_vorbereiten(kind_a)
    assert (anpassung.art, anpassung.minuten) == ("gesenkt", max(5, ziel - 5))
    assert tagesziel.serie(kind_a, zeit.heute()).wochen == 2  # laufende Woche bricht nie ab
    uhr.jetzt = zeit.lokal_zu_utc(vier + timedelta(weeks=1), time(12, 0))
    assert tagesziel.serie(kind_a, zeit.heute()).wochen == 0  # gerissen
    assert punkte.guthaben(kind_a) == guthaben  # ... aber keine Punkte gehen verloren
    assert selectors.tage_geuebt(kind_a) == 6
