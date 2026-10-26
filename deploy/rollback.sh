#!/usr/bin/env bash
# Rollback auf eine frühere Version.
#   deploy/rollback.sh [<tag>] [--mit-db [<backup-datei>]]
# Ohne <tag>: VORHER_TAG aus .deploy-zustand. --mit-db spielt zusätzlich das Pre-Update-Backup
# zurück (ohne Dateiname: das neueste *-update-Backup). Ohne --mit-db bleibt die DB unverändert.
# Achtung: --mit-db verwirft alle Änderungen seit dem Backup (die alte DB bleibt als
# nestwerk.sqlite3.vor-restore-<zeit> im Volume erhalten).
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$HERE/lib.sh"
cd "$HERE/.."

image=$(image_name)
tag=""
mit_db=0
backup_datei=""
while [ $# -gt 0 ]; do
    case "$1" in
    --mit-db)
        mit_db=1
        if [ $# -gt 1 ] && [ "${2#--}" = "$2" ]; then
            backup_datei="$2"
            shift
        fi
        ;;
    -h | --help)
        sed -n '2,8p' "$0"
        exit 0
        ;;
    --*)
        fehler "Unbekannte Option: $1"
        exit 2
        ;;
    *) tag="$1" ;;
    esac
    shift
done

[ -n "$tag" ] || tag=$(zustand_lesen VORHER_TAG)
[ -n "$tag" ] || {
    fehler "Kein Tag angegeben und kein VORHER_TAG in $ZUSTAND_DATEI"
    exit 1
}
docker image inspect "$image:$tag" >/dev/null 2>&1 || {
    fehler "Image $image:$tag existiert nicht (docker images $image)"
    exit 1
}

log "Rollback auf $image:$tag"
export NESTWERK_TAG="$tag"
docker compose stop web worker scheduler

if [ "$mit_db" -eq 1 ]; then
    [ -n "$backup_datei" ] || backup_datei=$(zustand_lesen UPDATE_BACKUP)
    [ -n "$backup_datei" ] || backup_datei=$(neuestes_update_backup)
    [ -n "$backup_datei" ] || {
        fehler "Kein Update-Backup gefunden"
        exit 1
    }
    log "Spiele Backup zurück: $backup_datei"
    docker compose run --rm --no-deps web python manage.py db_wiederherstellen "/backup/$(basename "$backup_datei")"
fi

env_setzen NESTWERK_TAG "$tag"
docker compose up -d --remove-orphans
if warte_gesund 120; then
    log "Rollback fertig, Stack läuft mit $image:$tag"
else
    fehler "Stack wird nach dem Rollback nicht gesund: docker compose logs --tail=100"
    exit 1
fi
