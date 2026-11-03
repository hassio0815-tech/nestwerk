"""Anthropic (Cloud): Messages-API (``<Basis>/v1/messages``)."""

import base64

from . import transport
from .basis import Adapter, KiAusgabeFehler, fehler_aus_status, system_mit_json

STANDARD_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


class Anthropic(Adapter):
    def __init__(self, *, basis_url="", modell, api_key=""):
        super().__init__(basis_url=basis_url or STANDARD_URL, modell=modell, api_key=api_key)

    def _payload(self, anfrage):
        inhalt = []
        for bild in anfrage.bilder:
            daten = base64.b64encode(bild.daten).decode("ascii")
            inhalt.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": bild.mime, "data": daten},
                }
            )
        inhalt.append({"type": "text", "text": anfrage.nachricht})
        payload = {
            "model": self.modell,
            "max_tokens": anfrage.max_tokens,
            "messages": [{"role": "user", "content": inhalt}],
        }
        system = system_mit_json(anfrage)
        if system:
            payload["system"] = system
        return payload

    def chat(self, anfrage):
        basis = transport.url_pruefen(self.basis_url)
        if basis.endswith("/v1"):
            basis = basis[: -len("/v1")]
        header = {"anthropic-version": API_VERSION}
        if self._api_key:
            header["x-api-key"] = self._api_key
        status, daten = transport.post_json(
            f"{basis}/v1/messages",
            headers=header,
            payload=self._payload(anfrage),
            timeout=anfrage.timeout,
        )
        if not 200 <= status < 300:
            raise fehler_aus_status(status)
        try:
            bloecke = daten["content"]
            text = "".join(b.get("text", "") for b in bloecke if b.get("type") == "text")
            nutzung = daten.get("usage") or {}
        except (KeyError, TypeError, AttributeError) as exc:
            raise KiAusgabeFehler() from exc
        return self._fertig(
            text, nutzung.get("input_tokens"), nutzung.get("output_tokens"), anfrage
        )
