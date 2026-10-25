#!/usr/bin/env bash
# Sichert /data/secrets (Django-Secret, Fernet-, VAPID-Schlüssel) als verschlüsseltes Archiv.
#   deploy/secrets-sichern.sh <zielordner>      (Passphrase wird abgefragt; Ziel nicht im Repo)
# Das Archiv gehört NICHT in den normalen Backup-Ordner im Klartext. Aufbewahrung getrennt von
# der VM (Passwortmanager/USB-Stick). Wiederherstellen: siehe docs/RUNBOOK.md.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$HERE/.."

ziel="${1:?Aufruf: $0 <zielordner>}"
mkdir -p "$ziel"
chmod 700 "$ziel"
datei="$ziel/nestwerk-secrets-$(date +%Y%m%d-%H%M%S).tar.gz.enc"

umask 077
docker compose run --rm --no-deps -T web tar -C /data -czf - secrets |
    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -out "$datei"
echo "Geschrieben: $datei"
echo "Entschlüsseln: openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in <datei> | tar -xzf - -C <ziel>"
