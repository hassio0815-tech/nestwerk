import tempfile
from pathlib import Path

from .basis import *  # noqa: F403
from .basis import DATABASES

SECRET_KEY = "test"
ALLOWED_HOSTS = ["testserver", "localhost"]

# Datei-DB statt In-Memory, damit WAL und PRAGMAs wie in Produktion testbar sind
_tmp = Path(tempfile.mkdtemp(prefix="famko-test-"))
DATABASES["default"]["TEST"] = {"NAME": str(_tmp / "test.sqlite3")}
STATIC_ROOT = _tmp / "static"
STATIC_ROOT.mkdir()
