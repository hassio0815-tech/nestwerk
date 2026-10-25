"""Lesender Zustand des Assistenten: abgeschlossen? Welcher Schritt ist freigegeben?"""

import hmac
import ipaddress

from apps.kern import einstellungen
from apps.kern.umgebung import umgebung
from apps.konten import netz

PRAEFIX = "/einrichtung/"
TOKEN_VARIABLE = "SETUP_TOKEN"  # NESTWERK_SETUP_TOKEN, Fallback FAMKO_SETUP_TOKEN
SESSION_TOKEN_OK = "einrichtung_token_ok"


def abgeschlossen():
    try:
        return bool(einstellungen.wert("allgemein.einrichtung_abgeschlossen"))
    except einstellungen.EinstellungFehlt:
        return False


def freigegebener_schritt():
    try:
        return einstellungen.wert("einrichtung.schritt")
    except einstellungen.EinstellungFehlt:
        return 1


def erwartetes_token():
    return umgebung(TOKEN_VARIABLE, "").strip()


def token_stimmt(eingabe):
    erwartet = erwartetes_token()
    return bool(erwartet) and hmac.compare_digest(
        erwartet.encode(), (eingabe or "").strip().encode()
    )


def adresse_der_anfrage(request):
    """Client-Adresse (mit Proxy-Logik, solange Proxys konfiguriert sind) oder ``None``."""
    try:
        return netz.client_ip(request)
    except einstellungen.EinstellungFehlt:
        try:
            return ipaddress.ip_address(request.META.get("REMOTE_ADDR", "").strip())
        except ValueError:
            return None


def aus_heimnetz(request):
    """Nur private, Loopback- und Link-Local-Adressen (nicht global routbar)."""
    adresse = adresse_der_anfrage(request)
    return adresse is not None and not adresse.is_global


def token_ok(request):
    if not erwartetes_token():
        return True
    return bool(request.session.get(SESSION_TOKEN_OK))
