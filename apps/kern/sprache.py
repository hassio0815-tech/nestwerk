"""Sprache außerhalb einer Anfrage (Push, Mail, Worker) und Anzeige von Start-Inhalten.
Siehe docs/i18n.md."""

from django.conf import settings
from django.utils.translation import gettext

from . import einstellungen

CODES = tuple(code for code, _name in settings.LANGUAGES)


def familie():
    """Familien-Sprache (Einstellung ``allgemein.sprache``), sonst Deutsch."""
    try:
        wert = einstellungen.wert("allgemein.sprache")
    except Exception:
        return settings.LANGUAGE_CODE
    return wert if wert in CODES else settings.LANGUAGE_CODE


def fuer(benutzer):
    """Sprache für Texte an ``benutzer``: eigene Sprache, sonst Familien-Sprache."""
    eigene = getattr(benutzer, "sprache", "") if benutzer else ""
    return eigene if eigene in CODES else familie()


def uebersetzt(text):
    """Start-Inhalte aus der Datenbank (Ränge, Abzeichen, Kategorien …) sind deutsche msgids
    (mit ``gettext_noop`` markiert). Unbekannte Texte, z. B. von Eltern umbenannt, bleiben."""
    return gettext(text) if text else text
