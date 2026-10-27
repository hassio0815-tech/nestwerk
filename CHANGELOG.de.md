# Changelog

🇬🇧 [English](CHANGELOG.md) · 🇩🇪 **Deutsch**

Die Einträge sind aus der Git-Historie abgeleitet und nach Projektphasen gruppiert. Arbeitspaket-Nummern (AP) stehen in `docs/ARCHITECTURE.md`, Abschnitt 12.

## Umbenennung zu Nestwerk (25.10.2026)

Das Projekt hieß bis hierhin **FamKo** und heißt jetzt **Nestwerk** (Untertitel: „Nestwerk – the family hub for chores, rewards & learning“). Lizenz: AGPL-3.0-or-later.

### Geändert
- Django-Projektpaket `famko/` heißt `nestwerk/`; Docker-, Deploy- und Doku-Dateien, Oberfläche, PWA-Name und Standard-App-Name tragen den neuen Namen
- Umgebungsvariablen: Präfix `NESTWERK_*`. Die alten `FAMKO_*` gelten weiter als Fallback (zentral in `apps/kern/umgebung.py`)
- Neue Installationen nutzen `/opt/nestwerk`, Compose-Projekt `nestwerk`, Volume `nestwerk_data`, Image `nestwerk:<tag>`, Firewall `/etc/nestwerk`, Datenbank `nestwerk.sqlite3`
- `LICENSE` (GNU AGPL-3.0); `docs/LIZENZ-OFFEN.md` entfällt, der Lizenzhinweis steht im README

### Kompatibilität (bestehende FamKo-Installationen)
- `deploy/update.sh` erkennt eine alte `.env` (mit `FAMKO_*`) samt altem Volume und schreibt Projekt-, Volume- und Image-Namen in die `.env`; kein Datenverlust, keine manuelle Umbenennung nötig
- Die vorhandene Datenbankdatei `famko.sqlite3` und Backups `famko-*.sqlite3.gz` werden weiter erkannt; App-Labels und Migrationen sind unverändert
- Details: `docs/RUNBOOK.md`, Abschnitt „Bestehende FamKo-Installation umstellen“

## Phase 3: Feinschliff (25.10.2026)

### Hinzugefügt
- Prognose und Kalibrierungsansicht mit Übernahme per Klick (AP32)
- Ruhmeshalle: Helden auf Sockeln, Widmungen und Abzeichen (P3-A)
- Einheitliche, animierte Pop-ups (Konfetti, Rangaufstieg, Ruhmeshalle) mit Rücksicht auf „reduzierte Bewegung“ (AP33)
- Dokumentation für die Weitergabe: Installation, Benutzerhandbuch, Module erweitern, neutralisierte Beispieldaten

### Geändert
- Ruhmeshalle erst, wenn alle Bauaufträge im aktuellen Thema fertig sind (AP36)
- `deploy/install.sh` verweist zum Schluss auf `docs/INSTALLATION.md` (AP36)
- Abschluss-Review Phase 3: `docs/reviews/REVIEW_PHASE3.md` (AP36)

### Noch offen
- God-Mode-Mod-Sets und weitere Mods, AP34
- Preis und Bauzeit je Mod, Themen an/aus im Eltern-Dashboard (P-15)

## Phase 2: Spielebene (23.10. bis 24.10.2026)

### Hinzugefügt
- Regel-Engine `spielregeln`: Aktivität, Pausen für Kind oder Familie, Wochenauswertung, Serie und Tagesserie (AP20)
- Serienbonus bei der Bestätigung von Aufgaben (AP21)
- Ränge mit Schwellen, aktiven Wochen und Kalibrierungsfaktor (AP22)
- Generische Abzeichen- und Meilenstein-Engine mit Metrik-Registry (AP23)
- Avatar-Generator: deterministische SVG-Blockfiguren, Themen und SVG-Whitelist (AP24)
- 10 Themen mit je 36 Mod-Bauplänen (AP25)
- Mod-Shop mit Kauf über das Ledger, Bauzeit, Ausbaustufe und Themenwechsel mit Warnung (AP26)
- Sondertag: Ansprüche aus Meilensteinen, Grenzen, Wunsch, Begleitung und Annahme (AP27)
- Abzeichen-Grafiken (AP28)
- Familienziel mit Wochenfortschritt, Abstimmung und Großziel (AP29)
- Familien-Ranking mit Held der Woche und umschaltbarem Modus (AP30)
- Datenschutz: Aufbewahrungsfristen für Ereignisse, Zustellungen und Benachrichtigungen (B-15)
- Sondertag-Job in der Crontab, Benachrichtigung „jetzt einlösbar“

### Behoben
- Ruhezeit wird vor jedem Versand erneut geprüft (B-19)
- Späte Bestätigungen zählen in der Woche der Aktivität
- Großziel genau einmal je Folge
- Tablet ohne htmx-eval (CSP), kein Überlauf auf 390 px, Schrift ab 14 px
- Datumsformat ISO bei Pausen

### Review
- Review Phase 2 (AP31): Szenario-Tests über 52 Wochen und drei App-Jahre, Abgleich von DATA_MODEL und ARCHITECTURE mit dem Code (B-22)

## Phase 1: Kern (23.10.2026)

### Hinzugefügt
- Projektgerüst, Einstellungs-Registry, Zeit-Utilities, Audit-Log und Job-Sperren (AP01, AP02)
- Designsystem und Basis-Templates (AP06)
- Transaktionale Outbox für Domain-Ereignisse mit Worker (AP05)
- Benutzer, Eltern-Login, Kinder-PIN mit Rate-Limit und Kiosk-Sitzungen (AP03)
- Unveränderliches Punkte-Ledger mit idempotenter Buchung (AP04)
- Benachrichtigungen: Router, Präferenzen, Ruhezeiten, E-Mail, Pop-up, PWA-Manifest und Web-Push (AP07, AP08)
- Aufgaben: Kategorien, Bibliothek, Wiederholung und Instanz-Erzeugung, Reservierung, Nachweise mit EXIF-Entfernung, Bestätigung und Bonuspunkte, Wochenplaner mit Drag and drop (AP10 bis AP14)
- Belohnungen: Katalog, Einlöseanträge, Taschengeld-Monatslimit (AP15)
- Einrichtungs-Assistent mit Setup-Token (AP16)
- Dashboards für Kinder, Eltern und Tablet, Einstellungs-Editor, Familienverwaltung (AP17)
- Betrieb: Crontab-Scheduler, Datenbank-Backups, Backup-Test, Update und Rollback, Runbook (AP18)

### Behoben und gehärtet
- Schichtenregeln mit import-linter, nur Lesen über selectors (AP19)
- Sicherheit: X-Forwarded-For nur rechtester Eintrag, CSP-Header, Sitzungen bei Passwortwechsel und Gerätewiderruf, enge Dateirechte, Deep-Links nur intern
- Web-Push-Endpunkte auf erlaubte Push-Dienste beschränkt (B-14)
- Nachweis-Fotos nie an eine fremde Meldung, Upload-Grenze
- Eine Schreibsperre für Punkte und Belohnungen (Nebenläufigkeit)
- Healthcheck-Host immer erlaubt
- Installer und Update: Bundle statt Git-Remote, git safe.directory, Egress-Sperre für Container
- Oberfläche: Mobile Wochenplanung, Touch-Ziele, Schriftgrößen
