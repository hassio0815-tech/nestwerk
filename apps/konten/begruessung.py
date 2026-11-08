from zoneinfo import ZoneInfo

from django.utils.translation import gettext as _

from apps.kern import zeit


def gruss(jetzt=None):
    try:
        zone = zeit.zeitzone()
    except Exception:
        zone = ZoneInfo("Europe/Berlin")
    stunde = (jetzt or zeit.jetzt()).astimezone(zone).hour
    if stunde < 11:
        return _("Guten Morgen")
    if stunde < 18:
        return _("Guten Tag")
    return _("Guten Abend")
