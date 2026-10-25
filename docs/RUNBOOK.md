# FamKo Runbook (Betrieb)

Zielsystem: Debian-13-VM (2 vCPU, 4 GB, 46 GB) mit Docker Compose. Davor Nginx Proxy Manager (NPM, TLS), lokaler DNS per AdGuard. Alle Befehle auf der VM im Ordner `/opt/famko`, als Benutzer `famko` (Gruppe `docker`) oder root.

## 1. VM vorbereiten

1. Debian 13 minimal + SSH installieren, feste IP vergeben (z. B. `<VM-IP>`).
2. Lokale Platte verwenden, **nie** NFS/SMB fuer `/var/lib/docker` (SQLite-WAL).
3. Proxmox: tägliches VM-Backup einrichten (Ebene 1 der Datensicherung).
4. Zeitzone: `timedatectl set-timezone Europe/Berlin`.

## 2. Installation

Es gibt kein Git-Remote: der Code kommt als Git-Bundle vom Entwicklungsrechner.

```bash
# Entwicklungsrechner (im Repo, Branch main):
git bundle create /tmp/famko.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/famko.bundle root@<VM-IP>:/root/famko.bundle

# VM (als root; sudo ist auf Debian minimal nicht installiert):
apt-get install -y git
git clone -b main /root/famko.bundle /opt/famko && cd /opt/famko
deploy/install.sh --npm-ip <NPM-IP> --heimnetz <HEIMNETZ-CIDR> --ohne-start
# .env anpassen (siehe unten), dann erneut ohne --ohne-start:
deploy/install.sh --npm-ip <IP-des-NPM>
```

Das Skript (idempotent, darf wiederholt werden) installiert Docker Engine + Compose-Plugin aus dem offiziellen Docker-APT-Repo, legt Benutzer `famko`, `/srv/famko/backup` (UID 1000) und `/srv/famko/geheimnisse` (0700) an, erzeugt `.env` (inkl. `FAMKO_SETUP_TOKEN`), setzt die Firewall (nftables, **Port 8000 nur von der NPM-IP**, plus Egress-Sperre, Abschnitt 2a), baut, migriert und startet. Am Ende wird das Setup-Token ausgegeben (steht auch in `/opt/famko/.env`).

**`.env` vor dem ersten Start** (`/opt/famko/.env`; mit `--domain famko.<domain>` setzt das Skript die ersten drei Werte selbst):

- `FAMKO_ALLOWED_HOSTS`: Django kennt nur exakte Namen oder Suffix-Muster mit führendem Punkt (`.example.org`), kein `famko.*`. Bis die Subdomain feststeht: VM-IP; danach `famko.<domain>` (Healthcheck-Hosts `localhost`/`127.0.0.1` kommen automatisch dazu).
- `FAMKO_CSRF_TRUSTED_ORIGINS`: `https://famko.<domain>` (vorläufig `http://<VM-IP>:8000`).
- `FAMKO_BASIS_URL`: `https://famko.<domain>` (vorläufig `http://<VM-IP>:8000`).
- Nach Änderungen: `docker compose up -d` (Container neu erstellen).

Prüfen: `curl http://<VM-IP>:8000/gesundheit/` **auf der VM** liefert 200 (`web` ist nur an die VM-IP gebunden, nicht an 127.0.0.1); vom Laptop aus muss es hängen. Die VM-IP wird per DHCP vergeben: im Router eine feste Reservierung eintragen, sonst stimmt `FAMKO_BIND_IP` nach einem IP-Wechsel nicht mehr.

### 2a. Egress-Sperre der Container

`/etc/famko/firewall.nft` verbietet Containern (Bridges `br-*`) neue Verbindungen in private Netze (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, 127/8) und zur VM selbst, als zweite Schicht gegen DNS-Rebinding bei Push-Endpunkten. Erlaubt bleiben Internet (auch SMTP), DNS-Resolver aus `/etc/resolv.conf` (beim Installieren eingetragen; ändern sich die Resolver, `deploy/install.sh --npm-ip ...` erneut ausführen) und Ziele aus `FAMKO_EGRESS_ERLAUBT` (Komma-Liste, z. B. ein SMTP-Relay im LAN: `deploy/install.sh --npm-ip <NPM-IP> --egress-erlaubt <SMTP-IP>`). Prüfen: `nft list table inet famko_fw`; im Container `docker compose exec worker python -c ...` mit `socket.connect` zu einer LAN-IP muss in den Timeout laufen.

## 3. NPM-Proxy-Host

