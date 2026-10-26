#!/usr/bin/env bash
# Erstinstallation auf einer frischen Debian-13-VM (als root). Idempotent: mehrfach aufrufbar.
#
#   sudo deploy/install.sh --npm-ip <IP des Nginx Proxy Managers> [Optionen]
#
# Optionen:
#   --npm-ip IP        (Pflicht) einzige Quelle, die Port 8000 erreichen darf
#   --domain NAME      z. B. nestwerk.example.org (setzt Hosts/CSRF in .env)
#   --bind-ip IP       LAN-IP der VM für Port 8000 (Standard: automatisch erkannt)
#   --heimnetz CIDR    Heimnetz, z. B. 192.168.0.0/24 (nur Hinweis in .env)
#   --ziel PFAD        Installationsverzeichnis (Standard /opt/nestwerk; /opt/famko, wenn dort schon eine Installation liegt)
#   --egress-erlaubt X Komma-Liste privater Ziele (IP/CIDR), die Container erreichen dürfen
#                      (z. B. ein SMTP-Relay im LAN); DNS-Resolver der VM sind automatisch erlaubt
#   --ohne-start       nur vorbereiten, nicht bauen/starten
set -euo pipefail

npm_ip=""
domain=""
bind_ip=""
heimnetz=""
egress=""
ziel=""
start=1
BACKUP_HOST=/srv/nestwerk/backup
GEHEIMNISSE_HOST=/srv/nestwerk/geheimnisse

fehler() { printf '[install FEHLER] %s\n' "$*" >&2; }
log() { printf '[install] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
    --npm-ip) npm_ip="${2:?--npm-ip braucht einen Wert}"; shift ;;
    --domain) domain="${2:?--domain braucht einen Wert}"; shift ;;
    --bind-ip) bind_ip="${2:?--bind-ip braucht einen Wert}"; shift ;;
    --heimnetz) heimnetz="${2:?--heimnetz braucht einen Wert}"; shift ;;
    --egress-erlaubt) egress="${2:?--egress-erlaubt braucht einen Wert}"; shift ;;
    --ziel) ziel="${2:?--ziel braucht einen Wert}"; shift ;;
    --ohne-start) start=0 ;;
    -h | --help) sed -n '2,17p' "$0"; exit 0 ;;
    *) fehler "Unbekannte Option: $1"; exit 2 ;;
    esac
    shift
done

# Bestehende Installation (früher "FamKo") erkennen und deren Namen behalten (Pfad, Benutzer,
# Firewall); neue Installationen bekommen die nestwerk-Namen.
if [ -z "$ziel" ]; then
    if [ -d /opt/famko/.git ] && [ ! -d /opt/nestwerk/.git ]; then ziel=/opt/famko; else ziel=/opt/nestwerk; fi
fi
benutzer=nestwerk
if id famko >/dev/null 2>&1 && ! id nestwerk >/dev/null 2>&1; then benutzer=famko; fi
fw_name=nestwerk
if [ -f /etc/famko/firewall.nft ] && [ ! -f /etc/nestwerk/firewall.nft ]; then fw_name=famko; fi
[ -d /srv/famko ] && [ ! -d /srv/nestwerk ] && BACKUP_HOST=/srv/famko/backup && GEHEIMNISSE_HOST=/srv/famko/geheimnisse

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
if ! id "$benutzer" >/dev/null 2>&1; then
    if getent passwd 1000 >/dev/null; then
        useradd --create-home --shell /bin/bash "$benutzer"
    else
        useradd --uid 1000 --create-home --shell /bin/bash "$benutzer"
    fi
fi
usermod -aG docker "$benutzer"

# Code nach $ziel (Git-Checkout); der Container-Benutzer hat UID 1000 (Backup-Ordner!)
if [ "$quelle" != "$ziel" ] && [ ! -d "$ziel/.git" ]; then
    log "Kopiere Checkout nach $ziel"
    mkdir -p "$ziel"
    cp -a "$quelle/." "$ziel/"
