# Review Phase 1 (AP19)

- **Stand:** 23.10.2026, Basis `285a045` (AP01–AP18)
- **Umfang:** `apps/`, `nestwerk/`, `deploy/`, `templates/`, `static/js`, Dockerfile, compose.yaml; gegen SPEC, ARCHITECTURE, DATA_MODEL, research/web-push.md, Entscheidungen 1–29 und die offenen Prüfpunkte aus den AP-Berichten.
- **Docker** ist auf dem Entwicklungsrechner nicht installiert: Betrieb (Dockerfile, compose, Skripte, nftables) nur statisch geprüft.
- **Ergebnis:** 23 Befunde: 1 kritisch, 4 hoch, 6 mittel, 12 niedrig. Behoben: alle kritischen, hohen und mittleren sowie 2 niedrige (B-12, B-13). Offen: 10 niedrige (Begründung je Befund).
- **Nachweis:** `pytest` 933 grün (vorher 905), `ruff check .` grün, `lint-imports` 4 Verträge eingehalten (vorher 1).

Zeilenangaben „alt“ beziehen sich auf `285a045`, sonst auf den Stand nach dem Review.

---

## Übersicht

| Nr. | Schwere | Feld | Kurz | Status |
|---|---|---|---|---|
| B-01 | kritisch | Betrieb | Healthcheck wird mit Domain in `ALLOWED_HOSTS` abgewiesen, Container nie „healthy“ | behoben |
| B-02 | hoch | Sicherheit | `X-Forwarded-For` fälschbar, Rate-Limit des Eltern-Logins umgehbar | behoben |
| B-03 | hoch | Sicherheit | Keine Content-Security-Policy, Inline-Handler auf der Offline-Seite | behoben |
| B-04 | hoch | Datenschutz | Fotos einer zurückgerollten Meldung hängen an der nächsten Meldung (ID-Wiederverwendung) | behoben |
| B-05 | hoch | Sicherheit | Wechsel des Familien-Passworts beendet keine Eltern-Sitzungen | behoben |
| B-06 | mittel | Sicherheit | Gerätewiderruf beendet keine Sitzungen (Kiosk-Flag bleibt) | behoben |
| B-07 | mittel | Sicherheit | Uploads ohne Größengrenze vor dem Lesen (Platte voll) | behoben |
| B-08 | mittel | Sicherheit | Interne Einstellungen (Einrichtung abgeschlossen) im Eltern-Editor | behoben |
| B-09 | mittel | Grundregel | Nachweis-Grenzwerte als Django-Setting/Konstante statt Einstellung | behoben |
| B-10 | mittel | Nebenläufigkeit | Sperrlogik in belohnung von punkte kopiert | behoben |
| B-11 | mittel | Schichten | Fremde `models.py` in oberflaeche/einrichtung/belohnung, Vertrag prüfte das nicht | behoben |
| B-12 | niedrig | Sicherheit | Deep-Link-Prüfung ließ `/\host` durch | behoben |
| B-13 | niedrig | Betrieb | `/data/secrets`, `/data/media/nachweise` mit 755 angelegt | behoben |
| B-14 | niedrig | Sicherheit | Push-Abo akzeptiert jede https-URL (blindes SSRF ins LAN) | behoben (Allowlist-Einstellung, Prüfung bei Anlage und Versand) |
| B-15 | niedrig | Datenschutz | Keine Aufbewahrungsfrist für Ereignis/Zustellung/ungelesene Benachrichtigung/JobLauf | offen |
| B-16 | niedrig | Datenschutz | Proxmox-VM-Backup enthält gerade offene Nachweis-Fotos | akzeptiert (Nutzerentscheidung 23.10.2026) |
| B-17 | niedrig | Korrektheit | Push-Urgency „high“ für Kind-Erinnerungen fehlt | offen |
| B-18 | niedrig | Korrektheit | Melden nach Reservierungsablauf möglich, bis der Job läuft (≤ 5 min) | offen |
| B-19 | niedrig | Korrektheit | Wiederholte Zustellung kann in eine Ruhezeit fallen | offen |
| B-20 | niedrig | Grundregel | Backup-Aufbewahrung über Umgebungsvariablen statt Einstellungen | offen (bewusst) |
| B-21 | niedrig | Sicherheit | Argon2-Prüfung des Eltern-Passworts hält die DB-Schreibsperre | offen |
| B-22 | niedrig | Doku | DATA_MODEL weicht bei Einstellungsnamen/Startwerten vom Code ab | offen |
| B-23 | niedrig | Sicherheit | Einrichtungs-Assistent ohne `NESTWERK_SETUP_TOKEN` für das ganze Heimnetz offen | offen |