- Domain: `famko.<domain>` -> Scheme `http`, Forward Host `<VM-IP>`, Forward Port `8000`.
- **Websockets: aus.** Block Common Exploits: an. Cache Assets: **aus**.
- SSL: neues Zertifikat, **Let's Encrypt mit DNS-Challenge** (Cloudflare-API-Token), Force SSL + HTTP/2 an, HSTS an.
- **Keine Access-List** auf dem Host. `/sw.js` und `/manifest.json` müssen ohne Login und ohne Cache ausgeliefert werden (kein Custom-Cache, keine Auth-Regel).
- Upload-Größe: Im Tab **Advanced** `client_max_body_size 50m;` eintragen (Nachweis-Fotos; die App selbst begrenzt über die Einstellungen `aufgaben.nachweis_max_upload_mb`/`_max_anzahl`).
- **Nur ein Proxy-Hop:** FamKo wertet von `X-Forwarded-For` nur den rechtesten Eintrag aus (den der NPM anhängt). Kein weiterer Proxy vor dem NPM. Im Assistenten (Schritt 5) bei „Vertraute Proxys“ nur die NPM-IP eintragen (Review AP19, B-02).
- Prüfen: `https://famko.<domain>/gesundheit/` liefert 200.

## 4. AdGuard-DNS

AdGuard Home -> Filter -> DNS-Umschreibungen: `famko.<domain>` -> `<NPM-IP>` (IP des NPM, **nicht** der VM). Prüfen: `nslookup famko.<domain>` im Heimnetz.

## 5. Einrichtungs-Assistent

`https://famko.<domain>/einrichtung/` öffnen, `FAMKO_SETUP_TOKEN` aus `.env` eingeben (`grep SETUP_TOKEN /opt/famko/.env`), Schritte durcharbeiten. Danach Token aus `.env` entfernen und `docker compose up -d`.

## 6. Push-Test iPhone (iOS 16.4+)

1. Safari: `https://famko.<domain>` öffnen -> Teilen -> **Zum Home-Bildschirm**.
2. **Als Web-App öffnen** (Icon auf dem Home-Bildschirm, nicht Safari).
3. In der App einloggen -> Einstellungen -> **Benachrichtigungen aktivieren**, System-Dialog erlauben.
4. **Test-Push** auslösen; Nachricht kommt innerhalb weniger Sekunden. Sonst: Abschnitt 12.

## 7. Tablet als Kiosk

- Fully Kiosk Browser: Start-URL `https://famko.<domain>/`, Bildschirm immer an, Kiosk-Modus an.
- Als Eltern in FamKo: Eltern -> Geräte -> das Tablet als **Tablet/Kiosk markieren**.

## 8. Updates

Ohne Git-Remote per Bundle (Entwicklungsrechner -> VM):

```bash
git bundle create /tmp/famko.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/famko.bundle root@<VM-IP>:/root/famko.bundle
ssh -i ~/.ssh/<SSH-KEY> root@<VM-IP> 'cd /opt/famko && deploy/update.sh --bundle /root/famko.bundle'
```

`deploy/update.sh` allein (ohne `--bundle`) nutzt `git pull --ff-only` und braucht ein Remote. `--force` baut auch ohne neuen Commit neu. Das Bundle muss `main` als Fast-Forward des Stands auf der VM enthalten (keine umgeschriebene Historie).

Ablauf: Bundle prüfen und übernehmen, Image `famko:<sha>` bauen, Dienste stoppen, **DB-Backup (`--grund=update`)**, `migrate`, Neustart, Warten auf `healthy`. Schlägt etwas nach dem Stoppen fehl, rollt das Skript selbst zurück (altes Image, bei fehlgeschlagener Migration zusätzlich die DB aus dem Backup; beides am 2026-10-23 getestet). Migrationen sind additiv (expand/contract).

Grenzen: Ein Rollback tauscht nur das **Image**. `compose.yaml`, `deploy/` und der Git-Stand bleiben auf dem neuen Commit. Nach einem fehlgeschlagenen Update also den Fehler beheben und ein **weiteres Commit** ausliefern (kein `git reset` auf der VM). Ist `compose.yaml` selbst das Problem, scheitert auch der Rollback; dann die Datei im Commit korrigieren und erneut updaten. Die Firewall-Datei wird nicht vom Update erneuert, nur von `install.sh`.

## 9. Rollback (manuell)

```bash
deploy/rollback.sh                       # zurück auf das vorherige Image (DB bleibt)
deploy/rollback.sh <sha> --mit-db        # zusätzlich Pre-Update-Backup zurückspielen
```

`--mit-db` verwirft alle Daten seit dem Update-Backup; die bisherige DB bleibt als `famko.sqlite3.vor-restore-<zeit>` im Volume. Vorhandene Images: `docker images famko`.

## 10. Backup und Restore-Übung (< 15 min)

