import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from .basis import *  # noqa: F403
from .basis import DATABASES

SECRET_KEY = "test"
ALLOWED_HOSTS = ["testserver", "localhost"]

# Datei-DB statt In-Memory, damit WAL und PRAGMAs wie in Produktion testbar sind
_tmp = Path(tempfile.mkdtemp(prefix="nestwerk-test-"))
DATABASES["default"]["TEST"] = {"NAME": str(_tmp / "test.sqlite3")}
SECRETS_DIR = _tmp / "secrets"
FERNET_KEY = Fernet.generate_key().decode()
BASIS_URL = "https://nestwerk.test"
STATIC_ROOT = _tmp / "static"
STATIC_ROOT.mkdir()
NACHWEIS_DIR = _tmp / "nachweise"

# Gleicher Algorithmus wie in Produktion (Argon2), nur mit minimalem Aufwand
PASSWORD_HASHERS = ["apps.konten.tests.hasher.SchnellerArgon2"]

# Einrichtungs-Assistent (AP16) wird nur in dessen eigenen Tests erzwungen
EINRICHTUNG_ERZWINGEN = False
