"""OpenAI-kompatibler Chat-Endpunkt (Ollama, vLLM, LiteLLM, eigene Hubs, auch OpenAI selbst).

Die Basis-URL enthält den Versionspfad (z. B. ``http://dein-ki-server:11434/v1``); angefragt wird
``<Basis>/chat/completions``. Der API-Schlüssel ist optional.
"""

import base64

from . import transport
from .basis import Adapter, KiAusgabeFehler, fehler_aus_status, system_mit_json


class OpenAIKompatibel(Adapter):
    #: Name des Token-Limit-Felds (OpenAI selbst verlangt ``max_completion_tokens``)
    token_feld = "max_tokens"

    def _inhalt(self, anfrage):
        if not anfrage.bilder:
            return anfrage.nachricht
        teile = [{"type": "text", "text": anfrage.nachricht}]
        for bild in anfrage.bilder:
            daten = base64.b64encode(bild.daten).decode("ascii")
            teile.append(
                {"type": "image_url", "image_url": {"url": f"data:{bild.mime};base64,{daten}"}}
            )
        return teile

    def _payload(self, anfrage):
        nachrichten = []
        system = system_mit_json(anfrage)
        if system:
            nachrichten.append({"role": "system", "content": system})
        nachrichten.append({"role": "user", "content": self._inhalt(anfrage)})
        payload = {
            "model": self.modell,
            "messages": nachrichten,
            self.token_feld: anfrage.max_tokens,
        }
        if anfrage.json_ausgabe:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _header(self):
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def chat(self, anfrage):
        basis = transport.url_pruefen(self.basis_url)
        status, daten = transport.post_json(
            f"{basis}/chat/completions",
            headers=self._header(),
            payload=self._payload(anfrage),
            timeout=anfrage.timeout,
        )
        if not 200 <= status < 300:
            raise fehler_aus_status(status)
        try:
            text = daten["choices"][0]["message"]["content"]
            nutzung = daten.get("usage") or {}
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise KiAusgabeFehler() from exc
        if isinstance(text, list):  # einige Server liefern Teile
            text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
        return self._fertig(
            text, nutzung.get("prompt_tokens"), nutzung.get("completion_tokens"), anfrage
        )
