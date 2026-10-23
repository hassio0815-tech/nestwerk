#!/bin/sh
# Bereitet /data vor (Verzeichnisse, Django-Secret) und startet die Rolle (CMD).
set -eu
DATA="${FAMKO_DATA_DIR:-/data}"
umask 077
mkdir -p "$DATA/db" "$DATA/media/nachweise" "$DATA/media/avatar-cache" "$DATA/secrets"
# Bestehende Volumes (vor AP19 mit 755 angelegt): Geheimnisse und Nachweise nur für famko
chmod 700 "$DATA/secrets" "$DATA/media/nachweise"
if [ -z "${FAMKO_SECRET_KEY:-}" ] && [ ! -f "$DATA/secrets/django_secret_key" ]; then
    python -c "import secrets; print(secrets.token_urlsafe(64))" > "$DATA/secrets/django_secret_key"
fi
exec "$@"
