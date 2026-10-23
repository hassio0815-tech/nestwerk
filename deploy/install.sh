#!/usr/bin/env bash
# Erstinstallation auf einer frischen Debian-13-VM (als root). Idempotent: mehrfach aufrufbar.
#
#   sudo deploy/install.sh --npm-ip <IP des Nginx Proxy Managers> [Optionen]
#
# Optionen:
#   --npm-ip IP        (Pflicht) einzige Quelle, die Port 8000 erreichen darf
#   --domain NAME      z. B. famko.example.org (setzt Hosts/CSRF in .env)
#   --bind-ip IP       LAN-IP der VM für Port 8000 (Standard: automatisch erkannt)
#   --heimnetz CIDR    Heimnetz, z. B. 192.168.0.0/24 (nur Hinweis in .env)
#   --ziel PFAD        Installationsverzeichnis (Standard /opt/famko)
#   --ohne-start       nur vorbereiten, nicht bauen/starten
set -euo pipefail

npm_ip=""
domain=""
bind_ip=""
heimnetz=""
ziel="/opt/famko"
start=1
BACKUP_HOST=/srv/famko/backup
GEHEIMNISSE_HOST=/srv/famko/geheimnisse

fehler() { printf '[install FEHLER] %s\n' "$*" >&2; }
log() { printf '[install] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
    --npm-ip) npm_ip="${2:?--npm-ip braucht einen Wert}"; shift ;;
    --domain) domain="${2:?--domain braucht einen Wert}"; shift ;;
    --bind-ip) bind_ip="${2:?--bind-ip braucht einen Wert}"; shift ;;
    --heimnetz) heimnetz="${2:?--heimnetz braucht einen Wert}"; shift ;;
    --ziel) ziel="${2:?--ziel braucht einen Wert}"; shift ;;
    --ohne-start) start=0 ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) fehler "Unbekannte Option: $1"; exit 2 ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || { fehler "Bitte als root ausführen (sudo)"; exit 1; }
[[ "$npm_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { fehler "--npm-ip fehlt oder ist keine IPv4-Adresse"; exit 2; }

# shellcheck source=/etc/os-release
. /etc/os-release
if [ "${ID:-}" != "debian" ] || [ "${VERSION_ID:-}" != "13" ]; then
    log "WARNUNG: getestet nur mit Debian 13 (hier: ${PRETTY_NAME:-unbekannt})"
fi

quelle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# --- Pakete und Docker-Repo --------------------------------------------------------------------
log "Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git nftables openssl

if [ ! -f /etc/apt/keyrings/docker.asc ]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
fi
cat >/etc/apt/sources.list.d/docker.sources <<EOT
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: ${VERSION_CODENAME}
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOT
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# --- Benutzer und Verzeichnisse ----------------------------------------------------------------
if ! id famko >/dev/null 2>&1; then
    if getent passwd 1000 >/dev/null; then
        useradd --create-home --shell /bin/bash famko
    else
        useradd --uid 1000 --create-home --shell /bin/bash famko
    fi
fi
usermod -aG docker famko

# Code nach $ziel (Git-Checkout); der Container-Benutzer hat UID 1000 (Backup-Ordner!)
if [ "$quelle" != "$ziel" ] && [ ! -d "$ziel/.git" ]; then
    log "Kopiere Checkout nach $ziel"
    mkdir -p "$ziel"
    cp -a "$quelle/." "$ziel/"
fi
chown -R famko: "$ziel"

install -d -m 0755 -o 1000 -g 1000 "$BACKUP_HOST"
install -d -m 0700 -o root -g root "$GEHEIMNISSE_HOST"

# --- .env --------------------------------------------------------------------------------------
cd "$ziel"
# shellcheck source=lib.sh
. "$ziel/deploy/lib.sh"
if [ ! -f .env ]; then
    cp .env.example .env
    log ".env aus .env.example angelegt"
fi
chmod 600 .env
env_setzen FAMKO_BACKUP_DIR "$BACKUP_HOST"
if [ -z "$bind_ip" ]; then
    bind_ip=$(ip -4 route get "$npm_ip" 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n 1)
fi
[ -n "$bind_ip" ] && env_setzen FAMKO_BIND_IP "$bind_ip"
[ -n "$heimnetz" ] && env_setzen FAMKO_HEIMNETZ_CIDR "$heimnetz"
if [ -n "$domain" ]; then
    env_setzen FAMKO_DOMAIN "$domain"
    env_setzen FAMKO_ALLOWED_HOSTS "$domain"
    env_setzen FAMKO_CSRF_TRUSTED_ORIGINS "https://$domain"
fi
if [ -z "$(env_wert FAMKO_SETUP_TOKEN)" ]; then
    env_setzen FAMKO_SETUP_TOKEN "$(openssl rand -hex 16)"
    log "FAMKO_SETUP_TOKEN erzeugt (steht in $ziel/.env)"
fi
if [ -z "$(env_wert FAMKO_TAG)" ] || [ "$(env_wert FAMKO_TAG)" = "dev" ]; then
    env_setzen FAMKO_TAG "$(git rev-parse --short=12 HEAD 2>/dev/null || echo dev)"
fi
chown famko: .env

# --- Firewall: Port 8000 nur vom NPM -----------------------------------------------------------
log "Firewall (nftables): Port 8000 nur von $npm_ip"
install -d -m 0755 /etc/famko
sed "s/@NPM_IP@/$npm_ip/g" "$ziel/deploy/famko-firewall.nft.in" >/etc/famko/firewall.nft
cat >/etc/systemd/system/famko-firewall.service <<'EOT'
[Unit]
Description=FamKo Firewall (Port 8000 nur vom Nginx Proxy Manager)
After=network-pre.target
Before=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/famko/firewall.nft
ExecReload=/usr/sbin/nft -f /etc/famko/firewall.nft

[Install]
WantedBy=multi-user.target
EOT
nft -c -f /etc/famko/firewall.nft
systemctl daemon-reload
systemctl enable famko-firewall.service
systemctl restart famko-firewall.service

# --- Bauen und starten -------------------------------------------------------------------------
if [ "$start" -eq 1 ]; then
    log "Image bauen, migrieren, starten"
    docker compose build
    docker compose run --rm --no-deps web python manage.py migrate --noinput
    docker compose up -d --remove-orphans
    # shellcheck disable=SC2310
    if warte_gesund 120; then log "Stack läuft"; else fehler "Stack nicht gesund: docker compose logs"; exit 1; fi
fi

log "Fertig. Nächste Schritte: docs/RUNBOOK.md (NPM, DNS, Einrichtungs-Assistent)."
log "Setup-Token: $(env_wert FAMKO_SETUP_TOKEN)"