---

## Behobene Befunde

### B-01 (kritisch) Healthcheck scheitert an `ALLOWED_HOSTS`

- **Beleg:** `compose.yaml:25` ruft `http://127.0.0.1:8000/gesundheit/` auf. `install.sh:112` und `.env.example:4` setzen `NESTWERK_ALLOWED_HOSTS=<domain>`; `nestwerk/settings/basis.py:39` (alt) übernahm nur diese Liste. `CommonMiddleware` ruft `get_host()` → `DisallowedHost` → 400 → `urlopen` wirft → Container bleibt „unhealthy“.
- **Folge:** `install.sh` (`warte_gesund`) und `update.sh` brechen ab; `update.sh` startet den Rollback, der ebenfalls an `warte_gesund` scheitert.
- **Behebung:** `ALLOWED_HOSTS` = konfigurierte Hosts + `localhost`, `127.0.0.1` (`nestwerk/settings/basis.py`). Unbedenklich, weil Port 8000 per nftables nur vom NPM erreichbar ist.
- **Test:** `tests/test_gesundheit.py::test_healthcheck_host_ist_auch_mit_domain_erlaubt`.
- **Commit:** `a0c4bbf`

### B-02 (hoch) `X-Forwarded-For` fälschbar

- **Beleg:** `apps/konten/netz.py:44-51` (alt) nahm von rechts den ersten Eintrag, der **kein** vertrauter Proxy ist. Startwert `konten.vertraute_proxys` = alle privaten Netze (`apps/konten/einstellungen.py:30`). Heimnetz-Clients sind selbst privat → werden als „Proxy“ übersprungen → der Client-kontrollierte linke Teil zählt.
- **Angriff:** Kind im WLAN schickt `X-Forwarded-For: 10.66.0.<n>` und probiert das Eltern-Passwort beliebig oft (Rate-Limit je IP, `sperre.py:60`).
- **Behebung:** Nur der rechteste Eintrag (vom NPM angehängt) zählt, wenn `REMOTE_ADDR` ein vertrauter Proxy ist. Topologie mit genau einem Proxy-Hop (E20, kein cloudflared). RUNBOOK ergänzt.
- **Tests:** `apps/konten/tests/test_netz.py::test_nur_der_rechteste_eintrag_zaehlt_auch_bei_privaten_adressen`, `::test_eltern_rate_limit_laesst_sich_nicht_per_xff_umgehen`.
- **Commit:** `eb80de7`

### B-03 (hoch) Keine Content-Security-Policy

- **Beleg:** ARCHITECTURE 4.5 verlangt „CSP ohne Inline-Scripts“; kein Header in Code, Settings oder NPM-Hinweisen. `offline.html:22` (alt) mit `onclick`.
- **Behebung:** `nestwerk/sicherheit.py` (Middleware): nur eigene Origin, keine Inline-Skripte/-Styles, `frame-ancestors 'none'`, `object-src 'none'`, `img-src` zusätzlich `data:`/`blob:` (Foto-Vorschau). Offline-Seite: Link statt Inline-Handler, eigene Policy (Inline-Style, kein Skript). htmx ohne eingefügte Indicator-Styles (`basis.html`).
- **Tests:** `tests/test_sicherheit.py` (Header, Offline-Policy, statischer Scan aller Templates auf Inline-Skripte/-Handler/-Styles).
- **Commit:** `eb80de7`

### B-04 (hoch) Nachweis-Fotos landen bei fremder Meldung

