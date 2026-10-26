"""Fernet-Verschlüsselung für Geheimnisse in der DB (SMTP-Passwort).

Schlüssel: Einstellung ``FERNET_KEY`` (Umgebungsvariable ``NESTWERK_FERNET_KEY``), sonst die Datei
``<SECRETS_DIR>/fernet.key`` im Volume. Fehlt beides, wird die Datei einmalig mit Rechten 0600
erzeugt. Geht der Schlüssel verloren, müssen die Geheimnisse neu eingegeben werden.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

SCHLUESSEL_DATEI = "fernet.key"


class SchluesselFehler(Exception):
    """Token lässt sich mit dem vorhandenen Schlüssel nicht entschlüsseln."""


def _schluessel():
    aus_umgebung = getattr(settings, "FERNET_KEY", None)
    if aus_umgebung:
        return aus_umgebung.encode() if isinstance(aus_umgebung, str) else aus_umgebung
    ordner = Path(settings.SECRETS_DIR)
    datei = ordner / SCHLUESSEL_DATEI
    if not datei.exists():
        ordner.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(datei, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # parallel angelegt
            pass
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(Fernet.generate_key())
    return datei.read_bytes().strip()


def verschluesseln(klartext):
    return Fernet(_schluessel()).encrypt(klartext.encode()).decode()


def entschluesseln(token):
    try:
        return Fernet(_schluessel()).decrypt(token.encode()).decode()
    except InvalidToken:
        raise SchluesselFehler("Gespeichertes Geheimnis passt nicht zum Schlüssel") from None
