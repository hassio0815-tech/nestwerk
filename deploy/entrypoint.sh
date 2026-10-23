#!/bin/sh
# Bereitet /data vor (Verzeichnisse, Django-Secret) und startet die Rolle (CMD).
set -eu
DATA="${FAMKO_DATA_DIR:-/data}"
mkdir -p "$DATA/db" "$DATA/media/nachweise" "$DATA/media/avatar-cache" "$DATA/secrets"
umask 077
if [ -z "${FAMKO_SECRET_KEY:-}" ] && [ ! -f "$DATA/secrets/django_secret_key" ]; then
    python -c "import secrets; print(secrets.token_urlsafe(64))" > "$DATA/secrets/django_secret_key"
fi
exec "$@"
