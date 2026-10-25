# Nestwerk Runbook (Betrieb)

Zielsystem: Debian-13-VM (2 vCPU, 4 GB, 46 GB) mit Docker Compose. Davor Nginx Proxy Manager (NPM, TLS), lokaler DNS per AdGuard. Alle Befehle auf der VM im Ordner `/opt/nestwerk`, als Benutzer `nestwerk` (Gruppe `docker`) oder root.

## 1. VM vorbereiten

1. Debian 13 minimal + SSH installieren, feste IP vergeben (z. B. `<VM-IP>`).
2. Lokale Platte verwenden, **nie** NFS/SMB fuer `/var/lib/docker` (SQLite-WAL).
3. Proxmox: tägliches VM-Backup einrichten (Ebene 1 der Datensicherung).
4. Zeitzone: `timedatectl set-timezone Europe/Berlin`.

## 2. Installation

Es gibt kein Git-Remote: der Code kommt als Git-Bundle vom Entwicklungsrechner.

```bash
# Entwicklungsrechner (im Repo, Branch main):
git bundle create /tmp/nestwerk.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle

# VM (als root; sudo ist auf Debian minimal nicht installiert):
apt-get install -y git
git clone -b main /root/nestwerk.bundle /opt/nestwerk && cd /opt/nestwerk
deploy/install.sh --npm-ip <NPM-IP> --heimnetz <HEIMNETZ-CIDR> --ohne-start
# .env anpassen (siehe unten), dann erneut ohne --ohne-start:
deploy/install.sh --npm-ip <IP-des-NPM>
```

Das Skript (idempotent, darf wiederholt werden) installiert Docker Engine + Compose-Plugin aus dem offiziellen Docker-APT-Repo, legt Benutzer `nestwerk`, `/srv/nestwerk/backup` (UID 1000) und `/srv/nestwerk/geheimnisse` (0700) an, erzeugt `.env` (inkl. `NESTWERK_SETUP_TOKEN`), setzt die Firewall (nftables, **Port 8000 nur von der NPM-IP**, plus Egress-Sperre, Abschnitt 2a), baut, migriert und startet. Am Ende wird das Setup-Token ausgegeben (steht auch in `/opt/nestwerk/.env`).

**`.env` vor dem ersten Start** (`/opt/nestwerk/.env`; mit `--domain nestwerk.<domain>` setzt das Skript die ersten drei Werte selbst):

- `NESTWERK_ALLOWED_HOSTS`: Django kennt nur exakte Namen oder Suffix-Muster mit führendem Punkt (`.example.org`), kein `nestwerk.*`. Bis die Subdomain feststeht: VM-IP; danach `nestwerk.<domain>` (Healthcheck-Hosts `localhost`/`127.0.0.1` kommen automatisch dazu).
- `NESTWERK_CSRF_TRUSTED_ORIGINS`: `https://nestwerk.<domain>` (vorläufig `http://<VM-IP>:8000`).
- `NESTWERK_BASIS_URL`: `https://nestwerk.<domain>` (vorläufig `http://<VM-IP>:8000`).
- Nach Änderungen: `docker compose up -d` (Container neu erstellen).

Prüfen: `curl http://<VM-IP>:8000/gesundheit/` **auf der VM** liefert 200 (`web` ist nur an die VM-IP gebunden, nicht an 127.0.0.1); vom Laptop aus muss es hängen. Die VM-IP wird per DHCP vergeben: im Router eine feste Reservierung eintragen, sonst stimmt `NESTWERK_BIND_IP` nach einem IP-Wechsel nicht mehr.

### 2a. Egress-Sperre der Container

`/etc/nestwerk/firewall.nft` verbietet Containern (Bridges `br-*`) neue Verbindungen in private Netze (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, 127/8) und zur VM selbst, als zweite Schicht gegen DNS-Rebinding bei Push-Endpunkten. Erlaubt bleiben Internet (auch SMTP), DNS-Resolver aus `/etc/resolv.conf` (beim Installieren eingetragen; ändern sich die Resolver, `deploy/install.sh --npm-ip ...` erneut ausführen) und Ziele aus `NESTWERK_EGRESS_ERLAUBT` (Komma-Liste, z. B. ein SMTP-Relay im LAN: `deploy/install.sh --npm-ip <NPM-IP> --egress-erlaubt <SMTP-IP>`). Prüfen: `nft list table inet nestwerk_fw`; im Container `docker compose exec worker python -c ...` mit `socket.connect` zu einer LAN-IP muss in den Timeout laufen.

