"""OpenAI (Cloud): derselbe Chat-Endpunkt wie die kompatible Variante, feste Standard-URL."""

from .openai_kompatibel import OpenAIKompatibel

STANDARD_URL = "https://api.openai.com/v1"


class OpenAI(OpenAIKompatibel):
    token_feld = "max_completion_tokens"

    def __init__(self, *, basis_url="", modell, api_key=""):
        super().__init__(basis_url=basis_url or STANDARD_URL, modell=modell, api_key=api_key)