- **Beleg:** `apps/aufgaben/ablauf.py:489` (alt) schrieb Fotos mitten in der Transaktion; scheiterte danach etwas (Ereignis, Audit, äußere Transaktion), blieben die Dateien unter `NACHWEIS_DIR/<meldung_id>/`. SQLite (`AUTOINCREMENT`) vergibt die zurückgerollte ID erneut → die nächste Meldung (ggf. anderes Kind) zeigt die alten Fotos Eltern und Kind (`nachweise.dateinamen`), bis der stündliche Aufräum-Job läuft.
- **Behebung:** Fotos werden als **letzter** Schritt geschrieben (nach Ereignis und Audit). Neue Meldungen entfernen zuerst Reste ihrer ID (`nachweise.speichern(..., neu=True)`), auch ohne Fotos und bei Vertrauen.
- **Tests:** `apps/aufgaben/tests/test_nachweise.py::test_fotos_einer_zurueckgerollten_meldung_landen_nie_bei_einer_neuen` (belegt die ID-Wiederverwendung), `::test_fotos_entstehen_erst_wenn_ereignis_und_audit_stehen`.
- **Rest (akzeptiert):** Scheitert eine äußere Transaktion **nach** einer Rückfrage-Antwort, bleiben Fotos derselben Meldung (gleiches Kind) bis zur Entscheidung bzw. bis zum Aufräum-Job liegen.
- **Commit:** `9d5acc3`

### B-05 (hoch) Passwortwechsel beendet keine Eltern-Sitzungen

- **Beleg:** Eltern haben kein eigenes Passwort (`apps/konten/models.py`, `set_unusable_password`); Djangos Sitzungsprüfsumme hängt nur an `Benutzer.password` und ändert sich bei `eltern_passwort_setzen` nicht. Sitzungen auf vertrauten Geräten laufen 90 Tage gleitend.
- **Folge:** Ein verlorenes Handy oder ein Kind mit bekanntem Passwort bleibt angemeldet, egal wie oft das Passwort geändert wird.
- **Behebung:** `Benutzer._get_session_auth_hash` bezieht für Eltern den Hash von `ElternZugang` ein; die ändernde Sitzung wird per `update_session_auth_hash` erneuert (`apps/oberflaeche/views_familie.py`).
- **Test:** `apps/konten/tests/test_login.py::test_passwortwechsel_beendet_andere_eltern_sitzungen`.
- **Commit:** `eb80de7`

### B-06 (mittel) Gerätewiderruf ohne Wirkung auf Sitzungen

- **Beleg:** `apps/konten/sitzung.py:63-65` (alt): Kiosk-Status aus Sitzungs-Flag **oder** Gerät; nach Widerruf blieb die Sitzung (inkl. Flag) bestehen. Prüfpunkt aus AP03.
- **Bewertung:** Das verbliebene Kiosk-Flag selbst ist harmlos (restriktive Richtung). Das eigentliche Problem: Widerruf ist das einzige Mittel gegen ein verlorenes Gerät und wirkte nicht.
- **Behebung:** Sitzungen merken sich das registrierte Gerät (`nestwerk_geraet_id`); fehlt es oder ist es widerrufen, endet die Sitzung (Audit `grund: geraet_widerrufen`). Neuregistrierung im selben Browser übernimmt die Bindung.
- **Tests:** `apps/konten/tests/test_kiosk.py::test_widerruf_des_geraets_beendet_dessen_sitzung` u. a.
- **Commits:** `eb80de7`, `20fb722`

### B-07 (mittel) Uploads ohne Größengrenze

- **Beleg:** Django begrenzt Datei-Uploads nicht (`DATA_UPLOAD_MAX_MEMORY_SIZE` gilt nur für Formularfelder); die CSRF-Prüfung liest den Body vor der View. `nachweise.bild_verarbeiten` prüfte erst danach.
- **Behebung:** `apps/aufgaben/middleware.py` (vor `CsrfViewMiddleware`): `Content-Length` > Anzahl × Größe + 1 MB → 413; HTMX zeigt die Meldung als Toast (`static/js/nestwerk.js`). RUNBOOK: `client_max_body_size` im NPM.
- **Test:** `test_nachweise.py::test_zu_grosse_upload_anfrage_wird_vor_dem_lesen_abgewiesen`.
- **Commit:** `9d5acc3`

