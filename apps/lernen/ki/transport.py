"""HTTP-Transport (nur Standardbibliothek). Tests ersetzen ``post_json`` oder nutzen einen
lokalen Fake-Server; echte Netzaufrufe gibt es dort nie.

Sicherheit: nur http/https, keine Zugangsdaten in der URL, keine Weiterleitungen (sonst würde der
Authorization-Header an einen anderen Host gehen), Antwortgröße begrenzt, Schlüssel nur im Header.
"""

import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .basis import (
    KiAnfrageFehler,
    KiKonfigurationsFehler,
    KiVerbindungsFehler,
    KiZeitueberschreitung,
)

MAX_ANTWORT_BYTES = 20 * 1024 * 1024


def url_pruefen(url):
    """Normalisierte Basis-URL (ohne Schrägstrich am Ende) oder ``KiKonfigurationsFehler``."""
    teile = urlsplit((url or "").strip())
    if teile.scheme not in ("http", "https") or not teile.hostname:
        raise KiKonfigurationsFehler()
    if teile.username or teile.password or teile.query or teile.fragment:
        raise KiKonfigurationsFehler()
    try:
        teile.port  # noqa: B018 - löst bei ungültigem Port ValueError aus
    except ValueError as exc:
        raise KiKonfigurationsFehler() from exc
    return teile.geturl().rstrip("/")


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_KeineWeiterleitung)


def _lesen(antwort):
    roh = antwort.read(MAX_ANTWORT_BYTES + 1)
    if len(roh) > MAX_ANTWORT_BYTES:
        raise KiAnfrageFehler()
    try:
        return json.loads(roh.decode("utf-8")) if roh else None
    except ValueError:
        return None


def post_json(url, *, headers, payload, timeout):
    """POST mit JSON-Körper. Liefert ``(status, geparstes_json_oder_None)``; Netzfehler werden
    zu ``KiVerbindungsFehler`` / ``KiZeitueberschreitung`` (ohne URL oder Header im Text)."""
    anfrage = urllib.request.Request(  # noqa: S310 - Schema in url_pruefen begrenzt
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with _opener.open(anfrage, timeout=timeout) as antwort:
            return antwort.status, _lesen(antwort)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _lesen(exc)
        except (OSError, KiAnfrageFehler):
            return exc.code, None
    except TimeoutError as exc:
        raise KiZeitueberschreitung() from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError | socket.timeout):
            raise KiZeitueberschreitung() from exc
        raise KiVerbindungsFehler() from exc
    except (OSError, ValueError) as exc:
        raise KiVerbindungsFehler() from exc