## 3. NPM-Proxy-Host

- Domain: `nestwerk.<domain>` -> Scheme `http`, Forward Host `<VM-IP>`, Forward Port `8000`.
- **Websockets: aus.** Block Common Exploits: an. Cache Assets: **aus**.
- SSL: neues Zertifikat, **Let's Encrypt mit DNS-Challenge** (Cloudflare-API-Token), Force SSL + HTTP/2 an, HSTS an.
- **Keine Access-List** auf dem Host. `/sw.js` und `/manifest.json` müssen ohne Login und ohne Cache ausgeliefert werden (kein Custom-Cache, keine Auth-Regel).
- Upload-Größe: Im Tab **Advanced** `client_max_body_size 50m;` eintragen (Nachweis-Fotos; die App selbst begrenzt über die Einstellungen `aufgaben.nachweis_max_upload_mb`/`_max_anzahl`).
- **Nur ein Proxy-Hop:** Nestwerk wertet von `X-Forwarded-For` nur den rechtesten Eintrag aus (den der NPM anhängt). Kein weiterer Proxy vor dem NPM. Im Assistenten (Schritt 5) bei „Vertraute Proxys“ nur die NPM-IP eintragen (Review AP19, B-02).
- Prüfen: `https://nestwerk.<domain>/gesundheit/` liefert 200.

## 4. AdGuard-DNS

AdGuard Home -> Filter -> DNS-Umschreibungen: `nestwerk.<domain>` -> `<NPM-IP>` (IP des NPM, **nicht** der VM). Prüfen: `nslookup nestwerk.<domain>` im Heimnetz.

## 5. Einrichtungs-Assistent

`https://nestwerk.<domain>/einrichtung/` öffnen, `NESTWERK_SETUP_TOKEN` aus `.env` eingeben (`grep SETUP_TOKEN /opt/nestwerk/.env`), Schritte durcharbeiten. Danach Token aus `.env` entfernen und `docker compose up -d`.

## 6. Push-Test iPhone (iOS 16.4+)

1. Safari: `https://nestwerk.<domain>` öffnen -> Teilen -> **Zum Home-Bildschirm**.
2. **Als Web-App öffnen** (Icon auf dem Home-Bildschirm, nicht Safari).
3. In der App einloggen -> Einstellungen -> **Benachrichtigungen aktivieren**, System-Dialog erlauben.
4. **Test-Push** auslösen; Nachricht kommt innerhalb weniger Sekunden. Sonst: Abschnitt 12.

## 7. Tablet als Kiosk

- Fully Kiosk Browser: Start-URL `https://nestwerk.<domain>/`, Bildschirm immer an, Kiosk-Modus an.
- Als Eltern in Nestwerk: Eltern -> Geräte -> das Tablet als **Tablet/Kiosk markieren**.

## 8. Updates

Ohne Git-Remote per Bundle (Entwicklungsrechner -> VM):

```bash
git bundle create /tmp/nestwerk.bundle main
scp -i ~/.ssh/<SSH-KEY> /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle
ssh -i ~/.ssh/<SSH-KEY> root@<VM-IP> 'cd /opt/nestwerk && deploy/update.sh --bundle /root/nestwerk.bundle'
```

`deploy/update.sh` allein (ohne `--bundle`) nutzt `git pull --ff-only` und braucht ein Remote. `--force` baut auch ohne neuen Commit neu. Das Bundle muss `main` als Fast-Forward des Stands auf der VM enthalten (keine umgeschriebene Historie).

Ablauf: Bundle prüfen und übernehmen, Image `nestwerk:<sha>` bauen, Dienste stoppen, **DB-Backup (`--grund=update`)**, `migrate`, Neustart, Warten auf `healthy`. Schlägt etwas nach dem Stoppen fehl, rollt das Skript selbst zurück (altes Image, bei fehlgeschlagener Migration zusätzlich die DB aus dem Backup; beides am 2026-10-23 getestet). Migrationen sind additiv (expand/contract).

Grenzen: Ein Rollback tauscht nur das **Image**. `compose.yaml`, `deploy/` und der Git-Stand bleiben auf dem neuen Commit. Nach einem fehlgeschlagenen Update also den Fehler beheben und ein **weiteres Commit** ausliefern (kein `git reset` auf der VM). Ist `compose.yaml` selbst das Problem, scheitert auch der Rollback; dann die Datei im Commit korrigieren und erneut updaten. Die Firewall-Datei wird nicht vom Update erneuert, nur von `install.sh`.

