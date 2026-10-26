"""Tageszeit-Gruß für Begrüßung und Einrichtungs-Start (in der Zeitzone der Familie)."""

from zoneinfo import ZoneInfo

from apps.kern import zeit


def gruss(jetzt=None):
    try:
        zone = zeit.zeitzone()
    except Exception:
        zone = ZoneInfo("Europe/Berlin")
    stunde = (jetzt or zeit.jetzt()).astimezone(zone).hour
    if stunde < 11:
        return "Guten Morgen"
    if stunde < 18:
        return "Guten Tag"
    return "Guten Abend"
