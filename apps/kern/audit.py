"""Audit-Log (insert-only): wer hat wann was an welchem Objekt getan.

Nie sensible Inhalte: PINs, Passwörter, Tokens, Nachweis-Inhalte. ``details`` wird auf
verbotene Schlüssel und Größe geprüft.
"""

import json
import re

from django.db import models

from .models import AuditEintrag, Rolle

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

__all__ = ["Rolle", "protokollieren", "SensiblerInhalt"]


class SensiblerInhalt(ValueError):
    """``details`` enthält einen verbotenen Schlüssel (z. B. PIN, Passwort, Nachweis)."""


def protokollieren(
    aktion,
    *,
    akteur=None,
    objekt=None,
    objekt_typ="",
    objekt_id="",
    details=None,
    akteur_name=None,
    rolle=None,
):
    """Schreibt einen Audit-Eintrag und gibt ihn zurück.

    - ``akteur``: Benutzer-Objekt (``anzeigename``, ``rolle``) oder ``None`` = System/Job.
    - ``objekt``: Modell-Instanz; setzt ``objekt_typ`` (``app.modell``) und ``objekt_id``.
    - Läuft in der Transaktion des Aufrufers (Rollback = kein Eintrag).
    """
    if not AKTION_MUSTER.match(aktion) or len(aktion) > 80:
        raise ValueError(f"Ungültige Audit-Aktion '{aktion}' (Format 'bereich.ereignis')")

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
    if len(objekt_typ) > 60 or len(objekt_id) > 40:
        raise ValueError("objekt_typ (max. 60) oder objekt_id (max. 40) zu lang")

    details = {} if details is None else details
    _details_pruefen(details)

    return AuditEintrag.objects.create(
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
