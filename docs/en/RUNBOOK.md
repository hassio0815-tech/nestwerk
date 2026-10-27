# Nestwerk Runbook (operations)

🇬🇧 **English** · 🇩🇪 [Deutsch](../RUNBOOK.md)

Target system: Debian 13 VM (2 vCPU, 4 GB, 46 GB) with Docker Compose. In front of it: Nginx Proxy Manager (NPM, TLS), local DNS via AdGuard. Run all commands on the VM in the folder `/opt/nestwerk`, as user `nestwerk` (group `docker`) or as root.

## 1. Preparing the VM

1. Install Debian 13 minimal + SSH, assign a fixed IP (e.g. `<VM-IP>`).
2. Use a local disk, **never** NFS/SMB for `/var/lib/docker` (SQLite WAL).
3. Proxmox: set up a daily VM backup (layer 1 of the data backup).
4. Time zone: `timedatectl set-timezone Europe/Berlin`.

## 2. Installation

There is no Git remote: the code comes as a Git bundle from the development machine.

```bash
# Development machine (in the repo, branch main):
git bundle create /tmp/nestwerk.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle

# VM (as root; sudo is not installed on minimal Debian):
apt-get install -y git
git clone -b main /root/nestwerk.bundle /opt/nestwerk && cd /opt/nestwerk
deploy/install.sh --npm-ip <NPM-IP> --heimnetz <HOME-NET-CIDR> --ohne-start
# adjust .env (see below), then again without --ohne-start:
deploy/install.sh --npm-ip <NPM-IP>
```

The script (idempotent, can be re-run) installs Docker Engine + Compose plugin from the official Docker APT repository, creates the user `nestwerk`, `/srv/nestwerk/backup` (UID 1000) and `/srv/nestwerk/geheimnisse` (0700), generates `.env` (incl. `NESTWERK_SETUP_TOKEN`), sets up the firewall (nftables, **port 8000 only from the NPM IP**, plus the egress block, section 2a), builds, migrates and starts. At the end the setup token is printed (it is also in `/opt/nestwerk/.env`).

**`.env` before the first start** (`/opt/nestwerk/.env`; with `--domain nestwerk.<domain>` the script sets the first three values itself):

- `NESTWERK_ALLOWED_HOSTS`: Django only knows exact names or suffix patterns with a leading dot (`.example.org`), not `nestwerk.*`. Until the subdomain is fixed: VM IP; afterwards `nestwerk.<domain>` (health check hosts `localhost`/`127.0.0.1` are added automatically).
- `NESTWERK_CSRF_TRUSTED_ORIGINS`: `https://nestwerk.<domain>` (temporarily `http://<VM-IP>:8000`).
- `NESTWERK_BASIS_URL`: `https://nestwerk.<domain>` (temporarily `http://<VM-IP>:8000`).
- After changes: `docker compose up -d` (recreate the containers).

Check: `curl http://<VM-IP>:8000/gesundheit/` **on the VM** returns 200 (`web` is bound only to the VM IP, not to 127.0.0.1); from the laptop it must not respond. The VM IP is assigned via DHCP: set a fixed reservation in the router, otherwise `NESTWERK_BIND_IP` will be wrong after an IP change.

### 2a. Egress block for the containers

`/etc/nestwerk/firewall.nft` stops containers (bridges `br-*`) from opening new connections to private networks (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, 127/8) and to the VM itself. This is a second layer against DNS rebinding on push endpoints. Still allowed: the internet (including SMTP), the DNS resolvers from `/etc/resolv.conf` (entered during installation; if the resolvers change, re-run `deploy/install.sh --npm-ip ...`), and targets from `NESTWERK_EGRESS_ERLAUBT` (comma-separated list, e.g. an SMTP relay on the LAN: `deploy/install.sh --npm-ip <NPM-IP> --egress-erlaubt <SMTP-IP>`). Check: `nft list table inet nestwerk_fw`; inside the container, `docker compose exec worker python -c ...` with `socket.connect` to a LAN IP must run into the timeout.

## 3. NPM proxy host

- Domain: `nestwerk.<domain>` -> Scheme `http`, Forward Host `<VM-IP>`, Forward Port `8000`.
- **Websockets: off.** Block Common Exploits: on. Cache Assets: **off**.
- SSL: new certificate, **Let's Encrypt with DNS challenge** (Cloudflare API token), Force SSL + HTTP/2 on, HSTS on.
- **No access list** on the host. `/sw.js` and `/manifest.json` must be served without login and without cache (no custom cache, no auth rule).
- Upload size: in the **Advanced** tab, add `client_max_body_size 50m;` (proof photos; the app itself limits uploads via the settings `aufgaben.nachweis_max_upload_mb`/`_max_anzahl`).
- **Only one proxy hop:** Nestwerk only reads the rightmost entry of `X-Forwarded-For` (the one NPM appends). No further proxy in front of NPM. In the wizard (step 5), under "Trusted proxies", enter only the NPM IP (review AP19, B-02).
- Check: `https://nestwerk.<domain>/gesundheit/` returns 200.

