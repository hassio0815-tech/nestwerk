"""Kanal-Registry (ARCHITECTURE 5.3). Kanäle sind Klassen mit gemeinsamer Schnittstelle:

    class HomeAssistantKanal(ZustellKanal):
        slug = "homeassistant"
        bezeichnung = "Home Assistant"
        rollen = ("eltern",)
        def senden(self, zustellung): ...      # NichtKonfiguriert / DauerhafterFehler / Exception

    registry.kanal_registrieren(HomeAssistantKanal())          # in AppConfig.ready()
    registry.kanal_registrieren(PushKanal(), ersetzen=True)    # Platzhalter ersetzen (AP08)

``senden`` läuft im Worker außerhalb einer DB-Transaktion (Netzwerk-I/O erlaubt). Nach
Rückkehr gilt die Zustellung als gesendet; Ausnahmen steuern den Status:

- ``NichtKonfiguriert``: Status ``nicht_konfiguriert`` (kein Retry, kein Alarm),
- ``DauerhafterFehler``: Status ``aufgegeben`` (kein Retry),
- jede andere Ausnahme: Retry mit Backoff, nach ``benachrichtigung.zustellung_max_versuche``
  ``aufgegeben``.
"""

from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext

from apps.kern.registry import UnbekannterEintrag

__all__ = [
    "DauerhafterFehler",
    "NichtKonfiguriert",
    "UnbekannterEintrag",
    "ZustellKanal",
    "isoliert",
    "kanaele",
    "kanal",
    "kanal_registrieren",
]

IMMER = "immer"  # Ruhezeit unterdrückt den Kanal
OPTIONAL = "optional"  # nur wenn die Ruhezeit es für diesen Kanal verlangt (E-Mail, K7)
NIE = "nie"  # Ruhezeit wirkt nicht (Pop-up)


class NichtKonfiguriert(Exception):
    """Kanal ist (noch) nicht eingerichtet; wird protokolliert, nicht wiederholt."""


class DauerhafterFehler(Exception):
    """Zustellung ist unmöglich (z. B. keine Adresse); kein Retry."""


class ZustellKanal:
    slug = ""
    bezeichnung = ""
    rollen = ("eltern", "kind")  # Empfänger-Rollen, für die der Kanal gilt
    ruhezeit = IMMER

    @property
    def anzeigename(self):
        """Bezeichnung in der aktiven Sprache (``bezeichnung`` ist die deutsche Msgid)."""
        return gettext(self.bezeichnung)

    def ziele(self, benutzer):
        """Ziele je Empfänger: eine Zustellung je Eintrag (``None`` = ohne Ziel-Objekt).
        Push liefert hier die aktiven ``PushAbo`` des Benutzers (AP08)."""
        return [None]

    def senden(self, zustellung):
        raise NotImplementedError


_kanaele = {}


def kanal_registrieren(instanz, *, ersetzen=False):
    if not instanz.slug or len(instanz.slug) > 30:
        raise ImproperlyConfigured("Kanal braucht einen slug (max. 30 Zeichen)")
    if instanz.slug in _kanaele and not ersetzen:
        raise ImproperlyConfigured(f"Kanal '{instanz.slug}' ist doppelt registriert")
    _kanaele[instanz.slug] = instanz
    return instanz


def kanal(slug):
    try:
        return _kanaele[slug]
    except KeyError:
        raise UnbekannterEintrag(f"Kanal '{slug}' ist nicht registriert") from None


def kanaele():
    return [_kanaele[s] for s in sorted(_kanaele)]


@contextmanager
def isoliert():
    """Für Tests: Kanäle werden danach zurückgesetzt."""
    stand = dict(_kanaele)
    try:
        yield
    finally:
        _kanaele.clear()
        _kanaele.update(stand)
