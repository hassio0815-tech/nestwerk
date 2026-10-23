#!/usr/bin/env bash
# Update auf den neuesten Stand von git: pull, build, Backup, migrate, Neustart, Healthcheck.
# Bei Fehler nach dem Stoppen: automatischer Rollback auf das vorherige Image-Tag
# (mit DB-Rückspielung, falls schon migriert wurde).   Aufruf: deploy/update.sh [--force]
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$HERE/lib.sh"
cd "$HERE/.."

force=0
[ "${1:-}" = "--force" ] && force=1

[ -f "$ENV_DATEI" ] || {
    fehler ".env fehlt (cp .env.example .env bzw. deploy/install.sh)"
    exit 1
}
if ! git diff --quiet || ! git diff --cached --quiet; then
    fehler "Arbeitsbaum hat lokale Änderungen – erst committen/verwerfen"
    exit 1
fi

vorher=$(env_wert FAMKO_TAG)
[ -n "$vorher" ] || vorher=dev
log "Aktuell: famko:$vorher"

git pull --ff-only
neu=$(git rev-parse --short=12 HEAD)
if [ "$neu" = "$vorher" ] && [ "$force" -eq 0 ]; then
    log "Bereits auf $neu – nichts zu tun (--force erzwingt Neuaufbau)"
    exit 0
fi

log "Baue famko:$neu"
FAMKO_TAG="$neu" docker compose build

# Ab hier ändert sich der laufende Betrieb: Fehler lösen Rollback aus.
phase=vorbereitung
rollback() {
    local rc=$?
    trap - ERR
    fehler "Update fehlgeschlagen in Phase '$phase' (Exit $rc) – Rollback"
    if docker image inspect "famko:$vorher" >/dev/null 2>&1; then
        if [ "$phase" = "migriert" ]; then
            "$HERE/rollback.sh" "$vorher" --mit-db || fehler "Rollback fehlgeschlagen – siehe docs/RUNBOOK.md"
        else
            "$HERE/rollback.sh" "$vorher" || fehler "Rollback fehlgeschlagen – siehe docs/RUNBOOK.md"
        fi
    else
        fehler "Image famko:$vorher fehlt, kein automatischer Rollback möglich"
    fi
    exit "$rc"
}
trap rollback ERR

# Pointer auf die letzte gute Version
if docker image inspect "famko:$vorher" >/dev/null 2>&1; then
    docker tag "famko:$vorher" famko:vorher
fi
zustand_setzen VORHER_TAG "$vorher"

export FAMKO_TAG="$neu"
phase=gestoppt
log "Stoppe Dienste (Backup und Migration ohne parallele Schreiber)"
docker compose stop web worker scheduler
if docker compose run --rm --no-deps web test -f /data/db/famko.sqlite3; then
    log "Sichere DB vor der Migration"
    docker compose run --rm --no-deps web python manage.py db_sichern --grund=update
    zustand_setzen UPDATE_BACKUP "$(neuestes_update_backup)"
else
    log "Keine DB vorhanden (Erstinstallation) – kein Backup nötig"
    zustand_setzen UPDATE_BACKUP ""
fi

phase=migriert # ab hier kann die DB verändert sein
log "Migriere"
docker compose run --rm --no-deps web python manage.py migrate --noinput

phase=start
env_setzen FAMKO_TAG "$neu"
docker compose up -d --remove-orphans
log "Warte auf Healthcheck"
warte_gesund 120

trap - ERR
log "Update fertig: famko:$neu (vorher: $vorher)"