## 9. Rollback (manuell)

```bash
deploy/rollback.sh                       # zurück auf das vorherige Image (DB bleibt)
deploy/rollback.sh <sha> --mit-db        # zusätzlich Pre-Update-Backup zurückspielen
```

`--mit-db` verwirft alle Daten seit dem Update-Backup; die bisherige DB bleibt als `nestwerk.sqlite3.vor-restore-<zeit>` im Volume. Vorhandene Images: `docker images nestwerk`.

## 10. Backup und Restore-Übung (< 15 min)

**Was wird gesichert:** Täglich 03:30 (Nachholtermin 13:30) schreibt der Scheduler per `db_sichern` einen konsistenten, komprimierten SQLite-Dump nach `/srv/nestwerk/backup` (`nestwerk-JJJJMMTT-HHMMSS-taeglich.sqlite3.gz`). Aufbewahrung: 14 tägliche, 8 wöchentliche, 12 monatliche (je das neueste einer Periode), dazu die letzten 5 Update-Backups. Einstellbar per `.env`: `NESTWERK_BACKUP_TAEGLICH`, `_WOECHENTLICH`, `_MONATLICH`, `_UPDATE_BEHALTEN`, `_MAX_ALTER_STUNDEN`. **Nicht gesichert:** Nachweis-Fotos (Datenschutz) und Secrets (Abschnitt 11). Ein Nachweis-Text kann bis zum Ablauf der Aufbewahrung im Dump liegen (bewusst akzeptiert).

**Wöchentlicher Test:** `backup_pruefen` (So 04:30) entpackt das neueste Backup in eine Temp-DB, prüft `integrity_check`, Alter (max. 36 h) und vergleicht die Ledger-Zeilen mit der Live-DB. Fehler: Job-Lauf `fehler` plus Push/E-Mail an die Eltern (`system.backup_fehler`).

**Restore-Übung** (vor Go-live und dann halbjährlich):

```bash
cd /opt/nestwerk
docker compose exec scheduler python manage.py db_sichern --grund=manuell   # frischer Stand
docker compose exec scheduler python manage.py backup_pruefen               # Test ohne Eingriff
docker compose stop web worker scheduler
docker compose run --rm --no-deps web python manage.py db_wiederherstellen neuestes
docker compose up -d
curl -s http://<VM-IP>:8000/gesundheit/                                     # 200? (auf der VM)
```

`db_wiederherstellen <datei|neuestes> [--grund=taeglich|update|manuell]` ersetzt die Live-DB; die alte bleibt als `*.vor-restore-<zeit>` erhalten (nach erfolgreicher Übung im Volume löschen). Totalverlust der VM: Proxmox-Backup zurückspielen oder frische VM (Abschnitt 2) und Dump nach `/srv/nestwerk/backup` legen, dann wie oben mit `db_wiederherstellen /backup/<datei>` vor dem ersten Start der Dienste.

Empfehlung (Ebene 3): `/srv/nestwerk/backup` zusätzlich auf ein NAS außerhalb des Proxmox-Hosts kopieren.

## 11. Secrets sichern

Im Volume unter `/data/secrets`: `django_secret_key`, `fernet.key` (verschlüsselt das SMTP-Passwort), `vapid_private.pem` (Push). **Verlust des VAPID-Schlüssels = alle Push-Abos ungültig, Verlust des Fernet-Schlüssels = SMTP-Passwort neu eingeben.** Die DB-Backups enthalten sie bewusst nicht.

```bash
deploy/secrets-sichern.sh /srv/nestwerk/geheimnisse     # AES-256-verschlüsseltes Archiv, Passphrase wird abgefragt
```

Archiv **und** Passphrase getrennt von der VM aufbewahren (Passwortmanager/USB). Nach jeder Änderung der Secrets (selten) wiederholen. Zurückspielen:
`openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in <datei> | docker compose run --rm --no-deps -T web tar -xzf - -C /data`.
Die Domain-/Host-Werte in `.env` sind keine Secrets, aber `NESTWERK_SETUP_TOKEN` nach der Einrichtung entfernen.

## 12. Fehlersuche

