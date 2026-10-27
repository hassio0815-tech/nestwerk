"""Ruhezeiten (ARCHITECTURE 5.3, K7): reine Logik ohne DB.

Ein Fenster ``von``–``bis`` gilt an den Wochentagen der Bitmaske (Mo=1 … So=64) und beginnt an
diesem Tag. Ein Fenster über Mitternacht (``bis < von``) reicht in den Folgetag; der Teil nach
Mitternacht gehört zum Wochentag, an dem das Fenster begann. ``von == bis`` = ganzer Tag.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.kern import zeit
from apps.kern.einstellungen import EinstellungFehlt

from . import registry

ALLE_TAGE = 127
TAGE = (_("Mo"), _("Di"), _("Mi"), _("Do"), _("Fr"), _("Sa"), _("So"))


def tag_bit(wochentag):
    """``date.weekday()`` (Mo=0) -> Bit."""
    return 1 << (wochentag % 7)


def tage_liste(maske):
    return [i for i in range(7) if maske & tag_bit(i)]


def fenster_aktiv(ruhezeit, lokal):
    """Liegt die lokale Zeit ``lokal`` im Fenster?"""
    if not ruhezeit.aktiv:
        return False
    t = lokal.time()
    heute = ruhezeit.wochentage & tag_bit(lokal.weekday())
    gestern = ruhezeit.wochentage & tag_bit((lokal - timedelta(days=1)).weekday())
    if ruhezeit.von == ruhezeit.bis:
        return bool(heute)
    if ruhezeit.von < ruhezeit.bis:
        return bool(heute) and ruhezeit.von <= t < ruhezeit.bis
    return (bool(heute) and t >= ruhezeit.von) or (bool(gestern) and t < ruhezeit.bis)


def _lokal(moment):
    """Lokale Zeit in der Fach-Zeitzone; vor Abschluss der Einrichtung (Zeitzone noch nicht
    gesetzt) gilt ``settings.TIME_ZONE``, damit der Router nie daran scheitert."""
    try:
        return zeit.lokal(moment)
    except EinstellungFehlt:
        return zeit.lokal(moment, ZoneInfo(settings.TIME_ZONE))


def unterdrueckt(ruhezeiten, kanal_slug, moment=None):
    """Soll der Kanal zum Zeitpunkt ``moment`` (Standard: jetzt) stumm bleiben?"""
    wirkung = registry.kanal(kanal_slug).ruhezeit
    if wirkung == registry.NIE:
        return False
    lokal = _lokal(moment or zeit.jetzt())
    for r in ruhezeiten:
        if wirkung == registry.OPTIONAL and not r.gilt_fuer_email:
            continue
        if fenster_aktiv(r, lokal):
            return True
    return False
