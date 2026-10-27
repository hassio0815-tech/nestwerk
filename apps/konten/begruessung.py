from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import translation
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


def gruesse(jetzt=None):
    """Der Gruß in allen Sprachen, aktuelle Sprache zuerst: ``[(code, text), ...]``.
    Der Startbildschirm wechselt damit alle paar Sekunden die Sprache."""
    aktuell = translation.get_language() or settings.LANGUAGE_CODE
    codes = sorted((c for c, _name in settings.LANGUAGES), key=lambda c: c != aktuell[:2])
    ergebnis = []
    for code in codes:
        with translation.override(code):
            ergebnis.append((code, gruss(jetzt)))
    return ergebnis