### B-08 (mittel) Interne Einstellungen im Editor

- **Beleg:** `allgemein.einrichtung_abgeschlossen`, `einrichtung.schritt`, `einrichtung.smtp_uebersprungen` waren im generischen Editor änderbar. Abschalten öffnete den Assistenten wieder (Schritt 2 setzt das Eltern-Passwort neu).
- **Behebung:** `Definition.intern`; der Editor zeigt und speichert interne Schlüssel nicht.
- **Test:** `apps/oberflaeche/tests/test_einstellungen_editor.py::test_interne_einstellungen_sind_nicht_editierbar`.
- **Commit:** `eb80de7`

### B-09 (mittel) Grundregel: Nachweis-Grenzwerte im Code

- **Beleg:** `nestwerk/settings/basis.py:134` (alt) `NACHWEIS_MAX_BYTES` aus Umgebungsvariable; `apps/aufgaben/nachweise.py:31-32` (alt) `MAX_FOTOS = 3`, `MAX_KANTE = 1600`. DATA_MODEL 15.2 sieht Einstellungen vor.
- **Behebung:** Einstellungen `aufgaben.nachweis_max_upload_mb` (15), `aufgaben.nachweis_max_anzahl` (3), `aufgaben.nachweis_max_kante_px` (1600), Datenmigration `aufgaben/0007`. Im Editor sichtbar.
- **Bewusst Konstanten (technisch):** `MAX_PIXEL` (Schutz vor Dekompressionsbomben), `JPEG_QUALITAET`, Textlängen in `ablauf.py` (DB-/UI-Grenzen), `PASSWORT_MINDESTLAENGE` (Sicherheitsuntergrenze), Backoff/Lease in `versand.py`/`jobs.py`, `VERSUCHE_AUFBEWAHRUNG` (30 Tage laut DATA_MODEL 2.6), Cookie-/Sitzungs-Schreibabstände. Keine davon ist eine Familienregel.
- **Tests:** `test_nachweise.py::test_groesse_und_anzahl_sind_familienwerte`, `::test_kantenlaenge_ist_einstellung`; Editor-Test prüft jede Einstellung.
- **Commits:** `9d5acc3`, `a9b512e`

### B-10 (mittel) Doppelte Sperrlogik

- **Beleg:** `apps/belohnung/services.py:270-277` (alt) war eine Kopie von `apps/punkte/services.py:232` (Prüfpunkt aus AP15).
- **Behebung:** Nur noch `punkte.services.schreibsperre` (öffentlich; belohnung → punkte ist schichtenkonform). Prüft zusätzlich, dass eine Transaktion läuft.
- **Zur IMMEDIATE-Annahme:** `transaction_mode: IMMEDIATE` gilt für **jede äußerste** `atomic()`-Ebene, auch wenn ein Aufrufer sie öffnet. Eine „äußere `atomic()` ohne IMMEDIATE“ gibt es mit dieser Konfiguration nicht; fehlt die Konfiguration, wirft `schreibsperre`. Kein weiterer Befund.
- **Tests:** `apps/punkte/tests/test_schreibsperre.py`, `apps/belohnung/tests/test_schreibsperre.py`; bestehende Paralleltests (echte getrennte Verbindungen) grün.
- **Commit:** `e0d605f`

### B-11 (mittel) Versteckte Kopplungen

