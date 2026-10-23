"""Zeit-Utilities: einzige Stelle für "heute", ISO-Woche und App-Jahr (ARCHITECTURE 1).

- Intern UTC (aware). Fachliche Tage/Wochen in der Zeitzone ``allgemein.zeitzone``.
- Woche = ISO-Woche Montag–Sonntag (Woche 53 möglich, Jahreswechsel nach ISO-Regel).
- Intervalle sind halboffen ``[beginn, ende)`` in UTC; ein Tag hat bei Zeitumstellung
  23 bzw. 25 Stunden.
- Funktionen mit ``tz=None`` lesen die Zeitzone aus der Einstellung.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from . import einstellungen


class VorGoLive(ValueError):
    """Datum liegt vor dem Go-live-Datum (kein App-Jahr)."""


def zeitzone():
    return ZoneInfo(einstellungen.wert("allgemein.zeitzone"))


def jetzt():
    """Aktueller Zeitpunkt, aware, UTC."""
    return timezone.now()


def lokal(moment, tz=None):
    """Aware Zeitpunkt -> lokale Zeit der Fach-Zeitzone."""
    if timezone.is_naive(moment):
        raise ValueError("Naive datetime: Zeitpunkte müssen aware sein")
    return moment.astimezone(tz or zeitzone())


def heute(moment=None, tz=None):
    """Fachliches Datum (lokal) für ``moment`` (Standard: jetzt)."""
    return lokal(moment or jetzt(), tz).date()


def lokal_zu_utc(tag, uhrzeit, tz=None):
    """Lokales Datum + Uhrzeit -> aware UTC.

    DST-Regeln: Uhrzeit in der Lücke (Frühjahr, 02:30) wird um die Lückenlänge nach vorn
    verschoben (-> 03:30); doppelte Uhrzeit (Herbst, 02:30) = erstes Auftreten (Sommerzeit).
    """
    tz = tz or zeitzone()
    return datetime.combine(tag, uhrzeit, tzinfo=tz).replace(fold=0).astimezone(UTC)


def tag_beginn(tag, tz=None):
    """Lokale Mitternacht von ``tag`` als UTC-Zeitpunkt."""
    return lokal_zu_utc(tag, time.min, tz)


def tag_intervall(tag, tz=None):
    """``(beginn, ende)`` von ``tag`` in UTC, halboffen."""
    tz = tz or zeitzone()
    return tag_beginn(tag, tz), tag_beginn(tag + timedelta(days=1), tz)


# --- ISO-Woche -------------------------------------------------------------------------------


def anzahl_iso_wochen(jahr):
    """52 oder 53. Der 28.12. liegt immer in der letzten ISO-Woche des Jahres."""
    return date(jahr, 12, 28).isocalendar().week


@dataclass(frozen=True, order=True, slots=True)
class IsoWoche:
    jahr: int
    woche: int

    def __post_init__(self):
        if not 1 <= self.woche <= anzahl_iso_wochen(self.jahr):
            raise ValueError(f"ISO-Woche {self.jahr}-W{self.woche:02d} existiert nicht")

    @classmethod
    def von(cls, wann, tz=None):
        """ISO-Woche eines Datums oder (aware) Zeitpunkts (lokal ausgewertet)."""
        if isinstance(wann, datetime):
            wann = heute(wann, tz)
        jahr, woche, _ = wann.isocalendar()
        return cls(jahr, woche)

    @property
    def montag(self):
        return date.fromisocalendar(self.jahr, self.woche, 1)

    @property
    def sonntag(self):
        return date.fromisocalendar(self.jahr, self.woche, 7)

    def tage(self):
        return [self.montag + timedelta(days=i) for i in range(7)]

    def naechste(self):
        return IsoWoche.von(self.montag + timedelta(days=7))

    def vorherige(self):
        return IsoWoche.von(self.montag - timedelta(days=7))

    def intervall(self, tz=None):
        """``(beginn, ende)`` in UTC: Montag 00:00 bis nächster Montag 00:00 lokal."""
        tz = tz or zeitzone()
        return tag_beginn(self.montag, tz), tag_beginn(self.montag + timedelta(days=7), tz)

    def __str__(self):
        return f"{self.jahr}-W{self.woche:02d}"


def aktuelle_woche(moment=None, tz=None):
    return IsoWoche.von(moment or jetzt(), tz)


# --- App-Jahr --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppJahr:
    """App-Jahr ``nummer`` (ab 1) = ``[beginn, ende)`` als lokale Daten."""

    nummer: int
    beginn: date
    ende: date

    def enthaelt(self, tag):
        return self.beginn <= tag < self.ende


def go_live_datum():
    return einstellungen.wert("allgemein.go_live_datum")


def _jahrestag(start, jahre):
    """``start`` plus ``jahre`` Jahre; 29.02. -> 28.02. in Nicht-Schaltjahren."""
    try:
        return start.replace(year=start.year + jahre)
    except ValueError:
        return date(start.year + jahre, 2, 28)


def app_jahr_nummer(nummer, go_live=None):
    """App-Jahr ``nummer`` (1 = ab Go-live)."""
    if nummer < 1:
        raise ValueError("App-Jahre beginnen bei 1")
    go_live = go_live or go_live_datum()
    return AppJahr(nummer, _jahrestag(go_live, nummer - 1), _jahrestag(go_live, nummer))


def app_jahr(wann=None, go_live=None, tz=None):
    """App-Jahr eines Datums oder Zeitpunkts (Standard: heute). Vor Go-live -> ``VorGoLive``."""
    if wann is None or isinstance(wann, datetime):
        wann = heute(wann, tz)
    go_live = go_live or go_live_datum()
    if wann < go_live:
        raise VorGoLive(f"{wann} liegt vor dem Go-live-Datum {go_live}")
    jahre = wann.year - go_live.year
    if _jahrestag(go_live, jahre) > wann:
        jahre -= 1
    return app_jahr_nummer(jahre + 1, go_live)
