"""Cloud-Erkennung (SPEC 21.6): Anthropic und OpenAI sind immer Cloud; bei OpenAI-kompatiblen
Adressen gelten nur localhost, ``.local``/``.localhost``/``.home.arpa``, einfache Rechnernamen
ohne Punkt und private/Loopback-/Link-Local-IP-Adressen als lokal. Im Zweifel: Cloud."""

import ipaddress
from urllib.parse import urlsplit

ANTHROPIC = "anthropic"
OPENAI = "openai"
OPENAI_KOMPATIBEL = "openai_kompatibel"

_LOKALE_ENDUNGEN = (".local", ".localhost", ".home.arpa")


def ist_cloud(typ, basis_url):
    if typ in (ANTHROPIC, OPENAI):
        return True
    try:
        teile = urlsplit((basis_url or "").strip())
        host = (teile.hostname or "").lower().rstrip(".")
    except ValueError:
        return True
    if not host or teile.scheme not in ("http", "https"):
        return True
    try:
        adresse = ipaddress.ip_address(host)
    except ValueError:
        return not (host == "localhost" or host.endswith(_LOKALE_ENDUNGEN) or "." not in host)
    if getattr(adresse, "ipv4_mapped", None):
        adresse = adresse.ipv4_mapped
    return not (adresse.is_private or adresse.is_loopback or adresse.is_link_local)
