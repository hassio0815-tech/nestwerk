# Installing Nestwerk (step by step)

🇬🇧 **English** · 🇩🇪 [Deutsch](../INSTALLATION.md)

This guide sets up Nestwerk on your own server on the home network. It is written for technically inclined parents with basic knowledge of Proxmox, Linux and Docker.

Replace the placeholders in `<angle brackets>` with your own values. Examples:

- `<VM-IP>`: fixed IP of the Nestwerk VM, e.g. `192.168.1.50`
- `<NPM-IP>`: IP of your reverse proxy (e.g. Nginx Proxy Manager), e.g. `192.168.1.10`
- `<YOUR-DOMAIN>`: your own domain, e.g. `example.org`
- `<HOME-NET-CIDR>`: your home network, e.g. `192.168.1.0/24`

---

## 0. Overview

```
Phone/tablet ──HTTPS──> Reverse proxy (<NPM-IP>) ──HTTP:8000──> Nestwerk VM (<VM-IP>)
                                                              (Docker: web, worker, scheduler)
Local DNS (AdGuard/Pi-hole): nestwerk.<YOUR-DOMAIN> -> <NPM-IP>
```

- **Only one proxy:** port 8000 on the VM is open only to the reverse proxy.
- **No cloud:** data, photos and the database stay on your server.
- **No open ports to the internet:** remote access only through your own VPN (e.g. WireGuard or Tailscale).

---

## 1. Requirements

- [ ] Proxmox (or another hypervisor) with a **Debian 13 VM**, minimal install, with SSH.
  - Tested with: 2 vCPU, 4 GB RAM, 46 GB storage.
