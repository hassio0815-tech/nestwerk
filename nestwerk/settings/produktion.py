from django.core.exceptions import ImproperlyConfigured

from .basis import *  # noqa: F403
from .basis import DATA_DIR, SECRET_KEY

DEBUG = False

# Schlüssel: Umgebungsvariable oder Datei im Volume (vom Entrypoint erzeugt, Rechte 600)
if not SECRET_KEY:
    _datei = DATA_DIR / "secrets" / "django_secret_key"
    if not _datei.is_file():
        raise ImproperlyConfigured(
            "NESTWERK_SECRET_KEY fehlt und /data/secrets/django_secret_key existiert nicht"
        )
    SECRET_KEY = _datei.read_text().strip()

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
