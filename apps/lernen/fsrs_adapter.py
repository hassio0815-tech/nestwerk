"""FSRS-Adapter (Etappe 12, W-4): Stabilität und Schwierigkeit je Lernstand statt fester Boxen.

Die Bibliothek ``fsrs`` (py-fsrs, MIT) rechnet mit Standardparametern, ohne Optimierung je Kind.
Dieses Modul kapselt sie:

- Alles läuft in ganzen Tagen (keine Lernschritte in Minuten), ohne Zufall (kein Fuzzing).
- Ziel-Retention und Höchstabstand kommen aus den Einstellungen (Standard 90 % und 60 Tage).
- "Noch nicht" kommt immer morgen wieder (Frust vermeiden), egal was die Formel sagt.
- Fehlt die Bibliothek oder wählen die Eltern Leitner, gilt ``algorithmus() == "leitner"`` und
  ``wiederholung`` rechnet mit den Boxen wie bisher.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from apps.kern.einstellungen import wert

try:
    import fsrs
except ImportError:  # pragma: no cover  (die Tests ersetzen das Modul durch None)
    fsrs = None

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4  # wie fsrs.Rating, aber ohne die Bibliothek nutzbar

ALGORITHMUS_FSRS = "fsrs"
ALGORITHMUS_LEITNER = "leitner"

HILFE_HART_AB = 3  # ab dieser Hilfestufe zählt eine richtige Antwort nur als "schwer"
START_SCHWIERIGKEIT = 5.0  # für Stände, die aus einer Leitner-Box übernommen werden


@dataclass(frozen=True)
class Stand:
    stabilitaet: float
    schwierigkeit: float
    abstand_tage: int


def algorithmus():
    """Der wirksame Algorithmus: FSRS nur, wenn gewählt *und* die Bibliothek da ist."""
    if fsrs is not None and wert("lernen.wiederholung_algorithmus") == ALGORITHMUS_FSRS:
        return ALGORITHMUS_FSRS
    return ALGORITHMUS_LEITNER


def bewertung(richtig, hilfestufe, dauer_ms=None, median_ms=None):
    """Bewertung einer Antwort: nicht richtig = Again; richtig mit viel Hilfe = Hard; richtig mit
    wenig Hilfe = Good; richtig ohne Hilfe und schneller als der Median des Kindes = Easy."""
    if not richtig:
        return AGAIN
    if hilfestufe >= HILFE_HART_AB:
        return HARD
    if hilfestufe == 0 and dauer_ms is not None and median_ms and dauer_ms < median_ms:
        return EASY
    return GOOD


def _scheduler():
    return fsrs.Scheduler(
        desired_retention=wert("lernen.fsrs_ziel_retention_prozent") / 100,
        learning_steps=(),
        relearning_steps=(),
        maximum_interval=wert("lernen.fsrs_hoechstabstand_tage"),
        enable_fuzzing=False,
    )


def _utc(tag):
    return datetime.combine(tag, time(), tzinfo=UTC)


def fortschreiben(stabilitaet, schwierigkeit, zuletzt, heute, bew):
    """Neuer Stand nach einer Antwort am Tag ``heute``.

    ``stabilitaet`` und ``schwierigkeit`` sind ``None`` bei der ersten Antwort. ``zuletzt`` ist der
    Tag der Antwort davor (fehlt er, gilt gestern)."""
    if fsrs is None:
        raise RuntimeError("fsrs ist nicht installiert")
    zeitplan = _scheduler()
    if stabilitaet is None:
        karte = fsrs.Card()
    else:
        karte = fsrs.Card(
            state=fsrs.State.Review,
            step=None,
            stability=stabilitaet,
            difficulty=schwierigkeit,
            due=_utc(heute),
            last_review=_utc(min(zuletzt or heute - timedelta(days=1), heute)),
        )
    karte, _log = zeitplan.review_card(karte, fsrs.Rating(bew), _utc(heute))
    abstand = max(1, (karte.due - _utc(heute)).days)
    if bew == AGAIN:
        abstand = 1
    return Stand(karte.stability, karte.difficulty, min(abstand, zeitplan.maximum_interval))


def nominale_abstaende(anzahl):
    """Die Abstände, wenn eine Karte jedes Mal richtig (Good) beantwortet wird: Grundlage für
    den Prüfungsplan, solange es keine echte Fälligkeit gibt."""
    abstaende, stab, schw, zuletzt, tag = [], None, None, None, date(2026, 1, 1)
    for _ in range(anzahl):
        neu = fortschreiben(stab, schw, zuletzt, tag, GOOD)
        abstaende.append(neu.abstand_tage)
        stab, schw, zuletzt = neu.stabilitaet, neu.schwierigkeit, tag
        tag += timedelta(days=neu.abstand_tage)
    return abstaende