- **Beleg:** `apps/oberflaeche/selectors.py:7,11` (alt) `aufgaben.models.AufgabenInstanz`, `kern.models.JobLauf`; `apps/oberflaeche/einstellungen_editor.py:9` `kern.models.Einstellung`; `apps/einrichtung/views.py:268` (alt) `apps.get_model("belohnung"/"aufgaben", ...)`; `apps/belohnung/services.py:23` `punkte.models.Art`. ARCHITECTURE 2.2: „Fremde `models.py` werden nie importiert“. Der Layers-Vertrag erkennt das nicht.
- **Behebung:** Zugriffe über `aufgaben.selectors.zahlen_je_kind/vorlagen`, `kern.jobs.letzter_lauf`, `kern.einstellungen.gespeicherte_werte`, `belohnung.selectors.katalog`, `punkte.services.Art`. Drei neue `forbidden`-Verträge in `pyproject.toml` (Oberfläche und Fach-Module ohne fremde Modelle, `benachrichtigung` ohne `punkte`). Enums wie `konten.Rolle` bleiben als bewusste Ausnahme erlaubt. ARCHITECTURE 2.2 nennt `punkte -> ereignisse` jetzt ausdrücklich (war nur im Vertrag).
- **Nachweis:** `lint-imports`: 4 Verträge eingehalten.
- **Commit:** `721bd18`

### B-12 (niedrig) Deep-Link `/\host`

- **Beleg:** `apps/benachrichtigung/texte.py:159`, `views.py:76-78`, `push.py:111` (alt) prüften nur `//`. Browser behandeln `/\host` wie `//host`. Heute nicht ausnutzbar (Muster aus dem Code, Platzhalter sind IDs), aber Muster sind DB-Werte.
- **Behebung:** Gemeinsame Prüfung `texte.ist_interner_pfad`.
- **Test:** `apps/benachrichtigung/tests/test_texte.py::test_nur_interne_pfade`.
- **Commit:** `bdbcf99`

### B-13 (niedrig) Verzeichnisrechte im Volume

- **Beleg:** `deploy/entrypoint.sh:5-6` (alt): `mkdir` vor `umask 077` → `secrets/` und `media/nachweise/` mit 755 (Dateien selbst 600).
- **Behebung:** `umask` zuerst, `chmod 700` auch für bestehende Volumes.
- **Test:** `tests/test_entrypoint.py`.
- **Commit:** `bdbcf99`

---

## Offene Befunde (mit Begründung)

### B-14 (niedrig) Push-Endpoint ohne Host-Prüfung

- **Beleg:** `apps/benachrichtigung/push.py:57-59` akzeptiert jede `https://`-URL; der Worker sendet dorthin POST-Anfragen.
- **Risiko:** Ein angemeldetes Kind kann den Worker gegen https-Dienste im Heimnetz schicken (blind, Körper verschlüsselt, kein Rückkanal).
- **Status: behoben (23.10.2026).** Einstellung `benachrichtigung.push_erlaubte_hosts` (Liste von Host-Endungen, im Eltern-Editor änderbar; Startwerte `push.apple.com`, `fcm.googleapis.com`, `push.services.mozilla.com`, `notify.windows.com`). `push.endpoint_pruefen` verlangt https, Port 443, Suffix-Treffer auf Label-Grenze und sperrt IP-Literale sowie Hosts mit nicht öffentlicher Auflösung immer. Geprüft beim Anlegen des Abos (400) und vor jedem Versand (Abo wird deaktiviert, dauerhafter Fehler, Audit ohne URL). Rest-Risiko: DNS-Rebinding zwischen Prüfung und Versand; die VM-Egress-Regel bleibt als zweite Schicht empfohlen.
- **Ursprüngliche Begründung:** Eine Allowlist (`*.push.apple.com`, `fcm.googleapis.com`, `updates.push.services.mozilla.com`, `*.notify.windows.com`) könnte künftige Browser ausschließen; besser zusammen mit einer Egress-Regel der VM (nur 443 nach außen) entscheiden. Empfehlung: Allowlist als Einstellung in Phase 2.

### B-15 (niedrig) Aufbewahrungsfristen unvollständig

