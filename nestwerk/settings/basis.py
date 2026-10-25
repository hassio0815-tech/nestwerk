"""Gemeinsame Einstellungen. Konfiguration per Umgebungsvariablen.

Präfix NESTWERK_; der alte Präfix FAMKO_ gilt als Fallback (apps.kern.umgebung).
"""

from pathlib import Path

from apps.kern.umgebung import umgebung

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name, default=None):
    return umgebung(name, default)


def env_liste(name, default=""):
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


# Datenverzeichnis (Volume): db/, media/, secrets/
DATA_DIR = Path(env("DATA_DIR", BASE_DIR / "data"))

# Geheimnisse im Volume; der Fernet-Schlüssel (SMTP-Passwort) kommt aus NESTWERK_FERNET_KEY oder
# wird einmalig als secrets/fernet.key angelegt
SECRETS_DIR = DATA_DIR / "secrets"
FERNET_KEY = env("FERNET_KEY")
# Öffentliche Adresse für Links in E-Mails (z. B. https://nestwerk.example.org)
BASIS_URL = env("BASIS_URL", "")
VAPID_KONTAKT = env("VAPID_KONTAKT", "")  # optional: mailto:/https-Kontakt für Push (sub-Claim)

# Backups (AP18): Zielordner im Container (compose mountet ihn als /backup) und Aufbewahrung.
# Nicht NESTWERK_BACKUP_DIR: das ist der Host-Pfad in .env.
BACKUP_DIR = Path(env("BACKUP_ZIEL", DATA_DIR / "backup"))
BACKUP_TAEGLICH = int(env("BACKUP_TAEGLICH", "14"))
BACKUP_WOECHENTLICH = int(env("BACKUP_WOECHENTLICH", "8"))
BACKUP_MONATLICH = int(env("BACKUP_MONATLICH", "12"))
BACKUP_UPDATE_BEHALTEN = int(env("BACKUP_UPDATE_BEHALTEN", "5"))
BACKUP_MAX_ALTER_STUNDEN = int(env("BACKUP_MAX_ALTER_STUNDEN", "36"))

SECRET_KEY = env("SECRET_KEY")  # Pflicht in Produktion; Entwicklung/Test setzen Ersatzwert
DEBUG = False
# Der Container-Healthcheck (compose.yaml) ruft http://127.0.0.1:8000/gesundheit/ auf. Ohne
# diese beiden Namen lehnt Django ihn mit 400 ab (DisallowedHost), der Container wird nie
# "healthy" und update.sh/install.sh brechen ab (Review AP19, B-01). Port 8000 erreicht von
# außen nur der Proxy (nftables), daher ist das unbedenklich.
LOKALE_HOSTS = ["localhost", "127.0.0.1"]


def allowed_hosts(text):
    hosts = [h.strip() for h in text.split(",") if h.strip()]
    return hosts + [h for h in LOKALE_HOSTS if h not in hosts]


ALLOWED_HOSTS = allowed_hosts(env("ALLOWED_HOSTS", ""))
CSRF_TRUSTED_ORIGINS = env_liste("CSRF_TRUSTED_ORIGINS")

# Phase-1-Apps (Schichten siehe ARCHITECTURE 2.1). Auth/Sessions gehören zu konten.Benutzer (AP03).
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "apps.kern",
    "apps.konten",
    "apps.punkte",
    "apps.ereignisse",
    "apps.benachrichtigung",
    "apps.spielregeln",
    "apps.aufgaben",
    "apps.belohnung",
    "apps.avatar",
    "apps.sondertag",
    "apps.familienziel",
    "apps.einrichtung",
    "apps.oberflaeche",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "nestwerk.sicherheit.SicherheitsHeader",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.aufgaben.middleware.UploadGrenze",  # vor CSRF: die liest den Body schon
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.einrichtung.middleware.EinrichtungErzwingen",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.konten.middleware.GeraetMiddleware",
    "apps.konten.middleware.SitzungsRichtlinie",
    "apps.konten.middleware.AuditKontextMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "nestwerk.urls"
WSGI_APPLICATION = "nestwerk.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "apps.konten.context.konten",
            ]
        },
    }
]

# Bestehende Installationen (frühere Projektbezeichnung FamKo) behalten ihre Datenbankdatei.
_DB_ALT = DATA_DIR / "db" / "famko.sqlite3"
_DB_NEU = DATA_DIR / "db" / "nestwerk.sqlite3"
DB_DATEI = _DB_ALT if _DB_ALT.exists() and not _DB_NEU.exists() else _DB_NEU

# SQLite mit WAL für drei Prozesse (ARCHITECTURE 3.2).
# Die PRAGMAs laufen bei jedem Verbindungsaufbau; journal_mode=WAL ist dauerhaft in der Datei.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_DATEI,
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 5,
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA busy_timeout=5000;"
                "PRAGMA foreign_keys=ON;"
                "PRAGMA secure_delete=ON;"
            ),
        },
    }
}
# Konten (ARCHITECTURE 4): eigenes Benutzermodell, zwei Anmelde-Backends, Argon2
AUTH_USER_MODEL = "konten.Benutzer"
AUTHENTICATION_BACKENDS = [
    "apps.konten.backends.ElternBackend",
    "apps.konten.backends.KindBackend",
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
LOGIN_URL = "konten:start"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 12 * 3600  # Rückfall; die Dauer setzt konten beim Login aus den Einstellungen

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Berlin"  # nur Anzeige; intern UTC
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").is_dir() else []
MEDIA_ROOT = DATA_DIR / "media"

# Nachweis-Fotos (AP13): privat, nie öffentlich ausgeliefert, nicht im Backup (ARCHITECTURE 9)
# Größe, Anzahl, Kantenlänge der Fotos: Einstellungen aufgaben.nachweis_* (Eltern-Editor)
NACHWEIS_DIR = Path(env("NACHWEIS_DIR", DATA_DIR / "media" / "nachweise"))

# Hinter Nginx Proxy Manager (TLS endet dort)
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
