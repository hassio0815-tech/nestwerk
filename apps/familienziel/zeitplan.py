"""Zeitfenster von familienziel: Abstimmung und Wochenabschluss (alles aus Einstellungen)."""

from datetime import time, timedelta

from apps.kern import einstellungen, zeit


def abstimmung_fenster(zielwoche):
    """``(beginn, ende)`` in UTC (halboffen) der Abstimmung für ``zielwoche``.

    Der Abstimmungstag liegt in der Woche davor (Startwert Sonntag, 00:00 bis 23:59). Das Ende
    ``23:59`` bedeutet Tagesende; das Fenster endet nie nach Beginn der Zielwoche."""
    werte = einstellungen.werte(
        "familienziel.abstimmung_tag",
        "familienziel.abstimmung_beginn",
        "familienziel.abstimmung_ende",
    )
    tag = zielwoche.vorherige().montag + timedelta(days=werte["familienziel.abstimmung_tag"] - 1)
    beginn = zeit.lokal_zu_utc(tag, werte["familienziel.abstimmung_beginn"])
    schluss = werte["familienziel.abstimmung_ende"]
    tagesende = zeit.tag_beginn(tag + timedelta(days=1))
    ende = tagesende if schluss >= time(23, 59) else zeit.lokal_zu_utc(tag, schluss)
    if ende <= beginn:
        ende = tagesende
    return beginn, min(ende, zeit.tag_beginn(zielwoche.montag))


def abstimmung_offen_zeitlich(zielwoche, jetzt):
    beginn, ende = abstimmung_fenster(zielwoche)
    return beginn <= jetzt < ende


def abschluss_zeitpunkt(woche):
    """Ab hier ist ``woche`` endgültig: Wochenende plus Puffer von spielregeln (K1)."""
    puffer = einstellungen.wert("spielregeln.puffer_stunden")
    return zeit.tag_beginn(woche.montag + timedelta(days=7)) + timedelta(hours=puffer)
