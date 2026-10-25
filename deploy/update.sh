#!/usr/bin/env bash
# Update auf den neuesten Stand: holen (git pull oder Bundle-Datei), build, Backup, migrate,
# Neustart, Healthcheck. Bei Fehler nach dem Stoppen: automatischer Rollback auf das vorherige
# Image-Tag (mit DB-Rückspielung, falls schon migriert wurde).
#   deploy/update.sh [--force] [--bundle <datei.bundle>]
# Ohne --bundle wird "git pull --ff-only" benutzt (Remote nötig); mit --bundle wird Branch main
# aus der Bundle-Datei (git bundle create ... main) per fast-forward übernommen.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$HERE/lib.sh"
cd "$HERE/.."

force=0
bundle=""
while [ $# -gt 0 ]; do
    case "$1" in
    --force) force=1 ;;
    --bundle) bundle="${2:?--bundle braucht einen Dateipfad}"; shift ;;
    *) fehler "Unbekannte Option: $1"; exit 2 ;;
    esac
    shift
done
if [ -n "$bundle" ]; then
    [ -f "$bundle" ] || { fehler "Bundle-Datei nicht gefunden: $bundle"; exit 1; }
    bundle=$(realpath "$bundle")
fi

[ -f "$ENV_DATEI" ] || {
    fehler ".env fehlt (cp .env.example .env bzw. deploy/install.sh)"
    exit 1
}
if ! git diff --quiet || ! git diff --cached --quiet; then
    fehler "Arbeitsbaum hat lokale Änderungen – erst committen/verwerfen"
    exit 1
fi

# Bestehende FamKo-Installation: alte Namen (Projekt, Volume, Image) in .env festschreiben
bestehende_installation_uebernehmen
image=$(image_name)

vorher=$(env_wert_kompat TAG)
[ -n "$vorher" ] || vorher=dev
log "Aktuell: $image:$vorher"

if [ -n "$bundle" ]; then
    git bundle verify "$bundle" >/dev/null
    git fetch "$bundle" main
    git merge --ff-only FETCH_HEAD
else
    git pull --ff-only
fi
neu=$(git rev-parse --short=12 HEAD)
if [ "$neu" = "$vorher" ] && [ "$force" -eq 0 ]; then
    log "Bereits auf $neu – nichts zu tun (--force erzwingt Neuaufbau)"
    exit 0
fi

log "Baue $image:$neu"
NESTWERK_TAG="$neu" docker compose build

# Ab hier ändert sich der laufende Betrieb: Fehler lösen Rollback aus.
phase=vorbereitung
rollback() {
    local rc=$?
    trap - ERR
    fehler "Update fehlgeschlagen in Phase '$phase' (Exit $rc) – Rollback"
    if docker image inspect "$image:$vorher" >/dev/null 2>&1; then
        if [ "$phase" = "migriert" ]; then
            "$HERE/rollback.sh" "$vorher" --mit-db || fehler "Rollback fehlgeschlagen – siehe docs/RUNBOOK.md"
        else
            "$HERE/rollback.sh" "$vorher" || fehler "Rollback fehlgeschlagen – siehe docs/RUNBOOK.md"
        fi
    else
        fehler "Image $image:$vorher fehlt, kein automatischer Rollback möglich"
    fi
    exit "$rc"
}
trap rollback ERR

# Pointer auf die letzte gute Version
if docker image inspect "$image:$vorher" >/dev/null 2>&1; then
    docker tag "$image:$vorher" "$image:vorher"
fi
zustand_setzen VORHER_TAG "$vorher"

export NESTWERK_TAG="$neu"
phase=gestoppt
log "Stoppe Dienste (Backup und Migration ohne parallele Schreiber)"
docker compose stop web worker scheduler
if docker compose run --rm --no-deps web sh -c 'test -f /data/db/nestwerk.sqlite3 || test -f /data/db/famko.sqlite3'; then
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
env_setzen NESTWERK_TAG "$neu"
docker compose up -d --remove-orphans
log "Warte auf Healthcheck"
warte_gesund 120

trap - ERR
log "Update fertig: $image:$neu (vorher: $vorher)"