| Symptom | Prüfen |
|---|---|
| Seite nicht erreichbar | `docker compose ps`; `curl http://<VM-IP>:8000/gesundheit/`; NPM-Host/-Zertifikat; nftables: `nft list table inet nestwerk_fw` |
| Container startet neu | `docker compose logs --tail=100 web` (bzw. `worker`, `scheduler`) |
| `/gesundheit/` nicht 200 | Antwort lesen: DB lesbar? Migrationen offen? Worker-Herzschlag? Dann `docker compose run --rm web python manage.py migrate` |
| Jobs laufen nicht | `docker compose logs scheduler`; Eltern-Dashboard -> Systemstatus (Job-Läufe); Crontab: `deploy/crontab` |
| Kein Push | Web-App vom Home-Bildschirm geöffnet? Abo in Einstellungen vorhanden? `docker compose logs worker`; ausgehend `*.push.apple.com:443` frei? |
| Keine Backups | `ls -l /srv/nestwerk/backup`; Rechte (UID 1000); `docker compose exec scheduler python manage.py db_sichern` von Hand |
| Port 8000 aus falschem Netz erreichbar | `systemctl status nestwerk-firewall`; `deploy/install.sh` mit richtiger `--npm-ip` erneut ausführen |

Logs rotieren automatisch (10 MB x 3 je Container). Job-Ergebnisse stehen in der Tabelle `JobLauf` (Admin/Systemstatus).

## 13. Bestehende FamKo-Installation umstellen

Nestwerk hieß früher FamKo. Eine laufende Installation braucht **keine** Umbenennung und verliert keine Daten.

**Bleibt automatisch kompatibel**

| Was | Verhalten |
|---|---|
| `.env` mit `FAMKO_*` | Gilt weiter als Fallback; `NESTWERK_*` hat Vorrang, beides darf gemischt vorkommen |
| Compose-Projekt, Volume, Image | `update.sh` erkennt die alte `.env` samt Volume (`famko_famko_data` oder `famko_data`) und trägt ein: `COMPOSE_PROJECT_NAME=famko` (aus dem Volume-Label), `NESTWERK_DATA_VOLUME=<altes Volume>`, `NESTWERK_IMAGE=famko` |
| Image-Tags, Rollback | Weiter `famko:<sha>`; `rollback.sh` und `famko:vorher` funktionieren wie bisher |
| Datenbank | `/data/db/famko.sqlite3` wird weiterverwendet (nur ohne vorhandene `nestwerk.sqlite3`) |
| Backups | Dateien `famko-*.sqlite3.gz` werden erkannt, rotiert und wiederhergestellt; neue heißen `nestwerk-*.sqlite3.gz` |
| Pfade, Benutzer, Firewall | `/opt/famko`, Benutzer `famko`, `/etc/famko`, Dienst `famko-firewall` bleiben; ein erneutes `install.sh` erkennt sie und behält sie |
| App-Labels, Migrationen | Unverändert (kein Migrationseingriff) |

**Einmalig beim ersten Update auf Nestwerk-Stand** (das alte `update.sh` wird beim `git pull` überschrieben, deshalb den Code zuerst von Hand holen und dann das neue Skript starten):

```bash
cd /opt/famko
git fetch /root/nestwerk.bundle main && git merge --ff-only FETCH_HEAD   # oder: git pull --ff-only
deploy/update.sh --force
grep -E '^(COMPOSE_PROJECT_NAME|NESTWERK_DATA_VOLUME|NESTWERK_IMAGE)=' .env   # Kontrolle
```

Erwartete `.env`-Ergänzungen (setzt `update.sh` selbst; zur Not von Hand eintragen, `docker volume ls` zeigt den Volume-Namen):

```
COMPOSE_PROJECT_NAME=famko
NESTWERK_DATA_VOLUME=famko_famko_data
NESTWERK_IMAGE=famko
```

Notfall: Startet die App nach einem Update leer (Assistent erscheint wieder), wurde ein neues Volume `nestwerk_data` angelegt. Die Daten liegen unverändert im alten Volume. `.env` wie oben ergänzen und `docker compose up -d` ausführen.

**Optional und nicht nötig:** Pfade, Volume oder Image manuell umbenennen. Wer es trotzdem will, sichert zuerst die DB (`db_sichern`) und die Secrets (Abschnitt 11) und entfernt danach die drei Zeilen oben erst, wenn das Volume kopiert wurde.
