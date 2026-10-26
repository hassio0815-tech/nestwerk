"""Fälligkeitsberechnung aus dem ``Plan`` (reine Logik, ohne Datenbank).

- ``termine(plan, von, bis, start=...)``: alle Plan-Tage im geschlossenen Bereich ``[von, bis]``
  (lokale Daten), begrenzt durch Start/Ende des Plans.
- ``fenster(plan, tag, tz)``: ``(fenster_start, fenster_ende)`` als aware UTC. DST-sicher über
  ``kern.zeit.lokal_zu_utc`` (Lücke -> nach vorn, doppelte Stunde -> erstes Auftreten).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from apps.kern import zeit

from . import wiederholung
from .wiederholung import Plan


def termine(plan: Plan, von: date, bis: date, *, start: date | None = None) -> list[date]:
    """Plan-Tage in ``[von, bis]``. ``start`` ersetzt ein fehlendes ``plan.start_datum``."""
    anfang = plan.start_datum or start
    if anfang is None:
        return []
    ende = min(bis, plan.end_datum) if plan.end_datum else bis
    unten = max(von, anfang)
    if unten > ende:
        return []

    if plan.art == wiederholung.EINMALIG:
        return [anfang] if von <= anfang <= ende else []

    if plan.art == wiederholung.WOECHENTLICH:
        maske = plan.wochentage or 0
        tage = (ende - unten).days + 1
        kandidaten = (unten + timedelta(days=i) for i in range(tage))
        return [t for t in kandidaten if maske & (1 << t.weekday())]

    if plan.art == wiederholung.INTERVALL:
        schritt = plan.intervall_tage or 0
        if schritt < 1:
            return []
        versatz = (unten - anfang).days
        tag = anfang + timedelta(days=-(-versatz // schritt) * schritt)
        ergebnis = []
        while tag <= ende:
            ergebnis.append(tag)
            tag += timedelta(days=schritt)
        return ergebnis

    return []


def fenster(plan: Plan, tag: date, tz=None) -> tuple[datetime, datetime | None]:
    """Zeitfenster am Fälligkeitstag ``tag``. Ohne Frist ist ``fenster_ende`` ``None``.

    Frist 00:00 ohne Beginn und ohne Zusatztage gilt als Tagesende (24:00).
    """
    tz = tz or zeit.zeitzone()
    beginn = zeit.lokal_zu_utc(tag, plan.fenster_von or time.min, tz)
    if plan.fenster_bis is None:
        return beginn, None
    ende_tag = tag + timedelta(days=plan.fenster_tage or 0)
    if plan.fenster_bis == time.min and not plan.fenster_tage and plan.fenster_von is None:
        ende_tag += timedelta(days=1)  # "bis 00:00" = Tagesende
    ende = zeit.lokal_zu_utc(ende_tag, plan.fenster_bis, tz)
    if ende <= beginn:
        # Fenster liegt ganz in der Frühjahrs-Lücke (z. B. 02:15–02:45): minimal statt leer
        ende = beginn + timedelta(minutes=1)
    return beginn, ende
