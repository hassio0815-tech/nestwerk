#!/usr/bin/env bash
# Gemeinsame Funktionen für update.sh / rollback.sh (wird per source geladen).
# shellcheck shell=bash

log() { printf '[famko %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fehler() { printf '[famko FEHLER] %s\n' "$*" >&2; }

# Das Repo gehört dem Benutzer famko; als root würde git sonst mit "dubious ownership" abbrechen.
GIT_CONFIG_COUNT=1
GIT_CONFIG_KEY_0=safe.directory
GIT_CONFIG_VALUE_0=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0

ENV_DATEI=".env"
ZUSTAND_DATEI=".deploy-zustand"

# env_wert KEY [DATEI] -> Wert oder leer
env_wert() {
    local datei="${2:-$ENV_DATEI}"
    [ -f "$datei" ] || return 0
    sed -n "s/^$1=//p" "$datei" | tail -n 1
}

# env_setzen KEY WERT [DATEI]  (idempotent, Werte ohne Zeilenumbruch)
env_setzen() {
    local datei="${3:-$ENV_DATEI}" wert_escaped
    wert_escaped=$(printf '%s' "$2" | sed 's/[&|\\]/\\&/g')
    if grep -q "^$1=" "$datei" 2>/dev/null; then
        sed -i "s|^$1=.*|$1=$wert_escaped|" "$datei"
    else
        printf '%s=%s\n' "$1" "$2" >>"$datei"
    fi
}

# Zustand (VORHER_TAG, UPDATE_BACKUP) für Rollback
zustand_setzen() { env_setzen "$1" "$2" "$ZUSTAND_DATEI"; }
zustand_lesen() { env_wert "$1" "$ZUSTAND_DATEI"; }

backup_ordner() {
    local o
    o=$(env_wert FAMKO_BACKUP_DIR)
    printf '%s' "${o:-./backup}"
}

# neuestes Update-Backup im Host-Ordner (nur Name)
neuestes_update_backup() {
    local ordner
    ordner=$(backup_ordner)
    find "$ordner" -maxdepth 1 -name 'famko-*-update.sqlite3.gz' -printf '%f\n' 2>/dev/null | sort | tail -n 1
}

# Wartet bis web "healthy" ist und worker/scheduler laufen. Rückgabe 0 = ok.
warte_gesund() {
    local grenze="${1:-120}" start cid status
    start=$(date +%s)
    while [ $(($(date +%s) - start)) -lt "$grenze" ]; do
        cid=$(docker compose ps -q web 2>/dev/null || true)
        if [ -n "$cid" ]; then
            status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}keiner{{end}}' "$cid" 2>/dev/null || echo unbekannt)
            if [ "$status" = "healthy" ]; then
                if [ -n "$(docker compose ps -q --status running worker)" ] &&
                    [ -n "$(docker compose ps -q --status running scheduler)" ]; then
                    return 0
                fi
            fi
        fi
        sleep 3
    done
    return 1
}
