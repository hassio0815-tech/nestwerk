"""Sprache außerhalb einer Anfrage (Push, Mail, Worker) und Anzeige von Start-Inhalten.
Siehe docs/i18n.md."""

import re

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


_muster = []


def muster_registrieren(regex, msgid):
    """Für erzeugte Namen (z. B. ``"<Mod> · Set 2"``): ``regex`` (benannte Gruppen, ganzer
    Text) zerlegt den Namen, ``msgid`` (``%(gruppe)s``-Platzhalter, mit ``gettext_noop``
    markiert) setzt ihn in der aktiven Sprache wieder zusammen. Die Gruppen werden selbst
    übersetzt."""
    _muster.append((re.compile(regex), msgid))


def uebersetzt(text):
    """Start-Inhalte aus der Datenbank (Ränge, Abzeichen, Kategorien …) sind deutsche msgids
    (mit ``gettext_noop`` markiert). Unbekannte Texte, z. B. von Eltern umbenannt, bleiben."""
    if not text:
        return text
    uebersetzung = gettext(text)
    if uebersetzung != text:
        return uebersetzung
    for regex, msgid in _muster:
        treffer = regex.fullmatch(text)
        if treffer:
            teile = {name: uebersetzt(wert) for name, wert in treffer.groupdict().items()}
            return gettext(msgid) % teile
    return text
