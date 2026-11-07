# Changelog

🇬🇧 [English](CHANGELOG.md) · 🇩🇪 **Deutsch**

Die Einträge sind aus der Git-Historie abgeleitet und nach Projektphasen gruppiert. Arbeitspaket-Nummern (AP) stehen in `docs/ARCHITECTURE.md`, Abschnitt 12.

## Entlastung der Eltern, Etappe 13 (07.11.2026)

### Hinzugefügt
- **Ausnahme-Meldungen an die Eltern (Push):** Material wartet auf Freigabe (einmal je Stand, der Link wählt die Einträge des Kindes vor), ein Kind hat 3 Tage nicht geübt (nie in Ferien oder Pause, höchstens einmal pro Woche), Fehlerhäufung bei einer Rechenart mit passender Erklärkarte (einmal pro Woche), Prüfung in höchstens 3 Tagen bei weniger als 50 % des Plans (einmal je Prüfung). Tagesjob `lernen_eltern_hinweise`; jedes Ereignis entsteht je Zeitraum nur einmal.
- **Tutor-Markierungen sofort:** Ein Rollenwechsel-Versuch oder eine zurückgehaltene Antwort (Lösung vermutet) wird sofort gemeldet, einmal je Gespräch und Art. Einfache Lösungsbitten werden nicht gepusht.
- **Wochen-Digest:** eine Nachricht pro Woche (Grundeinstellung Sonntag 18:00, Tag und Uhrzeit einstellbar, Push; Mail kann jedes Elternteil zuschalten), höchstens 8 Zeilen, je Kind geübte Tage und ein Vorschlag, offene Freigaben und Prüfungen. Kein Vergleich zwischen Kindern, keine Rangfolge. Job `lernen_digest`.
- **Badge und Links:** Die Lern-Kachel der Eltern zeigt, wie viel Material auf Freigabe wartet, und führt zur Liste.
- **Eigene Einstellungsseite** für Lernen: Tagesziel, Punkte, Ferien, Titel, Tutor, neue Vokabeln pro Tag, Denkpause, Meldungen an die Eltern und die Liste der Rechenarten.

## Wiederholung und Mischung, Etappe 12 (07.11.2026)

### Hinzugefügt
- **FSRS-Planung:** Jede Übungsfrage hat jetzt Stabilität und Schwierigkeit (Bibliothek `fsrs`, gepinnt, MIT, Standardparameter, kein Training). Antworten werden bewertet als Again (noch nicht), Hard (richtig mit Hilfe ab Stufe 3), Good, Easy (richtig ohne Hilfe und schneller als der Median des Kindes). Ziel-Behaltensquote 90 %, größter Abstand 60 Tage, kein Zufall, eine falsche Antwort kommt morgen wieder. Die Leitner-Boxen bleiben als Fallback-Einstellung (`lernen.wiederholung_algorithmus`) und greifen automatisch, wenn die Bibliothek fehlt. Bestehende Stände starten aus ihrer Box.
- **Neu-Limit für Vokabeln:** 3 / 5 / 7 neue Wörter pro Tag (bis Klasse 5 / Klasse 6-7 / ab Klasse 8, Klasse unbekannt: 3), je Kind einstellbar.
- **Mischung (Interleaving):** Bei „alles gemischt“ stammen mindestens 30 % der Mathe-Aufgaben einer Runde aus früheren Rechenarten (Einstellung).
- **Fehlerart steuert die Auswahl:** Rechenarten mit mindestens drei erkannten Rechenfehlern in 14 Tagen kommen öfter dran (Formfehler zählen nicht).

### Geändert
- **Prüfungsplaner** nutzt für offene Wiederholungen die echte Fälligkeit aus dem Lernstand und für geplante den FSRS-Abstandsverlauf (statt des Box-Rasters).

## Lern-Fundament, Etappe 11 (07.11.2026)

