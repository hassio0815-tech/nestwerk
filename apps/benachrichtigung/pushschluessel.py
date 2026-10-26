"""VAPID-Schlüsselpaar für Web-Push (AP08).

Das Paar wird einmalig erzeugt und dauerhaft als ``<SECRETS_DIR>/vapid_private.pem`` (Rechte 0600)
gespeichert, nie in der DB. Existiert die Datei, wird **nie** neu erzeugt: Ein neuer Schlüssel
macht alle Push-Abos ungültig. Der öffentliche Schlüssel wird aus dem privaten abgeleitet und an
den Browser gegeben (``applicationServerKey``).
"""

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from py_vapid import Vapid02

from apps.kern import adressen

SCHLUESSEL_DATEI = "vapid_private.pem"


def _pfad():
    return Path(settings.SECRETS_DIR) / SCHLUESSEL_DATEI


def _erzeugen(pfad):
    pfad.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    vapid = Vapid02()
    vapid.generate_keys()
    temp = pfad.with_name(f".{pfad.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(vapid.private_pem())
    try:
        os.link(temp, pfad)  # atomar; schlägt fehl, wenn parallel schon angelegt
    except FileExistsError:
        pass
    finally:
        temp.unlink(missing_ok=True)


def schluessel():
    """Lädt das VAPID-Paar (``Vapid02``); erzeugt es nur, wenn die Datei fehlt."""
    pfad = _pfad()
    if not pfad.exists():
        _erzeugen(pfad)
    return Vapid02.from_file(str(pfad))


def oeffentlicher_schluessel():
    """Öffentlicher Schlüssel als URL-sicheres Base64 ohne Padding (für ``subscribe``)."""
    roh = schluessel().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode()


def kontakt():
    """``sub``-Claim: eigene https-Origin, sonst ``VAPID_KONTAKT`` (mailto:)."""
    eigener = getattr(settings, "VAPID_KONTAKT", "") or ""
    if eigener:
        return eigener
    basis = adressen.basis_url()
    return basis if basis.startswith("https://") else "mailto:nestwerk@localhost.invalid"
