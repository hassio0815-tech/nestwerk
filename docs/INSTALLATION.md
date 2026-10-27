# Nestwerk installieren (Schritt für Schritt)

🇬🇧 [English](en/INSTALLATION.md) · 🇩🇪 **Deutsch**

Diese Anleitung richtet Nestwerk auf einem eigenen Server im Heimnetz ein. Sie ist für technisch interessierte Eltern mit Grundkenntnissen in Proxmox, Linux und Docker gedacht.

Platzhalter in `<spitzen Klammern>` musst du durch deine Werte ersetzen. Beispiele:

- `<VM-IP>`: feste IP der Nestwerk-VM, z. B. `192.168.1.50`
- `<NPM-IP>`: IP deines Reverse Proxys (z. B. Nginx Proxy Manager), z. B. `192.168.1.10`
- `<DEINE-DOMAIN>`: deine eigene Domain, z. B. `example.org`
- `<HEIMNETZ-CIDR>`: dein Heimnetz, z. B. `192.168.1.0/24`

---

## 0. Überblick

```
Handy/Tablet ──HTTPS──> Reverse Proxy (<NPM-IP>) ──HTTP:8000──> Nestwerk-VM (<VM-IP>)
                                                              (Docker: web, worker, scheduler)
Lokales DNS (AdGuard/Pi-hole): nestwerk.<DEINE-DOMAIN> -> <NPM-IP>
```

- **Nur ein Proxy:** Port 8000 der VM ist nur für den Reverse Proxy offen.
- **Keine Cloud:** Daten, Fotos und Datenbank bleiben auf deinem Server.
- **Keine offenen Ports ins Internet:** Zugriff von unterwegs nur über dein eigenes VPN (z. B. WireGuard oder Tailscale).

---

## 1. Voraussetzungen

- [ ] Proxmox (oder anderer Hypervisor) mit einer **Debian-13-VM**, minimal installiert, mit SSH.
  - Getestet mit: 2 vCPU, 4 GB RAM, 46 GB Speicher.