### Hinzugefügt
- **Historie bleibt:** Jede Übungskarte hat jetzt eine stabile Kennung (`Karte`: Kind, Fach, Schlüssel). Versuche behalten Karte, Thema, Tage seit dem vorigen Versuch und den geplanten Termin. Das Aufräumen erzeugter Mathe-Aufgaben löscht keine Versuche mehr, die Historie kann über 60 Tage hinaus wachsen. Eine Datenmigration füllt Bestandsdaten.
- **Letzte Rückschau sichtbar:** Die Startseite zeigt, was beim letzten Mal geholfen hat und was schwer war. Eltern sehen die letzten drei Rückschauen im Wochenbild, das Kind wird darauf hingewiesen.
- **Letzte Auswahl vorbelegt:** Die Startseite merkt sich Fach, Thema, Vorhaben, Strategie, Erwartung und Anstrengung der letzten Sitzung.

### Geändert
- **Hilfe zählt:** Eine richtige Antwort mit Hilfestufe 3 oder höher rückt die Karte nicht mehr vor (sie bleibt in ihrer Box). Gilt ab jetzt, nicht rückwirkend.
- **„Zu leicht / zu schwer“ wirkt:** Die Angabe aus der letzten Rückschau verschiebt die erste Aufgabe jeder Rechenart in der nächsten Sitzung um eine Stufe, im erlaubten Bereich.

## Lernmodul (03.11.2026)

### Hinzugefügt
- **Lernen (`lernen`):** neues Modul für Kinder und Eltern. Alles ist freiwillig, und im Repository liegen keine privaten Daten (Startdaten sind generisch).
- **Üben:** Vokabeln und Fragen mit Wiederholung im Abstand (Boxen), Vorhaben und Strategie vorher, zwei Rückschau-Fragen nachher, „noch nicht“ statt „falsch“, Frust-Erkennung, die die Stufe senkt und eine Pause vorschlägt. Hilfen kosten nie Punkte.
- **Tagesziel und Serie:** Schon ein kleiner Mindesttag zählt, das Ziel passt sich sanft an die letzten zwei Wochen an, die Serie zählt in Wochen. Die Eltern tragen Schontage ein (Krankheit, Ferien); eine gerissene Serie nimmt nie Punkte weg.
- **Material hochladen:** Kinder legen ein Foto oder Dokument in ihre eigene Lernmappe. Fragen daraus warten auf die Freigabe der Eltern, solange diese sie nicht pro Kind sofort erlauben. Zweiter Eingang: Dateien im Ordner `inbox`, z. B. auf einem NAS. Speicher: Docker-Volume oder eingehängter Ordner.
- **Prüfungsvorbereitung:** Plan rückwärts vom Termin mit kleinen Portionen und Puffertagen, Realitätscheck mit Vorschlägen statt eines Plans, der nicht passt, und Probe-Prüfung.
- **Optionale KI mit eigenem Anbieter:** eigener Server mit OpenAI-kompatibler Schnittstelle (z. B. Ollama), Anthropic oder OpenAI mit eigenem Schlüssel. **Die KI ist standardmäßig aus.** Cloud-Anbieter brauchen eine ausdrückliche Einwilligung, Schlüssel liegen verschlüsselt, und eine Warteschlange arbeitet KI-Aufträge nacheinander mit Wiederholungen ab.
- **Tutor:** erklärt und hilft mit einer Leiter von Hilfestufen, löst aber keine Hausaufgaben. **Standardmäßig aus**, von den Eltern für die ganze Familie schaltbar, mit Protokoll. Die Prüfung auf verratene Lösungen ist eine Heuristik, keine Garantie.
- **Übungswoche und Titel:** Beteiligung statt Menge. Die Wochen-Titel (Übungsmeister, Aufsteiger, Durchbeißer, Entdecker) sind nur eine Anzeige, geben keine Punkte und sind abschaltbar. Die Eltern bekommen pro Kind ein Wochenbild mit Vorschlägen, ohne Noten und ohne Geschwistervergleich.
- **Einrichtungs-Assistent:** vier optionale Schritte „Lernen“ (Grundwerte, Speicher, Kinder, KI). Die neue Registry-Erweiterung `EinrichtungsSchritt` in `kern` lässt Module überspringbare Schritte ergänzen.
- **Eltern-Seite „Kinder und Leistungsstufen“:** Klassenstufe, Schulform, Leistungsstufe je Fach und die Freigabe von Upload-Fragen jederzeit ändern, mit denselben Services wie der Assistent. **Neues Schuljahr** hebt nach einer Bestätigung alle eingetragenen Klassenstufen um 1 an (bis 13); Lernstand wird nie gelöscht.
- **Mathe-Generator:** Mathe-Aufgaben entstehen lokal ohne KI (Zufallszahlen, immer berechnete Lösung) für die Klassen 3, 6 und 8: Grundrechenarten, Brüche, Dezimalzahlen, Prozent, Größen, Terme und Gleichungen, Dreisatz, Potenzen und Wurzeln. Die Schwierigkeit folgt Leistungsstufe, Intensität und den letzten Antworten (Ziel 70 bis 85 % richtig); fällige Wiederholungen kommen als neue Aufgabe der gleichen Art. Antworten werden großzügig gelesen (Komma oder Punkt, Brüche, gemischte Zahlen, Rest, `x = 5`, Einheiten); die Eltern schalten Rechenarten in den Einstellungen an oder aus.
- **Mathe-Hilfe (lokal, ohne KI):** Hilfeleiter mit fünf Stufen pro Rechenart (Nachfragen, Denkanstoß, ähnliches Beispiel mit anderen Zahlen, Rechen-Tipp, Lösungsgerüst mit Strichen statt Ergebnissen), jede Stufe nur auf Wunsch des Kindes, ohne Punktabzug. Die Lösung der echten Aufgabe steht nie in der Hilfe (Eigenschaftstest über alle Rechenarten). **Rechen-Tipps:** Erklärkarten je Rechenart in drei Sprachstufen, aufklappbar beim Üben und als eigener Bereich, auch für Eltern. **Fehleranalyse:** erkennt typische Rechenfehler (zum Beispiel vergessener Übertrag, Nenner mitgerechnet, Komma verrutscht, Punkt vor Strich), gibt einen Hinweis ohne Lösung und einen zweiten Versuch; das Wochenbild nennt die häufigsten Fehlerarten. Lokale Textaufgaben-Vorlagen (Anteil einstellbar, Standard 0).
- **Optionale KI für Mathe (aus, nur Opt-in):** Textaufgaben formulieren (nur mit Schalter und zugeordnetem Anbieter, im Hintergrund, Ausgabe streng geprüft, sonst lokale Vorlage) und „Erkläre es anders“ (nur mit Tutor, Tutor-Limits, Prüfung gegen die Lösung). Zahlen und Lösung kommen immer vom Generator.
- Hintergrundjobs `ki_auftraege_verarbeiten`, `lernen_inbox_scannen` und `tutor_aufraeumen` in `deploy/crontab`.
- Dokumentation: Benutzerhandbuch Kapitel „Lernen“, Installationsschritte für Speicher, KI-Anbieter und Jobs, Architektur Abschnitt 14, Datenmodell Abschnitt 16, Abschnitt 5a in „Ein neues Modul anlegen“.

