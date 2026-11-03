"""KI-Adapter von lernen (Etappe 3, SPEC 21.6): drei Typen hinter einer Schnittstelle."""

from .anthropic import Anthropic
from .basis import (
    Adapter,
    KiAnfrage,
    KiAnfrageFehler,
    KiAntwort,
    KiAusgabeFehler,
    KiAuthFehler,
    KiBild,
    KiEinwilligungFehlt,
    KiFehler,
    KiKonfigurationsFehler,
    KiLimitFehler,
    KiNichtVerfuegbar,
    KiServerFehler,
    KiVerbindungsFehler,
    KiZeitueberschreitung,
)
from .cloud import ANTHROPIC, OPENAI, OPENAI_KOMPATIBEL, ist_cloud
from .openai import OpenAI
from .openai_kompatibel import OpenAIKompatibel

ADAPTER = {
    OPENAI_KOMPATIBEL: OpenAIKompatibel,
    ANTHROPIC: Anthropic,
    OPENAI: OpenAI,
}


def adapter_erzeugen(typ, *, basis_url, modell, api_key=""):
    klasse = ADAPTER.get(typ)
    if klasse is None or not (modell or "").strip():
        raise KiKonfigurationsFehler()
    return klasse(basis_url=basis_url, modell=modell, api_key=api_key)


__all__ = [
    "ADAPTER",
    "Adapter",
    "KiAnfrage",
    "KiAnfrageFehler",
    "KiAntwort",
    "KiAuthFehler",
    "KiAusgabeFehler",
    "KiBild",
    "KiEinwilligungFehlt",
    "KiFehler",
    "KiKonfigurationsFehler",
    "KiLimitFehler",
    "KiNichtVerfuegbar",
    "KiServerFehler",
    "KiVerbindungsFehler",
    "KiZeitueberschreitung",
    "adapter_erzeugen",
    "ist_cloud",
]
