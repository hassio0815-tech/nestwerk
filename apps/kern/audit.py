"""Audit-Log (insert-only): wer hat wann was an welchem Objekt getan.

Nie sensible Inhalte: PINs, Passwörter, Tokens, Nachweis-Inhalte. ``details`` wird auf
verbotene Schlüssel und Größe geprüft.
"""

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import models

from .models import OBJEKT_ID_MAX, AuditEintrag, Rolle

AKTION_MUSTER = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
DETAILS_MAX_ZEICHEN = 4000

VERBOTENE_SCHLUESSEL = frozenset(
    {
        "pin",
        "passwort",
        "password",
        "kennwort",
        "geheimnis",
        "secret",
        "token",
        "foto",
        "bild",
        "nachweis_inhalt",
        "inhalt",
    }
)
VERBOTENE_ENDUNGEN = ("_pin", "_passwort", "_password", "_kennwort", "_secret", "_token", "_hash")

__all__ = [
    "AKTUELL",
    "Rolle",
    "SensiblerInhalt",
    "kontext",
    "protokollieren",
]

# Marker für "angemeldeten Akteur aus dem Kontext nehmen" (Standard von ``akteur``).
# ``akteur=None`` bleibt ausdrücklich System/Job.
AKTUELL = object()

# Anbieter für (akteur, geraet) der laufenden Anfrage; ihn setzt die Middleware von konten.
# kern kennt konten nicht: Es wird nur ein Aufruf hinterlegt (Schichtenregel).
_kontext: ContextVar = ContextVar("nestwerk_audit_kontext", default=None)


@contextmanager
def kontext(anbieter):
    """Hinterlegt ``anbieter() -> (akteur | None, geraet | None)`` für Audit-Einträge."""
    token = _kontext.set(anbieter)
    try:
        yield
    finally:
        _kontext.reset(token)


def aktueller_kontext():
    """(akteur, geraet) der laufenden Anfrage; außerhalb einer Anfrage (None, None)."""
    anbieter = _kontext.get()
    return anbieter() if anbieter else (None, None)


def aktueller_akteur():
    return aktueller_kontext()[0]


class SensiblerInhalt(ValueError):
    """``details`` enthält einen verbotenen Schlüssel (z. B. PIN, Passwort, Nachweis)."""


def protokollieren(
    aktion,
    *,
    akteur=AKTUELL,
    objekt=None,
    objekt_typ="",
    objekt_id="",
    details=None,
    akteur_name=None,
    rolle=None,
    kind=None,
    geraet=AKTUELL,
):
    """Schreibt einen Audit-Eintrag und gibt ihn zurück.

    - ``akteur``: Benutzer-Objekt (``anzeigename``, ``rolle``), ``None`` = System/Job. Ohne
      Angabe gilt der angemeldete Benutzer der laufenden Anfrage (sonst System).
    - ``kind``: betroffenes Kind (Benutzer); ``geraet``: Standard = Gerät der Anfrage.
    - ``objekt``: Modell-Instanz; setzt ``objekt_typ`` (``app.modell``) und ``objekt_id``.
    - Läuft in der Transaktion des Aufrufers (Rollback = kein Eintrag).
    """
    if not AKTION_MUSTER.match(aktion) or len(aktion) > 80:
        raise ValueError(f"Ungültige Audit-Aktion '{aktion}' (Format 'bereich.ereignis')")

    kontext_akteur, kontext_geraet = (
        aktueller_kontext() if AKTUELL in (akteur, geraet) else (None, None)
    )
    if akteur is AKTUELL:
        akteur = kontext_akteur
    if geraet is AKTUELL:
        geraet = kontext_geraet
    if akteur is None:
        rolle = rolle or Rolle.SYSTEM
        akteur_name = akteur_name or "System"
    else:
        rolle = rolle or getattr(akteur, "rolle", None)
        akteur_name = akteur_name or getattr(akteur, "anzeigename", None) or str(akteur)
    if rolle not in Rolle.values:
        raise ValueError(f"Ungültige Rolle '{rolle}' für Audit-Eintrag")

    if objekt is not None:
        if not isinstance(objekt, models.Model) or objekt.pk is None:
            raise ValueError("objekt muss eine gespeicherte Modell-Instanz sein")
        objekt_typ = objekt._meta.label_lower
        objekt_id = str(objekt.pk)
    objekt_id = str(objekt_id)
    if len(objekt_typ) > 60 or len(objekt_id) > OBJEKT_ID_MAX:
        raise ValueError(f"objekt_typ (max. 60) oder objekt_id (max. {OBJEKT_ID_MAX}) zu lang")

    details = {} if details is None else details
    _details_pruefen(details)

    return AuditEintrag.objects.create(
        akteur=akteur if isinstance(akteur, models.Model) else None,
        kind=kind,
        geraet=geraet,
        akteur_name=akteur_name[:80],
        rolle=rolle,
        aktion=aktion,
        objekt_typ=objekt_typ,
        objekt_id=objekt_id,
        details=details,
    )


def _details_pruefen(details):
    if not isinstance(details, dict):
        raise ValueError("details muss ein dict sein")
    _schluessel_pruefen(details)
    try:
        text = json.dumps(details)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"details ist nicht JSON-serialisierbar: {exc}") from exc
    if len(text) > DETAILS_MAX_ZEICHEN:
        raise ValueError(f"details ist zu groß (max. {DETAILS_MAX_ZEICHEN} Zeichen)")


def _schluessel_pruefen(wert):
    if isinstance(wert, dict):
        for schluessel, inhalt in wert.items():
            name = str(schluessel).lower()
            if name in VERBOTENE_SCHLUESSEL or name.endswith(VERBOTENE_ENDUNGEN):
                raise SensiblerInhalt(f"Audit-details darf '{schluessel}' nicht enthalten")
            _schluessel_pruefen(inhalt)
    elif isinstance(wert, list | tuple):
        for inhalt in wert:
            _schluessel_pruefen(inhalt)