### Hinweise
- Die KI-Adapter sind gegen einen Fake-Transport getestet. Das Modul ist **nicht** mit einer echten KI (Ollama, Anthropic, OpenAI) und nicht im Browser getestet.
- Uploads begrenzt die vorhandene Middleware `UploadGrenze` aus `aufgaben` (bei Standardwerten rund 46 MB je Anfrage).
## Bibliothek wird zu Schnell-Knöpfen (07.11.2026)

### Geändert
- Die Aufgaben-Bibliothek (Vorlagen-Oberfläche) entfällt; jeder Eintrag ist jetzt ein Schnell-Knopf. Die alte Adresse `/eltern/bibliothek/` leitet auf die neue Seite „Schnell-Knöpfe“ um. Das Modell „Vorlage“ bleibt als Historie
- Eltern tippen einen Knopf an und wählen im Auswahlfenster: „Einer für alle“ (alle Kinder werden benachrichtigt), „Jedes Kind“ (eigene reservierte Aufgabe je Kind, Kinder mit laufender Aufgabe werden übersprungen) oder „Bestimmtes Kind“; „Los“ bestätigt
- Neues Feld „Standard beim Drücken“ je Knopf (vorbelegt im Fenster). Kinder- und Tablet-Knöpfe bleiben wie bisher
- Startwerte: aus jeder aktiven Vorlage entsteht ein Knopf (Datenmigration plus stündlicher Job). Neu: „Zimmer saugen“ (15 P), „Waschmaschine ausräumen“ (10 P); „Zimmer gründlich“ heißt „Zimmer gründlich reinigen und aufräumen“ (50 P)
- Kinder-Seite: Knopf-Kachel und Aufgabenliste aktualisieren sich gemeinsam, der Hinweis erscheint nur einmal

