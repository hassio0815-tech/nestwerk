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
    """Ab hier ist ``woche`` endgültig: Wochenende plus Puffer von spielregeln (K1). Gleiche
    Rechnung wie der Wochenabschluss der Kinder (lokale Wanduhr, auch über Zeitumstellungen bei
    großem Puffer; Review AP31)."""
    from apps.spielregeln import selectors as spielregeln

    return spielregeln.woche_abgeschlossen_ab(woche)