## 4. AdGuard DNS

AdGuard Home -> Filters -> DNS rewrites: `nestwerk.<domain>` -> `<NPM-IP>` (IP of the NPM, **not** the VM). Check: `nslookup nestwerk.<domain>` on the home network.

## 5. Setup wizard

Open `https://nestwerk.<domain>/einrichtung/`, enter `NESTWERK_SETUP_TOKEN` from `.env` (`grep SETUP_TOKEN /opt/nestwerk/.env`), and work through the steps. Afterwards remove the token from `.env` and run `docker compose up -d`.

## 6. iPhone push test (iOS 16.4+)

1. Safari: open `https://nestwerk.<domain>` -> Share -> **Add to Home Screen**.
2. **Open it as a web app** (icon on the home screen, not Safari).
3. Log in to the app -> Settings -> **Turn on notifications**, and allow the system dialog.
4. Trigger **Send test push**; the message arrives within a few seconds. Otherwise: section 12.

## 7. Tablet as kiosk

- Fully Kiosk Browser: start URL `https://nestwerk.<domain>/`, keep the screen on at all times, kiosk mode on.
- As a parent in Nestwerk: Parents -> Devices -> mark the tablet as **Kiosk (hallway tablet)**.

## 8. Updates

Without a Git remote, via bundle (development machine -> VM):

```bash
git bundle create /tmp/nestwerk.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle
ssh -i ~/.ssh/<SSH-KEY> root@<VM-IP> 'cd /opt/nestwerk && deploy/update.sh --bundle /root/nestwerk.bundle'
```

`deploy/update.sh` on its own (without `--bundle`) uses `git pull --ff-only` and needs a remote. `--force` rebuilds even without a new commit. The bundle must contain `main` as a fast-forward of the state on the VM (no rewritten history).

Sequence: check and apply the bundle, build image `nestwerk:<sha>`, stop services, **DB backup (`--grund=update`)**, `migrate`, restart, wait for `healthy`. If something fails after the stop, the script rolls back by itself (old image; if the migration failed, also the DB from the backup; both tested on 2026-10-23). Migrations are additive (expand/contract).

Limits: a rollback only swaps the **image**. `compose.yaml`, `deploy/` and the Git state stay on the new commit. So after a failed update, fix the error and deploy **another commit** (no `git reset` on the VM). If `compose.yaml` itself is the problem, the rollback fails as well; then correct the file in a commit and update again. The firewall file is not renewed by the update, only by `install.sh`.

## 9. Rollback (manual)

```bash
deploy/rollback.sh                       # back to the previous image (DB stays)
deploy/rollback.sh <sha> --mit-db        # also restore the pre-update backup
```

`--mit-db` discards all data since the update backup; the previous DB stays in the volume as `nestwerk.sqlite3.vor-restore-<time>`. Existing images: `docker images nestwerk`.

## 10. Backup and restore drill (< 15 min)

**What is backed up:** daily at 03:30 (catch-up at 13:30) the scheduler writes a consistent, compressed SQLite dump via `db_sichern` to `/srv/nestwerk/backup` (`nestwerk-JJJJMMTT-HHMMSS-taeglich.sqlite3.gz`). Retention: 14 daily, 8 weekly, 12 monthly (each the newest of its period), plus the last 5 update backups. Configurable via `.env`: `NESTWERK_BACKUP_TAEGLICH`, `_WOECHENTLICH`, `_MONATLICH`, `_UPDATE_BEHALTEN`, `_MAX_ALTER_STUNDEN`. **Not backed up:** proof photos (privacy) and secrets (section 11). A proof text may remain in the dump until the retention period expires (deliberately accepted).

**Weekly test:** `backup_pruefen` (Sun 04:30) unpacks the newest backup into a temp DB, checks `integrity_check` and age (max. 36 h), and compares the ledger rows with the live DB. Errors: job run `fehler` plus push/email to the parents (`system.backup_fehler`).

**Restore drill** (before go-live, then every six months):

```bash
cd /opt/nestwerk
docker compose exec scheduler python manage.py db_sichern --grund=manuell   # fresh state
docker compose exec scheduler python manage.py backup_pruefen               # test without intervention
docker compose stop web worker scheduler
docker compose run --rm --no-deps web python manage.py db_wiederherstellen neuestes
docker compose up -d
curl -s http://<VM-IP>:8000/gesundheit/                                     # 200? (on the VM)
```