- [ ] **Fixed IP** for the VM (DHCP reservation in your router).
- [ ] A **reverse proxy** with HTTPS, e.g. Nginx Proxy Manager (NPM).
- [ ] A **domain** whose DNS zone is hosted by a provider with an API (for Let's Encrypt via DNS challenge).
- [ ] Optional: a local DNS server (AdGuard Home or Pi-hole).
- [ ] Optional: an **email mailbox** on your own domain for notifications (SMTP).
- [ ] Optional: an iPhone with iOS 16.4 or newer for push notifications, an Android tablet as a hallway display.

**Important:** during installation the VM needs internet access (Docker repository, Let's Encrypt) and outbound access to `*.push.apple.com` (push).

---

## 2. Getting the code onto the VM

Nestwerk has no dependency on any public cloud. You fetch the code from your Git repository.

Option A: Git repository (if you have a remote):

```bash
apt-get update && apt-get install -y git
git clone <REPO-URL> /opt/nestwerk
cd /opt/nestwerk
```

Option B: Git bundle (no remote, e.g. from your own laptop):

```bash
# On the development machine, inside the repo:
git bundle create /tmp/nestwerk.bundle main
scp /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle

# On the VM as root:
apt-get install -y git
git clone -b main /root/nestwerk.bundle /opt/nestwerk
cd /opt/nestwerk
```

The installer must run as **root** (on minimal Debian installs `sudo` is often not installed).

---

## 3. Running the installer

The installer `deploy/install.sh` is idempotent. You can run it more than once.

First run it without starting, so you can check the `.env`:

```bash
deploy/install.sh --npm-ip <NPM-IP> --domain nestwerk.<YOUR-DOMAIN> --heimnetz <HOME-NET-CIDR> --ohne-start
```

Then with start:

```bash
deploy/install.sh --npm-ip <NPM-IP> --domain nestwerk.<YOUR-DOMAIN> --heimnetz <HOME-NET-CIDR>
```

| Option | Meaning |
|---|---|
| `--npm-ip IP` | **Required.** The only source allowed to reach port 8000 (your reverse proxy). |
| `--domain NAME` | e.g. `nestwerk.<YOUR-DOMAIN>`. Sets hosts and CSRF in the `.env`. |
| `--bind-ip IP` | LAN IP of the VM for port 8000. Default: detected automatically. |
| `--heimnetz CIDR` | Home network; only recorded as a note in the `.env`. |
| `--egress-erlaubt X` | Private targets the containers may reach, e.g. an SMTP relay on the LAN. |
| `--ziel PFAD` | Installation folder. Default: `/opt/nestwerk`. |
| `--ohne-start` | Only prepare; do not build or start. |

The installer does the following:

1. Installs Docker Engine and the Compose plugin from the official Docker repository.
2. Creates the user `nestwerk`, plus `/srv/nestwerk/backup` (UID 1000) and `/srv/nestwerk/geheimnisse` (mode 0700).
3. Creates the `.env`, including the **setup token**.
4. Sets up the firewall (nftables): port 8000 only from the NPM IP, and containers cannot reach private networks.
5. Builds, migrates and starts Nestwerk.

**At the end, the installer prints the setup token.** It is also stored in `/opt/nestwerk/.env`:

```bash
grep SETUP_TOKEN /opt/nestwerk/.env
```

### 3.1 Checking the `.env`

The file is at `/opt/nestwerk/.env`. Important values:

- `NESTWERK_ALLOWED_HOSTS`: Django only accepts exact names or suffixes with a leading dot (e.g. `.example.org`), not wildcards like `nestwerk.*`. Until the subdomain is set up, enter the VM IP.
- `NESTWERK_CSRF_TRUSTED_ORIGINS`: `https://nestwerk.<YOUR-DOMAIN>`.
- `NESTWERK_BASIS_URL`: `https://nestwerk.<YOUR-DOMAIN>`. It appears in the links in notifications.

After every change: `cd /opt/nestwerk && docker compose up -d`.

All variables are commented in `.env.example`.

### 3.2 Checking

On the VM:

```bash
curl -s http://<VM-IP>:8000/gesundheit/
```

The response must be HTTP 200. From your laptop the address must **not** be reachable, because port 8000 is open only to the reverse proxy.

**Note:** the VM gets its IP via DHCP. Set a fixed reservation in your router. If the IP changes, `NESTWERK_BIND_IP` no longer matches.

---

## 4. Setting up the reverse proxy

The example uses the **Nginx Proxy Manager**. Other proxies (Traefik, Caddy, nginx) work the same way.

### 4.1 Creating a proxy host

1. **Hosts → Proxy Hosts → Add Proxy Host**
2. **Domain Names:** `nestwerk.<YOUR-DOMAIN>`
3. **Scheme:** `http`
4. **Forward Hostname / IP:** `<VM-IP>`
5. **Forward Port:** `8000`
6. Tick the boxes:
   - **Block Common Exploits:** on
   - **Websockets Support:** **off**
   - **Cache Assets:** **off** (important for `/sw.js` and `/manifest.json`)

### 4.2 Increasing the upload size

Proof photos need more space than the default limit.

1. Open the **Advanced** tab of the proxy host.
2. Add:

```nginx
client_max_body_size 50m;
```

The app also limits uploads itself, via the settings `aufgaben.nachweis_max_upload_mb` and `aufgaben.nachweis_max_anzahl`.

### 4.3 Access rules

- **No access list** on the host. `/sw.js` and `/manifest.json` must be served without login and without caching.
- **No second proxy** in front of the reverse proxy. Nestwerk only reads the rightmost entry of `X-Forwarded-For`. With an extra proxy hop, Nestwerk gets the wrong client address.
- In the setup wizard, enter only the `<NPM-IP>` under **"Trusted proxies"**.

### 4.4 HTTPS with Let's Encrypt (DNS challenge)

The DNS challenge also works if the name is only resolved on the home network. Your provider must offer an API for TXT records (e.g. Cloudflare).

1. Create an **API token** with rights to the DNS zone at your DNS provider.
2. In NPM: **SSL Certificates → Add SSL Certificate → Let's Encrypt**.
3. **Domain Names:** `nestwerk.<YOUR-DOMAIN>` (or `*.<YOUR-DOMAIN>`).
4. **Use a DNS Challenge:** on. Choose the provider and enter the API token.
5. In the proxy host, on the **SSL** tab: select the certificate, turn on **Force SSL** and **HTTP/2**, turn on **HSTS**.

### 4.5 Checking

```bash
curl -s https://nestwerk.<YOUR-DOMAIN>/gesundheit/
```

The response must be HTTP 200.

---

## 5. Local DNS entry (home network)

So that devices on the home network resolve `nestwerk.<YOUR-DOMAIN>` directly to the reverse proxy, set up a local DNS entry. It points to the **NPM IP**, not to the VM.

**AdGuard Home:**

1. **Filters → DNS rewrites**
2. **Domain:** `nestwerk.<YOUR-DOMAIN>`
3. **Answer:** `<NPM-IP>`

**Pi-hole (v6):**

1. **Settings → Local DNS → DNS Records**
2. **Domain:** `nestwerk.<YOUR-DOMAIN>`
3. **IP address:** `<NPM-IP>`

Check on a device in the home network:

```bash
nslookup nestwerk.<YOUR-DOMAIN>
```

The answer must be `<NPM-IP>`.

---

## 6. Setup wizard

1. Open `https://nestwerk.<YOUR-DOMAIN>/einrichtung/` in your browser.
2. Enter the **setup token** from the `.env`.
3. Go through the eight steps:
   1. **Welcome:** the app's display name
   2. **Parents:** names, email addresses, shared family password
   3. **Kids:** names and a four-digit PIN for each child
   4. **Email sending:** SMTP access with a test email
   5. **Network:** home network and "Trusted proxies" (only the `<NPM-IP>`)
   6. **Time:** go-live date (start of the app year) and time zone (default Europe/Berlin)
   7. **Check default values:** ranks, rewards, task library, family goal. You can change everything later.
   8. **Summary** and completion
4. Then **remove** the setup token from the `.env`:

```bash
cd /opt/nestwerk
sed -i '/^NESTWERK_SETUP_TOKEN=/d' .env
docker compose up -d
```

As long as the token is set, the wizard is open to every device on the home network. That is why you should remove it after setup.

---

## 7. Setting up devices

### 7.1 iPhone as a web app (push)

Requirements: iOS or iPadOS 16.4 or newer, HTTPS, the web app on the home screen.

1. Open `https://nestwerk.<YOUR-DOMAIN>` in **Safari**.
2. **Share → Add to Home Screen.**
3. Open the app **from its new icon**, not from Safari. Only then does the permission prompt appear.
4. Log in, then tap **Settings → Turn on notifications** and allow the system prompt.
5. Tap **Send test push**. The message should arrive within a few seconds.

If no message arrives:

- Does the VM have outbound access to `*.push.apple.com:443`?
- Was the app opened from the home screen?
- Check the log: `docker compose logs worker`

Note: Apple sometimes changes the web push requirements with new iOS versions. If you run into problems, check Apple's current documentation.

### 7.2 Android tablet as a hallway display (kiosk)

Recommended: **Fully Kiosk Browser** (Android).

1. **Start URL:** `https://nestwerk.<YOUR-DOMAIN>/`
2. Keep the screen on at all times.
3. Turn on **kiosk mode**.
4. Log in to Nestwerk as a parent: go to **Parents → Devices** and mark the tablet as **Kiosk (hallway tablet)**.

On the kiosk tablet, the kids' session expires after about 5 minutes of inactivity. Kids log in with their avatar and PIN.

### 7.3 Family smartphone or laptop

Open `https://nestwerk.<YOUR-DOMAIN>/` in the browser. Parents log in with the shared parent password and their name.

---

## 8. Updates

Updates automatically take a database backup before the migration. If something fails, the installer rolls back the image.

**With a Git remote:**

```bash
cd /opt/nestwerk
deploy/update.sh
```

**Without a remote, via bundle** (from the development machine):

```bash
git bundle create /tmp/nestwerk.bundle main
scp /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle
ssh root@<VM-IP> 'cd /opt/nestwerk && deploy/update.sh --bundle /root/nestwerk.bundle'
```

The bundle must contain `main` as a fast-forward of the state on the VM. A rewritten history is rejected.

Other options:

- `deploy/update.sh --force`: rebuilds the image even without a new commit.
- `deploy/rollback.sh`: back to the previous image (the database stays).
- `deploy/rollback.sh <sha> --mit-db`: also restores the pre-update backup. All data since the update is lost.

After a failed update: fix the error and deploy **another commit**. No `git reset` on the VM.

---

## 9. Backup and restore

Nestwerk backs up two things. The Proxmox backup is an additional layer.

**Layer 1: Proxmox VM backup** (daily, configurable in Proxmox).

**Layer 2: database dumps** (automatic):

- Daily at 03:30 (catch-up at 13:30), a compressed SQLite dump to `/srv/nestwerk/backup`.
- Retention: 14 daily, 8 weekly and 12 monthly dumps, plus the last 5 update backups. Configurable in the `.env` (see `.env.example`).
- Weekly check (Sun 04:30): `backup_pruefen` checks the latest backup and reports errors to the parents.

**Not backed up:** proof photos (privacy) and secrets (see below).

**Layer 3 (recommended):** also copy `/srv/nestwerk/backup` to a NAS outside the Proxmox host.

### 9.1 Restore drill (before go-live and then every six months)

```bash
cd /opt/nestwerk
docker compose exec scheduler python manage.py db_sichern --grund=manuell
docker compose exec scheduler python manage.py backup_pruefen
docker compose stop web worker scheduler
docker compose run --rm --no-deps web python manage.py db_wiederherstellen neuestes
docker compose up -d
curl -s http://<VM-IP>:8000/gesundheit/
```

The old database stays in the volume as `*.vor-restore-<time>`. After a successful drill you can delete it.

### 9.2 Backing up secrets

The volume holds `django_secret_key`, `fernet.key` (encrypts the SMTP password) and `vapid_private.pem` (push). **Without the VAPID key, all push subscriptions are invalid.** Without the Fernet key you have to re-enter the SMTP password. The database dumps deliberately do not contain them.

```bash
deploy/secrets-sichern.sh /srv/nestwerk/geheimnisse
```

The archive is encrypted with AES-256. Store the archive **and** the passphrase separately from the VM, e.g. in a password manager or on a USB stick.

---

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Page not reachable | `docker compose ps`; `curl http://<VM-IP>:8000/gesundheit/` on the VM; proxy host and certificate; `nft list table inet nestwerk_fw` |
| Container keeps restarting | `docker compose logs --tail=100 web` (or `worker`, `scheduler`) |
| `/gesundheit/` is not 200 | Read the response; pending migrations? `docker compose run --rm web python manage.py migrate` |
| Jobs don't run | `docker compose logs scheduler`; parent dashboard, system status; crontab in `deploy/crontab` |
| No push on the iPhone | App opened from the home screen? Subscription present in the settings? `*.push.apple.com:443` reachable from the VM? |
| No backups | `ls -l /srv/nestwerk/backup`; owner UID 1000; `docker compose exec scheduler python manage.py db_sichern` by hand |
| Port 8000 reachable from the wrong network | `systemctl status nestwerk-firewall`; re-run `deploy/install.sh` with the correct `--npm-ip` |
| Photo upload fails, log reports `/tmp/nginx/body` missing | See section 10.1 |

### 10.1 NPM: error "/tmp/nginx/body missing"

**Symptom:** proof uploads fail. The Nginx Proxy Manager log reports that the directory `/tmp/nginx/body` is missing.

**Cause:** the directory is in `/tmp`. It is gone after a restart, because `/tmp` is cleared at boot. This often happens with NPM in an LXC container.

**Fix:** create a `tmpfiles.d` entry so that systemd creates the directory at every boot:

```bash
# Find the user and group of the NPM process:
ps -o user=,group= -C nginx | head -1

# Create the entry (adjust user and group):
cat > /etc/tmpfiles.d/npm-body.conf <<'EOF'
d /tmp/nginx/body 0700 <NPM-USER> <NPM-GROUP> -
EOF

systemd-tmpfiles --create /etc/tmpfiles.d/npm-body.conf
```

Then restart NPM. The entry takes effect on every restart.

---

## 11. Privacy notes for operation

- **All data stays on your server.** There are no analytics or tracking services.
- **Fonts** are served by the app itself, not from Google Fonts.
- **Photos** (proofs) are deleted immediately after approval. The log only keeps a note of who approved.
- **Access** only from the home network. Remotely only via your own VPN.
- Remove **NESTWERK_SETUP_TOKEN** after setup.

More information: [operations runbook](RUNBOOK.md), [`docs/SPEC.md` (German)](../SPEC.md).