fi
chown -R "$benutzer": "$ziel"

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
bestehende_installation_uebernehmen
vorhanden=$(env_wert_kompat BACKUP_DIR)
[ -z "$vorhanden" ] || BACKUP_HOST="$vorhanden"
env_setzen NESTWERK_BACKUP_DIR "$BACKUP_HOST"
if [ -z "$bind_ip" ]; then
    bind_ip=$(ip -4 route get "$npm_ip" 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n 1)
fi
[ -n "$bind_ip" ] && env_setzen NESTWERK_BIND_IP "$bind_ip"
[ -n "$heimnetz" ] && env_setzen NESTWERK_HEIMNETZ_CIDR "$heimnetz"
if [ -n "$domain" ]; then
    env_setzen NESTWERK_DOMAIN "$domain"
    env_setzen NESTWERK_ALLOWED_HOSTS "$domain"
    env_setzen NESTWERK_CSRF_TRUSTED_ORIGINS "https://$domain"
fi
if [ -z "$(env_wert_kompat SETUP_TOKEN)" ]; then
    env_setzen NESTWERK_SETUP_TOKEN "$(openssl rand -hex 16)"
    log "NESTWERK_SETUP_TOKEN erzeugt (steht in $ziel/.env)"
fi
if [ -z "$(env_wert_kompat TAG)" ] || [ "$(env_wert_kompat TAG)" = "dev" ]; then
    env_setzen NESTWERK_TAG "$(git rev-parse --short=12 HEAD 2>/dev/null || echo dev)"
fi
chown "$benutzer": .env

# --- Firewall: Port 8000 nur vom NPM -----------------------------------------------------------
log "Firewall (nftables): Port 8000 nur von $npm_ip"
install -d -m 0755 "/etc/$fw_name"
# DNS-Resolver der VM (IPv4) bleiben für Container erreichbar, sonst blockt die Egress-Regel sie
dns=$(sed -n 's/^nameserver[[:space:]]\+\([0-9.]\+\).*/\1/p' /etc/resolv.conf | paste -sd, - | sed 's/,/, /g')
if [ -z "$dns" ] || [ "$dns" = "127.0.0.53" ]; then
    log "WARNUNG: keine direkten IPv4-DNS-Resolver in /etc/resolv.conf gefunden – Container-DNS prüfen"
    dns="127.0.0.53"
fi
# Die Liste wird in .env gemerkt, damit ein erneuter Lauf sie nicht verliert
[ -n "$egress" ] && env_setzen NESTWERK_EGRESS_ERLAUBT "$egress"
egress=$(env_wert_kompat EGRESS_ERLAUBT)
egress_elemente=""
[ -n "$egress" ] && egress_elemente="        elements = { ${egress//,/, } }"
sed -e "s|@NPM_IP@|$npm_ip|g" -e "s|@DNS_ERLAUBT@|$dns|" \
    -e "s|^@EGRESS_ELEMENTE@\$|$egress_elemente|" \
    "$ziel/deploy/nestwerk-firewall.nft.in" >"/etc/$fw_name/firewall.nft"
cat >"/etc/systemd/system/$fw_name-firewall.service" <<EOT
[Unit]
Description=Nestwerk Firewall (Port 8000 nur vom Nginx Proxy Manager)
After=network-pre.target
Before=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/$fw_name/firewall.nft
ExecReload=/usr/sbin/nft -f /etc/$fw_name/firewall.nft

[Install]
WantedBy=multi-user.target
EOT
nft -c -f "/etc/$fw_name/firewall.nft"
systemctl daemon-reload
systemctl enable "$fw_name-firewall.service"
systemctl restart "$fw_name-firewall.service"

# --- Bauen und starten -------------------------------------------------------------------------
if [ "$start" -eq 1 ]; then
    log "Image bauen, migrieren, starten"
    docker compose build
    docker compose run --rm --no-deps web python manage.py migrate --noinput
    docker compose up -d --remove-orphans
    # shellcheck disable=SC2310
    if warte_gesund 120; then log "Stack läuft"; else fehler "Stack nicht gesund: docker compose logs"; exit 1; fi
fi

log "Fertig. Nächste Schritte: docs/INSTALLATION.md (Proxy, DNS, Einrichtungs-Assistent); Betrieb: docs/RUNBOOK.md."
log "Setup-Token: $(env_wert_kompat SETUP_TOKEN)"