`db_wiederherstellen <file|neuestes> [--grund=taeglich|update|manuell]` replaces the live DB; the old one is kept as `*.vor-restore-<time>` (delete it in the volume after a successful drill). Total loss of the VM: restore the Proxmox backup, or set up a fresh VM (section 2) and place the dump in `/srv/nestwerk/backup`, then proceed as above with `db_wiederherstellen /backup/<file>` before the services start for the first time.

Recommendation (layer 3): also copy `/srv/nestwerk/backup` to a NAS outside the Proxmox host.

## 11. Backing up secrets

In the volume under `/data/secrets`: `django_secret_key`, `fernet.key` (encrypts the SMTP password), `vapid_private.pem` (push). **Losing the VAPID key = all push subscriptions become invalid; losing the Fernet key = re-enter the SMTP password.** The DB backups deliberately do not contain them.

```bash
deploy/secrets-sichern.sh /srv/nestwerk/geheimnisse     # AES-256 encrypted archive, passphrase is prompted
```

Store the archive **and** the passphrase separately from the VM (password manager/USB). Repeat after every change to the secrets (rare). To restore:
`openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in <file> | docker compose run --rm --no-deps -T web tar -xzf - -C /data`.
The domain/host values in `.env` are not secrets, but remove `NESTWERK_SETUP_TOKEN` after setup.

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| Page not reachable | `docker compose ps`; `curl http://<VM-IP>:8000/gesundheit/`; NPM host/certificate; nftables: `nft list table inet nestwerk_fw` |
| Container keeps restarting | `docker compose logs --tail=100 web` (or `worker`, `scheduler`) |
| `/gesundheit/` not 200 | Read the response: DB readable? Pending migrations? Worker heartbeat? Then `docker compose run --rm web python manage.py migrate` |
| Jobs don't run | `docker compose logs scheduler`; parent dashboard -> system status (job runs); crontab: `deploy/crontab` |
| No push | Web app opened from the home screen? Subscription in settings? `docker compose logs worker`; outbound `*.push.apple.com:443` open? |
| No backups | `ls -l /srv/nestwerk/backup`; permissions (UID 1000); `docker compose exec scheduler python manage.py db_sichern` by hand |
| Port 8000 reachable from the wrong network | `systemctl status nestwerk-firewall`; re-run `deploy/install.sh` with the correct `--npm-ip` |

Logs rotate automatically (10 MB x 3 per container). Job results are in the table `JobLauf` (admin/system status).

## 13. Migrating an existing FamKo installation

Nestwerk was formerly called FamKo. A running installation does **not** need renaming and loses no data.

**Stays compatible automatically**

| What | Behaviour |
|---|---|
| `.env` with `FAMKO_*` | Still applies as a fallback; `NESTWERK_*` takes precedence, both may be mixed |
| Compose project, volume, image | `update.sh` detects the old `.env` and volume (`famko_famko_data` or `famko_data`) and adds: `COMPOSE_PROJECT_NAME=famko` (from the volume label), `NESTWERK_DATA_VOLUME=<old volume>`, `NESTWERK_IMAGE=famko` |
| Image tags, rollback | Still `famko:<sha>`; `rollback.sh` and `famko:vorher` work as before |
| Database | `/data/db/famko.sqlite3` continues to be used (only if no `nestwerk.sqlite3` exists) |
| Backups | Files `famko-*.sqlite3.gz` are recognised, rotated and restored; new ones are called `nestwerk-*.sqlite3.gz` |
| Paths, user, firewall | `/opt/famko`, user `famko`, `/etc/famko`, service `famko-firewall` remain; a new `install.sh` recognises and keeps them |
| App labels, migrations | Unchanged (no migration intervention) |

**One-time step at the first update to the Nestwerk version** (the old `update.sh` is overwritten by `git pull`, so first fetch the code by hand and then run the new script):

```bash
cd /opt/famko
git fetch /root/nestwerk.bundle main && git merge --ff-only FETCH_HEAD   # or: git pull --ff-only
deploy/update.sh --force
grep -E '^(COMPOSE_PROJECT_NAME|NESTWERK_DATA_VOLUME|NESTWERK_IMAGE)=' .env   # check
```

Expected `.env` additions (`update.sh` sets these itself; if necessary, add them by hand; `docker volume ls` shows the volume name):

```
COMPOSE_PROJECT_NAME=famko
NESTWERK_DATA_VOLUME=famko_famko_data
NESTWERK_IMAGE=famko
```

Emergency: if the app starts empty after an update (the wizard appears again), a new volume `nestwerk_data` was created. The data is unchanged in the old volume. Add the `.env` lines as above and run `docker compose up -d`.

**Optional, not necessary:** rename paths, volume or image by hand. If you still want to, first back up the DB (`db_sichern`) and the secrets (section 11), and only remove the three lines above once the volume has been copied.
