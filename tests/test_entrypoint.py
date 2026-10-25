"""deploy/entrypoint.sh legt das Volume mit engen Rechten an (Review AP19, B-13)."""

import os
import stat
import subprocess
from pathlib import Path

from django.conf import settings

SKRIPT = Path(settings.BASE_DIR) / "deploy" / "entrypoint.sh"


def _rechte(pfad):
    return stat.S_IMODE(pfad.stat().st_mode)


def test_secrets_und_nachweise_nur_fuer_den_dienst(tmp_path):
    daten = tmp_path / "data"
    (daten / "secrets").mkdir(parents=True, mode=0o755)  # Altbestand mit zu weiten Rechten
    os.chmod(daten / "secrets", 0o755)
    umgebung = {**os.environ, "NESTWERK_DATA_DIR": str(daten), "NESTWERK_SECRET_KEY": ""}
    subprocess.run(["sh", str(SKRIPT), "true"], check=True, env=umgebung)
    assert _rechte(daten / "secrets") == 0o700
    assert _rechte(daten / "media" / "nachweise") == 0o700
    assert _rechte(daten / "secrets" / "django_secret_key") == 0o600