- **Beleg:** `benachrichtigung.services.aufraeumen` löscht nur **gelesene** Benachrichtigungen; `Ereignis`, `EreignisVerarbeitung`, `JobLauf` (≈ 900 Zeilen/Tag) und Zustellungen ungelesener Benachrichtigungen wachsen unbegrenzt. ARCHITECTURE 6 nennt „alte Zustellungen > 90 Tage“.
- **Inhalt:** keine Nachweise, nur Titel/IDs/Begründungen der Eltern.
- **Warum offen:** neue Aufräumregeln plus Einstellungen sind ein eigenes kleines Paket (kein Fehler im Bestand). Empfehlung: mit AP20 ff. (Ereignisse werden dann für Wochenabschlüsse gebraucht, Frist erst danach festlegen).

### B-16 (niedrig) Nachweis-Fotos im Proxmox-VM-Backup

- **Beleg:** ARCHITECTURE 3.4/9 „Fotos sind nie im Backup“ gilt für `db_sichern`. Das Proxmox-VM-Backup (Ebene 1) sichert das ganze Volume inkl. gerade offener Fotos.
- **Status: akzeptiert (Nutzerentscheidung 23.10.2026).** Ein Unterordner lässt sich im VM-Backup nicht ausnehmen. Wie K16 akzeptiert (Fotos liegen nur bis zur Entscheidung vor).

### B-17 (niedrig) Urgency für Kind-Erinnerungen

- **Beleg:** ARCHITECTURE 5.3 „`Urgency: high` nur für Kind-Erinnerungen“; `push.py:185` setzt `high` nur für Entscheidungen der Eltern.
- **Warum offen:** Funktional unkritisch (Zustellung kommt trotzdem), erst beim iPhone-Test (manuell offen) bewerten.

### B-18 (niedrig) Melden kurz nach Reservierungsablauf

- **Beleg:** `ablauf.erledigt_melden` prüft `status == reserviert`, nicht `reserviert_bis`. Bis `reservierungen_pruefen` läuft (alle 5 min), kann das Kind noch melden.
- **Warum offen:** kinderfreundlich, keine Doppelbuchung möglich (bedingtes Update), SPEC verlangt keine Strafe.

### B-19 (niedrig) Ruhezeit nur beim Routing

- **Beleg:** `router.py:106` bestimmt den Status einmal; eine Push-Zustellung, die nach Fehlern erneut versucht wird (`versand.py:72-76`), kann in eine Ruhezeit fallen.
- **Warum offen:** selten (nur nach Push-Fehlern), Auswirkung gering. Empfehlung: in `versand` vor dem Senden erneut prüfen, wenn Phase 2 die Zustellung anfasst.

### B-20 (niedrig, bewusst) Backup-Aufbewahrung als Umgebungsvariable

- **Beleg:** `nestwerk/settings/basis.py:31-35`, `ereignisse/betrieb.py:22`. ARCHITECTURE 3.4 nennt sie „Einstellung“.
- **Warum bleibt es so:** Backups müssen auch laufen, wenn die Datenbank selbst das Problem ist (`betrieb.lokal_jetzt`). Technischer Betriebswert, keine Familienregel.

### B-21 (niedrig) Argon2 in der Schreibtransaktion

- **Beleg:** `apps/konten/backends.py:54-60`: Passwortprüfung (Argon2, ≈ 0,1–0,3 s, ≈ 100 MB RAM) läuft innerhalb `BEGIN IMMEDIATE`; andere Schreiber warten so lange.
- **Warum offen:** Mit Rate-Limit (10 Versuche) und Heimnetz-Zugang unkritisch; der Umbau (Prüfung außerhalb, Versuch danach buchen) ändert die exakte Zählung. Bei Last-Review (AP36) erneut bewerten.

### B-22 (niedrig) DATA_MODEL weicht vom Code ab

- **Beleg:** DATA_MODEL 15.2 nennt `aufgaben.vorwarnung_eltern_stunden_vorher` (Code: `aufgaben.vorwarnung_stunden_vorher`), `konten.kind_netze_cidr = []` (Code: private Netze), `aufgaben.nachweis_sicherheitsnetz_tage` (Code: stündlicher Job mit 1 h Karenz); `konten.vertraute_proxys` fehlt.
- **Warum offen:** reine Dokumentation; beim nächsten Doku-Durchgang angleichen (Code ist maßgeblich).