- [ ] **Feste IP** für die VM (DHCP-Reservierung im Router).
- [ ] Ein **Reverse Proxy** mit HTTPS, z. B. Nginx Proxy Manager (NPM).
- [ ] Eine **Domain**, deren DNS-Zone bei einem Anbieter mit API liegt (für Let's Encrypt per DNS-Challenge).
- [ ] Optional: lokaler DNS-Server (AdGuard Home oder Pi-hole).
- [ ] Optional: ein **E-Mail-Postfach** auf eigener Domain für Benachrichtigungen (SMTP).
- [ ] Optional: iPhone mit iOS 16.4 oder neuer für Push-Nachrichten, Android-Tablet als Flur-Display.

**Wichtig:** Die VM braucht Internetzugang während der Installation (Docker-Repository, Let's Encrypt) und ausgehend Zugriff auf `*.push.apple.com` (Push).

---

## 2. Code auf die VM bringen

Nestwerk hat keine öffentliche Cloud-Abhängigkeit. Du holst den Code aus deinem Git-Repository.

Variante A: Git-Repository (wenn du einen Remote hast):

```bash
apt-get update && apt-get install -y git
git clone <REPO-URL> /opt/nestwerk
cd /opt/nestwerk
```

Variante B: Git-Bundle (ohne Remote, z. B. vom eigenen Laptop):

```bash
# Auf dem Entwicklungsrechner im Repo:
git bundle create /tmp/nestwerk.bundle main
scp /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle

# Auf der VM als root:
apt-get install -y git
git clone -b main /root/nestwerk.bundle /opt/nestwerk
cd /opt/nestwerk
```

Der Installer muss als **root** laufen (auf Debian-Minimalinstallationen ist `sudo` oft nicht vorhanden).

---

## 3. Installer ausführen

Der Installer `deploy/install.sh` ist idempotent. Du darfst ihn mehrfach ausführen.

Zuerst ohne Start, um die `.env` zu prüfen:

```bash
deploy/install.sh --npm-ip <NPM-IP> --domain nestwerk.<DEINE-DOMAIN> --heimnetz <HEIMNETZ-CIDR> --ohne-start
```

Danach mit Start:

```bash
deploy/install.sh --npm-ip <NPM-IP> --domain nestwerk.<DEINE-DOMAIN> --heimnetz <HEIMNETZ-CIDR>
```

| Option | Bedeutung |
|---|---|
| `--npm-ip IP` | **Pflicht.** Einzige Quelle, die Port 8000 erreichen darf (dein Reverse Proxy). |
| `--domain NAME` | z. B. `nestwerk.<DEINE-DOMAIN>`. Setzt Hosts und CSRF in der `.env`. |
| `--bind-ip IP` | LAN-IP der VM für Port 8000. Standard: automatisch erkannt. |
| `--heimnetz CIDR` | Heimnetz, nur als Hinweis in der `.env`. |
| `--egress-erlaubt X` | Private Ziele, die Container erreichen dürfen, z. B. ein SMTP-Relay im LAN. |
| `--ziel PFAD` | Installationsordner. Standard: `/opt/nestwerk`. |
| `--ohne-start` | Nur vorbereiten, nicht bauen und nicht starten. |

Der Installer macht Folgendes:

1. Installiert Docker Engine und das Compose-Plugin aus dem offiziellen Docker-Repository.
2. Legt den Benutzer `nestwerk` an sowie `/srv/nestwerk/backup` (UID 1000) und `/srv/nestwerk/geheimnisse` (Rechte 0700).
3. Erzeugt die `.env` inklusive **Setup-Token**.
4. Richtet die Firewall (nftables) ein: Port 8000 nur von der NPM-IP, und Container dürfen keine privaten Netze erreichen.
5. Baut, migriert und startet Nestwerk.

**Am Ende gibt der Installer das Setup-Token aus.** Es steht auch in `/opt/nestwerk/.env`:

```bash
grep SETUP_TOKEN /opt/nestwerk/.env
```

### 3.1 Die `.env` prüfen

Die Datei liegt unter `/opt/nestwerk/.env`. Wichtige Werte:

- `NESTWERK_ALLOWED_HOSTS`: Django kennt nur exakte Namen oder Suffixe mit führendem Punkt (z. B. `.example.org`), keine Platzhalter wie `nestwerk.*`. Bis die Subdomain steht, die VM-IP eintragen.
- `NESTWERK_CSRF_TRUSTED_ORIGINS`: `https://nestwerk.<DEINE-DOMAIN>`.
- `NESTWERK_BASIS_URL`: `https://nestwerk.<DEINE-DOMAIN>`. Sie steht in den Links der Benachrichtigungen.

Nach jeder Änderung: `cd /opt/nestwerk && docker compose up -d`.

Alle Variablen sind in `.env.example` kommentiert.

### 3.2 Prüfen

Auf der VM:

```bash
curl -s http://<VM-IP>:8000/gesundheit/
```

Die Antwort muss HTTP 200 sein. Vom Laptop aus darf die Adresse **nicht** erreichbar sein, weil Port 8000 nur für den Reverse Proxy offen ist.

**Achtung:** Die VM bekommt ihre IP per DHCP. Trage im Router eine feste Reservierung ein. Ändert sich die IP, stimmt `NESTWERK_BIND_IP` nicht mehr.

---

## 4. Reverse Proxy einrichten

Das Beispiel nutzt den **Nginx Proxy Manager**. Andere Proxys (Traefik, Caddy, nginx) funktionieren nach demselben Prinzip.

### 4.1 Proxy-Host anlegen

1. **Hosts → Proxy Hosts → Add Proxy Host**
2. **Domain Names:** `nestwerk.<DEINE-DOMAIN>`
3. **Scheme:** `http`
4. **Forward Hostname / IP:** `<VM-IP>`
5. **Forward Port:** `8000`
6. Haken setzen:
   - **Block Common Exploits:** an
   - **Websockets Support:** **aus**
   - **Cache Assets:** **aus** (wichtig für `/sw.js` und `/manifest.json`)

### 4.2 Upload-Größe erhöhen

Nachweis-Fotos brauchen mehr Platz als das Standardlimit.

1. Tab **Advanced** des Proxy-Hosts öffnen.
2. Eintragen:

```nginx
client_max_body_size 50m;
```

Die App begrenzt Uploads zusätzlich selbst über die Einstellungen `aufgaben.nachweis_max_upload_mb` und `aufgaben.nachweis_max_anzahl`.

### 4.3 Zugriffsregeln

- **Keine Access List** auf dem Host. `/sw.js` und `/manifest.json` müssen ohne Login und ohne Cache ausgeliefert werden.
- **Kein zweiter Proxy** vor dem Reverse Proxy. Nestwerk wertet `X-Forwarded-For` nur am rechtesten Eintrag aus. Mit einem zusätzlichen Proxy-Hop erhält Nestwerk die falsche Client-Adresse.
- Im Einrichtungs-Assistenten bei **„Vertraute Proxys“** nur die `<NPM-IP>` eintragen.

### 4.4 HTTPS mit Let's Encrypt (DNS-Challenge)

Die DNS-Challenge funktioniert auch, wenn der Name nur im Heimnetz aufgelöst wird. Dein Anbieter muss eine API für TXT-Einträge haben (z. B. Cloudflare).

1. Im DNS-Anbieter einen **API-Token** mit Recht auf die DNS-Zone erzeugen.
2. Im NPM: **SSL Certificates → Add SSL Certificate → Let's Encrypt**.
3. **Domain Names:** `nestwerk.<DEINE-DOMAIN>` (oder `*.<DEINE-DOMAIN>`).
4. **Use a DNS Challenge:** an. Anbieter wählen, API-Token eintragen.
5. Im Proxy-Host im Tab **SSL:** das Zertifikat wählen, **Force SSL** und **HTTP/2** an, **HSTS** an.

### 4.5 Prüfen

```bash
curl -s https://nestwerk.<DEINE-DOMAIN>/gesundheit/
```

Die Antwort muss HTTP 200 sein.

---

## 5. Lokaler DNS-Eintrag (Heimnetz)

Damit Geräte im Heimnetz `nestwerk.<DEINE-DOMAIN>` direkt zum Reverse Proxy auflösen, richtest du einen lokalen DNS-Eintrag ein. Er zeigt auf die **NPM-IP**, nicht auf die VM.

**AdGuard Home:**

1. **Filter → DNS-Umschreibungen** (DNS rewrites)
2. **Domain:** `nestwerk.<DEINE-DOMAIN>`
3. **Antwort:** `<NPM-IP>`

**Pi-hole (v6):**

1. **Settings → Local DNS → DNS Records**
2. **Domain:** `nestwerk.<DEINE-DOMAIN>`
3. **IP-Adresse:** `<NPM-IP>`

Prüfen auf einem Gerät im Heimnetz:

```bash
nslookup nestwerk.<DEINE-DOMAIN>
```

Die Antwort muss `<NPM-IP>` sein.

---

## 6. Einrichtungs-Assistent

1. Im Browser `https://nestwerk.<DEINE-DOMAIN>/einrichtung/` öffnen.
2. **Setup-Token** aus der `.env` eingeben.
3. Die acht Schritte durchgehen:
   1. **Willkommen:** Anzeigename der App
   2. **Eltern:** Namen, E-Mail-Adressen, gemeinsames Familien-Passwort
   3. **Kinder:** Namen und vierstellige PIN je Kind
   4. **E-Mail-Versand:** SMTP-Zugang mit Testmail
   5. **Netzwerk:** Heimnetz und „Vertraute Proxys“ (nur die `<NPM-IP>`)
   6. **Zeit:** Go-live-Datum (Startpunkt des App-Jahres) und Zeitzone (Standard Europe/Berlin)
   7. **Startwerte prüfen:** Ränge, Belohnungen, Aufgabenbibliothek, Familienziel. Alles ist später änderbar.
   8. **Zusammenfassung** und Abschluss
4. Danach das Setup-Token aus der `.env` **entfernen**:

```bash
cd /opt/nestwerk
sed -i '/^NESTWERK_SETUP_TOKEN=/d' .env
docker compose up -d
```

Solange das Token gesetzt ist, ist der Assistent für jedes Gerät im Heimnetz offen. Deshalb nach dem Abschluss entfernen.

---

## 7. Geräte einrichten

### 7.1 iPhone als Web-App (Push)

Voraussetzungen: iOS oder iPadOS 16.4 oder neuer, HTTPS, Web-App auf dem Home-Bildschirm.

1. In **Safari** `https://nestwerk.<DEINE-DOMAIN>` öffnen.
2. **Teilen → Zum Home-Bildschirm.**
3. Die App **über das neue Icon** öffnen, nicht über Safari. Nur so erscheint die Berechtigungsabfrage.
4. Anmelden, dann **Einstellungen → Benachrichtigungen aktivieren** antippen und die System-Abfrage erlauben.
5. **Test-Push** auslösen. Die Nachricht kommt innerhalb weniger Sekunden.

Wenn keine Nachricht kommt:

- Hat die VM ausgehend Zugriff auf `*.push.apple.com:443`?
- Wurde die App vom Home-Bildschirm geöffnet?
- Log prüfen: `docker compose logs worker`

Hinweis: Apple ändert die Web-Push-Voraussetzungen teils mit neuen iOS-Versionen. Bei Problemen die aktuelle Apple-Dokumentation prüfen.

### 7.2 Android-Tablet als Flur-Display (Kiosk)

Empfohlen: **Fully Kiosk Browser** (Android).

1. **Start-URL:** `https://nestwerk.<DEINE-DOMAIN>/`
2. **Bildschirm immer an** aktivieren.
3. **Kiosk-Modus** einschalten.
4. In Nestwerk als Elternteil anmelden: **Eltern → Geräte** und das Tablet als **Tablet/Kiosk** markieren.

Auf dem Kiosk-Tablet läuft die Kinder-Sitzung nach etwa 5 Minuten Inaktivität ab. Die Kinder melden sich mit Avatar und PIN an.

### 7.3 Familien-Smartphone oder Laptop

Im Browser `https://nestwerk.<DEINE-DOMAIN>/` öffnen. Eltern melden sich mit dem gemeinsamen Eltern-Passwort und ihrem Namen an.

---

## 8. Updates

Bei Updates läuft automatisch ein Datenbank-Backup vor der Migration. Schlägt etwas fehl, rollt der Installer das Image zurück.

**Mit Git-Remote:**

```bash
cd /opt/nestwerk
deploy/update.sh
```

**Ohne Remote, per Bundle** (vom Entwicklungsrechner):

```bash
git bundle create /tmp/nestwerk.bundle main
scp /tmp/nestwerk.bundle root@<VM-IP>:/root/nestwerk.bundle
ssh root@<VM-IP> 'cd /opt/nestwerk && deploy/update.sh --bundle /root/nestwerk.bundle'
```

Das Bundle muss `main` als Fast-Forward des Stands auf der VM enthalten. Eine umgeschriebene Historie wird abgelehnt.

Weitere Optionen:

- `deploy/update.sh --force`: baut das Image neu, auch ohne neuen Commit.
- `deploy/rollback.sh`: zurück auf das vorherige Image (die Datenbank bleibt).
- `deploy/rollback.sh <sha> --mit-db`: zusätzlich das Pre-Update-Backup zurückspielen. Dabei gehen alle Daten seit dem Update verloren.

Nach einem fehlgeschlagenen Update: den Fehler beheben und ein **weiteres Commit** ausliefern. Kein `git reset` auf der VM.

---

## 9. Backup und Wiederherstellung

Nestwerk sichert zwei Dinge. Die Proxmox-Sicherung ist die zweite Ebene.

**Ebene 1: Proxmox-VM-Backup** (täglich, einstellbar in Proxmox).

**Ebene 2: Datenbank-Dumps** (automatisch):

- Täglich um 03:30 (Nachholtermin 13:30) ein komprimierter SQLite-Dump nach `/srv/nestwerk/backup`.
- Aufbewahrung: 14 tägliche, 8 wöchentliche, 12 monatliche Dumps, dazu die letzten 5 Update-Backups. Einstellbar in der `.env` (siehe `.env.example`).
- Wöchentlicher Test (So 04:30): `backup_pruefen` prüft das neueste Backup und meldet Fehler an die Eltern.

**Nicht gesichert:** Nachweis-Fotos (Datenschutz) und Geheimnisse (siehe unten).

**Ebene 3 (empfohlen):** `/srv/nestwerk/backup` zusätzlich auf ein NAS außerhalb des Proxmox-Hosts kopieren.

### 9.1 Restore-Übung (vor dem Go-live und danach halbjährlich)

```bash
cd /opt/nestwerk
docker compose exec scheduler python manage.py db_sichern --grund=manuell
docker compose exec scheduler python manage.py backup_pruefen
docker compose stop web worker scheduler
docker compose run --rm --no-deps web python manage.py db_wiederherstellen neuestes
docker compose up -d
curl -s http://<VM-IP>:8000/gesundheit/
```

Die alte Datenbank bleibt als `*.vor-restore-<zeit>` im Volume erhalten. Nach einer erfolgreichen Übung kannst du sie löschen.

### 9.2 Geheimnisse sichern

Im Volume liegen `django_secret_key`, `fernet.key` (verschlüsselt das SMTP-Passwort) und `vapid_private.pem` (Push). **Ohne den VAPID-Schlüssel sind alle Push-Abos ungültig.** Ohne den Fernet-Schlüssel musst du das SMTP-Passwort neu eingeben. Die Datenbank-Dumps enthalten sie bewusst nicht.

```bash
deploy/secrets-sichern.sh /srv/nestwerk/geheimnisse
```

Das Archiv ist mit AES-256 verschlüsselt. Archiv **und** Passphrase getrennt von der VM aufbewahren, z. B. im Passwort-Manager oder auf einem USB-Stick.

---

## 10. Fehlersuche

| Symptom | Prüfen |
|---|---|
| Seite nicht erreichbar | `docker compose ps`; `curl http://<VM-IP>:8000/gesundheit/` auf der VM; Proxy-Host und Zertifikat; `nft list table inet nestwerk_fw` |
| Container startet ständig neu | `docker compose logs --tail=100 web` (bzw. `worker`, `scheduler`) |
| `/gesundheit/` ist nicht 200 | Antwort lesen; Migrationen offen? `docker compose run --rm web python manage.py migrate` |
| Jobs laufen nicht | `docker compose logs scheduler`; Eltern-Dashboard, Systemstatus; Crontab in `deploy/crontab` |
| Kein Push auf dem iPhone | App vom Home-Bildschirm geöffnet? Abo in den Einstellungen vorhanden? `*.push.apple.com:443` von der VM erreichbar? |
| Keine Backups | `ls -l /srv/nestwerk/backup`; Besitzer UID 1000; `docker compose exec scheduler python manage.py db_sichern` von Hand |
| Port 8000 aus falschem Netz erreichbar | `systemctl status nestwerk-firewall`; `deploy/install.sh` mit richtiger `--npm-ip` erneut ausführen |
| Foto-Upload schlägt fehl, Log meldet `/tmp/nginx/body` fehlt | Siehe Abschnitt 10.1 |

### 10.1 NPM: Fehler „/tmp/nginx/body fehlt“

**Symptom:** Nachweis-Uploads schlagen fehl. Das Log des Nginx Proxy Managers meldet, dass das Verzeichnis `/tmp/nginx/body` fehlt.

**Ursache:** Das Verzeichnis liegt in `/tmp`. Es fehlt nach einem Neustart, weil `/tmp` beim Start geleert wird. Das passiert häufig bei NPM in einem LXC-Container.

**Abhilfe:** Einen `tmpfiles.d`-Eintrag anlegen, damit systemd das Verzeichnis bei jedem Start erstellt:

```bash
# Benutzer und Gruppe des NPM-Prozesses ermitteln:
ps -o user=,group= -C nginx | head -1

# Eintrag anlegen (Benutzer und Gruppe anpassen):
cat > /etc/tmpfiles.d/npm-body.conf <<'EOF'
d /tmp/nginx/body 0700 <NPM-BENUTZER> <NPM-GRUPPE> -
EOF

systemd-tmpfiles --create /etc/tmpfiles.d/npm-body.conf
```

Danach den NPM neu starten. Der Eintrag wirkt bei jedem Neustart.

---

## 11. Datenschutz-Hinweise für den Betrieb

- **Alle Daten bleiben auf deinem Server.** Es gibt keine Analyse- oder Tracking-Dienste.
- **Schriften** werden selbst ausgeliefert, nicht von Google Fonts.
- **Fotos** (Nachweise) werden nach der Bestätigung sofort gelöscht. Im Protokoll bleibt nur der Vermerk, wer bestätigt hat.
- **Zugriff** nur aus dem Heimnetz. Von unterwegs nur über dein eigenes VPN.
- **NESTWERK_SETUP_TOKEN** nach der Einrichtung entfernen.

Weitere Hinweise: `docs/RUNBOOK.md` (Betrieb), `docs/SPEC.md` (Produktspezifikation).