**Was wird gesichert:** Täglich 03:30 (Nachholtermin 13:30) schreibt der Scheduler per `db_sichern` einen konsistenten, komprimierten SQLite-Dump nach `/srv/famko/backup` (`famko-JJJJMMTT-HHMMSS-taeglich.sqlite3.gz`). Aufbewahrung: 14 tägliche, 8 wöchentliche, 12 monatliche (je das neueste einer Periode), dazu die letzten 5 Update-Backups. Einstellbar per `.env`: `FAMKO_BACKUP_TAEGLICH`, `_WOECHENTLICH`, `_MONATLICH`, `_UPDATE_BEHALTEN`, `_MAX_ALTER_STUNDEN`. **Nicht gesichert:** Nachweis-Fotos (Datenschutz) und Secrets (Abschnitt 11). Ein Nachweis-Text kann bis zum Ablauf der Aufbewahrung im Dump liegen (bewusst akzeptiert).

**Wöchentlicher Test:** `backup_pruefen` (So 04:30) entpackt das neueste Backup in eine Temp-DB, prüft `integrity_check`, Alter (max. 36 h) und vergleicht die Ledger-Zeilen mit der Live-DB. Fehler: Job-Lauf `fehler` plus Push/E-Mail an die Eltern (`system.backup_fehler`).

**Restore-Übung** (vor Go-live und dann halbjährlich):

```bash
cd /opt/famko
docker compose exec scheduler python manage.py db_sichern --grund=manuell   # frischer Stand
docker compose exec scheduler python manage.py backup_pruefen               # Test ohne Eingriff
docker compose stop web worker scheduler
docker compose run --rm --no-deps web python manage.py db_wiederherstellen neuestes
docker compose up -d
curl -s http://<VM-IP>:8000/gesundheit/                                     # 200? (auf der VM)
```

`db_wiederherstellen <datei|neuestes> [--grund=taeglich|update|manuell]` ersetzt die Live-DB; die alte bleibt als `*.vor-restore-<zeit>` erhalten (nach erfolgreicher Übung im Volume löschen). Totalverlust der VM: Proxmox-Backup zurückspielen oder frische VM (Abschnitt 2) und Dump nach `/srv/famko/backup` legen, dann wie oben mit `db_wiederherstellen /backup/<datei>` vor dem ersten Start der Dienste.

Empfehlung (Ebene 3): `/srv/famko/backup` zusätzlich auf ein NAS außerhalb des Proxmox-Hosts kopieren.

## 11. Secrets sichern

Im Volume unter `/data/secrets`: `django_secret_key`, `fernet.key` (verschlüsselt das SMTP-Passwort), `vapid_private.pem` (Push). **Verlust des VAPID-Schlüssels = alle Push-Abos ungültig, Verlust des Fernet-Schlüssels = SMTP-Passwort neu eingeben.** Die DB-Backups enthalten sie bewusst nicht.

```bash
deploy/secrets-sichern.sh /srv/famko/geheimnisse     # AES-256-verschlüsseltes Archiv, Passphrase wird abgefragt
```

Archiv **und** Passphrase getrennt von der VM aufbewahren (Passwortmanager/USB). Nach jeder Änderung der Secrets (selten) wiederholen. Zurückspielen:
`openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in <datei> | docker compose run --rm --no-deps -T web tar -xzf - -C /data`.
Die Domain-/Host-Werte in `.env` sind keine Secrets, aber `FAMKO_SETUP_TOKEN` nach der Einrichtung entfernen.

## 12. Fehlersuche

| Symptom | Prüfen |
|---|---|
| Seite nicht erreichbar | `docker compose ps`; `curl http://<VM-IP>:8000/gesundheit/`; NPM-Host/-Zertifikat; nftables: `nft list table inet famko_fw` |
| Container startet neu | `docker compose logs --tail=100 web` (bzw. `worker`, `scheduler`) |
| `/gesundheit/` nicht 200 | Antwort lesen: DB lesbar? Migrationen offen? Worker-Herzschlag? Dann `docker compose run --rm web python manage.py migrate` |
| Jobs laufen nicht | `docker compose logs scheduler`; Eltern-Dashboard -> Systemstatus (Job-Läufe); Crontab: `deploy/crontab` |
| Kein Push | Web-App vom Home-Bildschirm geöffnet? Abo in Einstellungen vorhanden? `docker compose logs worker`; ausgehend `*.push.apple.com:443` frei? |
| Keine Backups | `ls -l /srv/famko/backup`; Rechte (UID 1000); `docker compose exec scheduler python manage.py db_sichern` von Hand |
| Port 8000 aus falschem Netz erreichbar | `systemctl status famko-firewall`; `deploy/install.sh` mit richtiger `--npm-ip` erneut ausführen |

Logs rotieren automatisch (10 MB x 3 je Container). Job-Ergebnisse stehen in der Tabelle `JobLauf` (Admin/Systemstatus).
