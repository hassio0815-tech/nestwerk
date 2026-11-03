"""Gemeinsame Schnittstelle der KI-Anbieter (SPEC 21.6): Anfrage, Antwort, Fehlerklassen.

Reine Python-Schicht ohne Django-Modelle. Inhalte (System-Prompt, Texte, Bilder) stehen nie in
``repr``, Fehlermeldungen oder Logs; der API-Schlüssel nie in ``repr`` des Adapters.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

# --- Fehlerklassen -------------------------------------------------------------------------------


class KiFehler(Exception):
    """Basis aller KI-Fehler. ``art`` ist ein stabiler Code (für Anzeige/Protokoll), die
    Meldung enthält nie Inhalte oder Schlüssel. ``wiederholbar``: ein späterer Versuch kann
    klappen (Netz, Limit, Serverfehler)."""

    art = "fehler"
    wiederholbar = False

    def __init__(self, status=None):
        self.status = status
        super().__init__(f"{self.art}" + (f" (HTTP {status})" if status else ""))


class KiKonfigurationsFehler(KiFehler):
    art = "konfiguration"


class KiVerbindungsFehler(KiFehler):
    art = "verbindung"
    wiederholbar = True


class KiZeitueberschreitung(KiFehler):
    art = "zeitueberschreitung"
    wiederholbar = True


class KiAuthFehler(KiFehler):
    art = "auth"


class KiLimitFehler(KiFehler):
    art = "limit"
    wiederholbar = True


class KiServerFehler(KiFehler):
    art = "server"
    wiederholbar = True


class KiAnfrageFehler(KiFehler):
    art = "anfrage"


class KiAusgabeFehler(KiFehler):
    """Antwort ist leer, unlesbar oder kein gültiges JSON."""

    art = "ausgabe"
    wiederholbar = True


class KiNichtVerfuegbar(KiFehler):
    """Aufgabe ohne Zuordnung oder Anbieter nicht aktiv: KI ist für diese Aufgabe aus."""

    art = "aus"


class KiEinwilligungFehlt(KiNichtVerfuegbar):
    art = "einwilligung"


def fehler_aus_status(status):
    """Ordnet einen HTTP-Status einer Fehlerklasse zu (nur Status, nie der Antworttext)."""
    if status in (401, 403):
        return KiAuthFehler(status)
    if status == 429:
        return KiLimitFehler(status)
    if status in (408, 504):
        return KiZeitueberschreitung(status)
    if status >= 500:
        return KiServerFehler(status)
    return KiAnfrageFehler(status)


# --- Anfrage und Antwort -------------------------------------------------------------------------


@dataclass(frozen=True)
class KiBild:
    mime: str
    daten: bytes = field(repr=False)


@dataclass(frozen=True)
class KiAnfrage:
    """Text-Chat mit Systemprompt, optional Bilder und strukturierte JSON-Ausgabe."""

    system: str = field(repr=False)
    nachricht: str = field(repr=False)
    bilder: tuple = field(default=(), repr=False)
    json_ausgabe: bool = False
    schema: dict | None = field(default=None, repr=False)
    max_tokens: int = 1024
    timeout: float = 60.0


@dataclass(frozen=True)
class KiAntwort:
    text: str = field(repr=False)
    json: Any = field(default=None, repr=False)
    tokens_ein: int | None = None
    tokens_aus: int | None = None


JSON_HINWEIS = "Respond only with valid JSON. No explanations, no Markdown."


def system_mit_json(anfrage):
    """Systemprompt, bei JSON-Ausgabe um die Anweisung (und optional das Schema) ergänzt."""
    if not anfrage.json_ausgabe:
        return anfrage.system
    teile = [anfrage.system, JSON_HINWEIS]
    if anfrage.schema is not None:
        teile.append("JSON schema: " + json.dumps(anfrage.schema, ensure_ascii=False))
    return "\n\n".join(t for t in teile if t)


_ZAUN = re.compile(r"^```[a-zA-Z0-9]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def json_parsen(text):
    """Liest JSON aus einer Modellantwort (auch in Code-Zäunen); sonst ``KiAusgabeFehler``."""
    roh = (text or "").strip()
    zaun = _ZAUN.match(roh)
    if zaun:
        roh = zaun.group(1).strip()
    try:
        return json.loads(roh)
    except ValueError as exc:
        raise KiAusgabeFehler() from exc


def zahl(wert):
    return wert if isinstance(wert, int) and not isinstance(wert, bool) else None


class Adapter:
    """Basis der Anbieter-Adapter. ``chat(anfrage) -> KiAntwort``."""

    def __init__(self, *, basis_url, modell, api_key=""):
        self.basis_url = (basis_url or "").strip()
        self.modell = (modell or "").strip()
        self._api_key = api_key or ""

    def __repr__(self):
        return f"<{type(self).__name__} modell={self.modell!r}>"

    def chat(self, anfrage):  # pragma: no cover - Schnittstelle
        raise NotImplementedError

    def _fertig(self, text, tokens_ein, tokens_aus, anfrage):
        text = text if isinstance(text, str) else ""
        if not text.strip():
            raise KiAusgabeFehler()
        daten = json_parsen(text) if anfrage.json_ausgabe else None
        return KiAntwort(
            text=text, json=daten, tokens_ein=zahl(tokens_ein), tokens_aus=zahl(tokens_aus)
        )