### B-23 (niedrig) Assistent ohne Setup-Token

- **Beleg:** `apps/einrichtung/zustand.py:57-60`: Ohne `NESTWERK_SETUP_TOKEN` ist der Assistent bis zum Abschluss für jedes Gerät im Heimnetz offen (inkl. Eltern-Passwort setzen).
- **Warum offen:** `install.sh:115-118` erzeugt das Token immer; Risiko nur bei manueller Installation. RUNBOOK nennt das Token. Kein Code-Änderungsbedarf.

---

## Geprüft ohne Befund (Auszug)

- **AuthZ je View:** alle Eltern-Views mit `nur_eltern`, Kind-Views mit `nur_kind` + Eigentumsprüfung (`kind_darf_sehen`, `get_object_or_404(..., kind=kind)`), Nachweis-Auslieferung nur Eltern bzw. eigenes Kind bei offener Meldung; Präferenzen nur eigene oder die eines Kindes. Kein `csrf_exempt`; HTMX sendet das Token per `hx-headers`.
- **Rate-Limits:** Kind je Kind mit Verdopplung (Zähler unter `select_for_update`/IMMEDIATE), Eltern je IP (mit B-02 jetzt fälschungssicher). Keine Zeitunterschiede, die etwas verraten (Elternliste ist ohnehin sichtbar).
- **Open Redirects:** `next=` über `url_has_allowed_host_and_scheme`; Deep-Links/Push siehe B-12.
- **Uploads:** Pillow-Prüfung ohne Dateiendung/MIME, Pixel-Grenze vor dem Dekodieren, Neu-Kodierung (EXIF/GPS, angehängte Inhalte weg), zufällige Namen, Pfad nur per Regex + kein Symlink, Rechte 600/700, `no-store`.
- **Secrets:** Fernet-/VAPID-Dateien 0600, SMTP-Passwort nur verschlüsselt, aus Fehlertexten entfernt, nie im Audit (Schlüsselfilter in `kern.audit`), nie in Templates.
- **Templates/SQL:** kein `|safe`/`mark_safe`, kein Roh-SQL mit Nutzereingaben; Formulare ohne Status-/Besitzer-Felder.
- **Idempotenz:** Buchungen mit Schlüssel + Unique, Statuswechsel als bedingte Updates, Ereignisse mit Schlüssel, Worker: Statuswechsel und Handler in einer Transaktion (genau einmal); Versand bewusst mindestens einmal (Lease). Jobs mit Sperre und Catch-up; keine Jobs zwischen 02 und 03 Uhr.
- **Datenschutz:** Ereignis-/Audit-Daten nur IDs, Titel, Zähler (`mit_text`, `fotos`); Nachweis-Texte beim Abschluss geleert, Fotos per `on_commit` gelöscht, Sicherheitsnetz-Job stündlich; `db_sichern` ohne Medien und Secrets.
- **Fachregeln (Stichproben):** Freigabearten (Vertrauen sofort + Korrektur per Gegenbuchung, Nachweis verlangt Text oder Foto), Sonderpunkte (einmal, Begründung, Deckel aufgerundet, abschaltbar), K11 (Frist ab Zuteilung), Verfall mit Vorwarnung genau einmal, Taschengeld-Limit je Kalendermonat inkl. offener Anträge, Präferenz × Kanal × Ruhezeit (über Mitternacht, E-Mail optional, K7).
- **Betrieb (statisch):** `update.sh` sichert vor `migrate` mit gestoppten Diensten, Rollback mit DB nur nach Migration; nftables-Regeln in eigener Tabelle vor Docker (input + forward per `ct original proto-dst`); supercronic per Prüfsumme; Healthcheck prüft DB und Migrationen (B-01 behoben).

## Für Tests auf der VM (nicht hier prüfbar)

- `docker compose build/up`, `install.sh`, `update.sh` inkl. erzwungenem Rollback, nftables unter Docker-DNAT, NPM mit `client_max_body_size`, CSP im echten Browser (Konsole ohne Verstöße auf allen Seiten, Tablet-WebView), iPhone-Push.