### Behoben
- Ungültige Kind-Angabe beim Knopfdruck ergibt einen Hinweis statt Fehler 500; Kinder können keinen fremd zugewiesenen Knopf mehr melden
- „Aufgabe je Kind aufteilen“: laufende und erledigte Instanzen folgen ihrem Kind; nur aktive Aufgaben; Befehl mit `--dry-run`, sammelt Fehler je ID
- Doppel-Schutz beim Anlegen (gleicher Titel, Wiederholung und Zuweisung) mit Häkchen „trotzdem anlegen“; „Für jedes Kind“ ohne aktive Kinder zeigt einen Hinweis
- Hygiene: `.gitignore` und `.dockerignore` (Backups, Wheels, `.env.*`, Übergaben)

## Anerkennung, Meine Einstellungen und Moods (02.11.2026)

### Hinzugefügt
- **Anerkennung (Eltern):** Punkte ohne Aufgabe schenken. Neue Buchungsart „Anerkennung“ (1 Punkt = 1 Guthaben und 1 XP), Bemerkung Pflicht, nur Eltern. Je Vergabe 1 bis 25 Punkte, je Kind höchstens 50 Punkte pro Woche (Montag bis Sonntag); beide Grenzen sind Elterneinstellungen (`aufgaben.anerkennung_max_punkte`, `aufgaben.anerkennung_woche_max`). Das Kind bekommt eine Push-Nachricht, die Punkte zählen für XP und Familienziel, ein Storno gibt den Wochenplatz wieder frei
- **Meine Einstellungen (Kinder):** Zahnrad in der Kopfleiste. Name (eindeutig, Groß-/Kleinschreibung egal), optionaler Spitzname (erscheint in Gruß und Kacheln), Code ändern (alter Code Pflicht, neuer Code zweimal; Fehlversuche zählen und sperren wie bei der Anmeldung)
- **Moods:** Katalog mit 50 kindgerechten Moods (Meme, Filme, müde, gut drauf, grummelig, ruhig) plus „Kein Mood“. Der gewählte Mood steht als kleine Zeile unter dem Namen auf der Startseite und im Kinder-Dashboard
- **Mood-Vorschläge:** Kinder schlagen neue Moods vor (höchstens 40 Zeichen, höchstens 3 offene). Eltern sehen Zähler und Liste unter „Moods“, lassen zu oder lehnen ab, blenden Katalog-Moods aus und ergänzen eigene. Zugelassene Moods gelten für alle Kinder. Push an die Eltern bei neuem Vorschlag, an das Kind bei der Entscheidung
- Kinder-Dashboard: „Letzte Punkte“ (Punkteverlauf mit Anerkennung und Bemerkung)

### Geändert
- Eltern setzen den Code eines Kindes jederzeit neu (Bereich Familie); neu mit Tests abgesichert

## Schnell-Knöpfe (30.10.2026)

### Hinzugefügt
- Schnell-Knöpfe: Aufgaben „bei Bedarf“ (z. B. Restmüll), die schlafen, bis jemand den Knopf drückt; ein Druck erzeugt genau eine offene Aufgabe
- Zwei Modi: „Ich mach's“ (für das Kind reserviert) und „Nur melden“ (offen für alle, Mitteilung an die Kinder)
- Kacheln für Eltern, Kinder und das Flur-Tablet (dort ohne PIN, nur auf dem registrierten Kiosk-Gerät)
- Aufgabenformular: Wiederholung „Bei Bedarf“, Emoji und „Wer darf drücken?“
- Bibliotheksvorlagen Restmüll, Biomüll und Altglas (5 Punkte)

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
