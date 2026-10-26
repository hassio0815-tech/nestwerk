# Review Phase 3 (AP36)

- **Stand:** 25.10.2026, Basis `9121f4a` (produktiv, Phase 2), geprüft bis `86fea38` (P3-A Ruhmeshalle, AP32 Prognose/Kalibrierung, AP33 Pop-ups, Weitergabe-Doku `ad9598d`), Review-Commits danach.
- **Umfang (kompakt):** Diff `9121f4a..HEAD` (neue Views Ruhmeshalle, Widmung, Prognose/Übernahme; Services `avatar.ruhmeshalle`, `spielregeln.raenge` Kalibrierung, Migrationen avatar 0005/0006, spielregeln 0010/0011; Templates, `nestwerk.js`), offene Punkte aus `nestwerk-followups`, Doku gegen Code.
- **Ergebnis:** 9 Befunde: 0 kritisch, 0 hoch, 2 mittel, 7 niedrig. Behoben: 1 mittlerer, 3 niedrige. Offen: 1 mittlerer (Funktionsumfang AP34, Nutzerentscheidung), 4 niedrige (Begründung je Befund).
- **Migration Phase 2 -> Phase 3:** DB im Stand `9121f4a` mit Demo-Daten -> `migrate` auf HEAD fehlerfrei, `spielregeln_neuberechnen` ohne Abweichung, alle Cron-Jobs zweimal: zweiter Lauf ändert nichts (Abschnitt "Migrationstest").
- **Browser-Prüfung:** `screenshots.py` (72 Seiten), `--nur ruhmeshalle` (22), `prognose_screens.py` (11): **0 Konsolenfehler, 0 CSP-Verstöße, 0 fehlgeschlagene/externe Requests**.
- **Nachweis:** Abschnitt "Nachweis".
- **Deploy:** bereit (kein Befund kritisch/hoch offen); vor dem Update wie gewohnt `update.sh` (sichert vor `migrate`).

---

## Übersicht

| Nr. | Schwere | Feld | Kurz | Status |
|---|---|---|---|---|
| R-01 | mittel | Fachregel/Nebenläufigkeit | Held lässt sich einfrieren, während Bauaufträge im Thema laufen; diese Mods werden danach im alten Thema fertig (zählen nirgends) | behoben |
| R-02 | mittel | Grundregel "alles im Eltern-Dashboard" | P-15: Preis/Bauzeit je Mod, Themen an/aus, SVG-Overrides nur per Code/Daten änderbar (nur Standards und Faktoren im Dashboard) | offen (Umfang AP34, Nutzerentscheidung) |
| R-03 | niedrig | Betrieb/Doku | `deploy/install.sh` verwies zum Schluss nur auf RUNBOOK, nicht auf `docs/INSTALLATION.md` | behoben |
| R-04 | niedrig | Doku | DATA_MODEL ohne `RuhmeshallenEintrag`, `Kalibrierung.faktor_wochen`, Status `eingefroren`; beschrieb ein Modell `Prognose` mit Unique, das es nicht gibt | behoben |
| R-05 | niedrig | Doku | CHANGELOG führte AP33 (Pop-ups) als offen; Ruhmeshallen-Sperre (R-01) in SPEC/Handbuch/ARCHITECTURE ergänzt | behoben |
| R-06 | niedrig | Datenbank | CHECK `spielregeln_kalibrierung_bereich` deckt `faktor_wochen` nicht ab | offen |
| R-07 | niedrig | Datenschutz | Audit der Widmung speichert alten und neuen Text (sonst gilt "Audit ohne Freitext") | offen (bewusst) |
| R-08 | niedrig | Struktur | `sondertag.views.prognose_seite` ohne `require_GET` | offen |
| R-09 | niedrig | Weitergabe | Git-Historie enthält persönliche Daten (IPs, Schlüsselname, Familiendetails, Autor-E-Mail) | offen (Nutzerentscheidung) |

---

## Befunde

### R-01 (mittel) Ruhmeshalle trotz laufender Bauaufträge

- **Beleg:** `apps/avatar/ruhmeshalle.py` (alt): "Laufende Bauaufträge laufen weiter". `mods_fertigstellen` setzt sie später auf `fertig` mit `mod.thema = altes Thema`; die Ausbaustufe zählt nur das aktuelle Thema, der Snapshot ist schon geschrieben. Ergebnis: bezahlter Mod ohne Wirkung (P3-A-Annahme aus `nestwerk-followups`).
- **Korrektur:** Einfrieren gesperrt, solange `im_bau` im aktuellen Thema existiert; Prüfung in derselben Transaktion unter `punkte.schreibsperre` (kein Kauf dazwischen). `Bereitschaft` liefert `ausgebaut`/`bau_laeuft`; die Seite "Meine Ruhmeshalle" zeigt "Warte, bis deine N Bauaufträge fertig sind" statt des Knopfs, der Dienst lehnt mit derselben Meldung ab.
- **Test:** `apps/avatar/tests/test_ruhmeshalle.py::test_gesperrt_solange_bauauftrag_im_thema_laeuft` (Sperre, Meldung auf der Seite, kein Knopf, nach Fertigstellung möglich).

### R-02 (mittel) P-15: nicht alles im Eltern-Dashboard

- **Beleg:** Mod-Preis/Bauzeit je Mod, Themen an/aus und SVG-Overrides haben keine Eltern-Oberfläche (nur Rang-Standards, Faktoren global/je Kind).
- **Bewertung:** Kein Fehler im umgesetzten Code, sondern fehlender Funktionsumfang (AP34). Über die Faktoren lassen sich Preise/Bauzeiten pauschal steuern. Offen bis zur Priorisierung durch den Nutzer.

### R-03 bis R-05 (niedrig) Doku und Installationshinweis

- `install.sh` endet jetzt mit "Nächste Schritte: docs/INSTALLATION.md …; Betrieb: docs/RUNBOOK.md".
- DATA_MODEL: 9.8 `RuhmeshallenEintrag` (aus dem Modell erzeugt), `faktor_wochen`, `eingefroren`, Modellzahl 58 (geprüft per `apps.get_models()`), Unique-Tabelle und ER-Diagramm angepasst.
- Abgleich README, INSTALLATION, BENUTZERHANDBUCH, ARCHITECTURE, SPEC, CHANGELOG: alle genannten `manage.py`-Kommandos und `NESTWERK_*`-Variablen existieren im Code; Dateiverweise gültig (außer bewusste Beispielpfade in MODULE-ERWEITERN).

### R-06 (niedrig) CHECK ohne `faktor_wochen`

- Der Dienst prüft den Bereich (`faktor_lesen`, 0,25–4,00); nur direkte DB-Schreibzugriffe könnten abweichen. Mit der nächsten Schema-Migration ergänzen.

### R-07 (niedrig, bewusst) Widmungstext im Audit

- Die Widmung ist der einzige änderbare Teil eines sonst unveränderlichen Eintrags; ohne Text im Audit wäre eine überschriebene Widmung verloren. Text ≤ 140 Zeichen, von Eltern geschrieben, ohnehin in der Halle sichtbar.

### R-08 (niedrig) `prognose_seite` ohne Methodenfilter

- POST auf die Seite rendert nur (CSRF-geschützt, ohne Wirkung). Kosmetisch.

### R-09 (niedrig) Git-Historie

- Repo-Inhalt ist neutralisiert (`ad9598d`), die Historie nicht. Empfehlung: für die Weitergabe ein frisches Export-Repo mit einem Commit; Arbeits-Repo nicht umschreiben. Lizenz offen (`docs/LIZENZ-OFFEN.md`).

---

## Migrationstest Phase 2 -> Phase 3

1. Worktree auf `9121f4a` (produktiv), Demo-Server mit Einrichtungs-Assistent, `demo_daten.py` und Ranking-Demo (3 Kinder, Aufgaben, Punkte, Avatare, Wochen, Held der Woche).
2. Kopie der DB, `migrate` mit HEAD: `avatar.0005_ruhmeshalle`, `avatar.0006_ruhmeshalle_startwerte`, `spielregeln.0010_abzeichen_ruhmeshalle`, `spielregeln.0011_prognose` fehlerfrei; danach keine offene Migration, `makemigrations --check` ohne Änderung.
3. `spielregeln_neuberechnen`: die einzigen 3 Abweichungen (W42 der Ranking-Demo) bestehen schon im Stand `9121f4a` ohne Migration (Demo-Artefakt: direkt gesäte Woche); `wochen_sicherstellen` bereinigt sie, danach **keine Abweichung**.
4. Alle Cron-Jobs (`aufgaben_erzeugen`, `verfall_pruefen`, `reservierungen_pruefen`, `wochen_sicherstellen`, `familienwoche_sicherstellen`, `mods_fertigstellen`, `sondertag_sicherstellen`, `konten_aufraeumen`, `benachrichtigungen_aufraeumen`, `nachweise_aufraeumen`) zweimal: alle `ok`, zweiter Lauf ohne Änderung, Datenbestand gleich (669 Zeilen ohne Protokoll-Tabellen).

---

## Geprüft ohne Befund (Auszug)

- **AuthZ:** Ruhmeshalle Kind (`nur_kind`, nur eigene Einträge, Dialog nur eigenes Thema), Eltern-Halle und Widmung (`nur_eltern`, Rolle zusätzlich im Service), Prognose/Übernahme (`nur_eltern`, `require_POST`, Kind nur aus `aktive_kinder`, Rolle im Service). Kein `csrf_exempt`; alle neuen Formulare mit `{% csrf_token %}`; kein `|safe`/`mark_safe` neu, Widmung escaped; SVG nur aus dem Renderer (`svg_roh`). `nestwerk.js` ohne `innerHTML`/`eval`.
- **Idempotenz/Nebenläufigkeit:** Einfrieren unter `punkte.schreibsperre` (SQLite IMMEDIATE), `unique(kind, themenstart)`, Doppelklick liefert den bestehenden Eintrag ohne zweite Ereignisse/Audit; veralteter Dialog wird abgelehnt. Kalibrierung übernehmen: `@transaction.atomic` + IMMEDIATE, gleicher Wert = keine Änderung/kein Audit, globale Zeile per Ausdrucks-Unique.
- **Schichten:** `lint-imports` 5 Verträge eingehalten; `sondertag` nutzt nur `spielregeln.services`, `avatar` liest `punkte.selectors`.
- **Grundregel:** neue Einstellungen (`avatar.ruhmeshalle_ausbaustufe`, `spielregeln.prognose_*`) über die Einstellungs-Registry im Eltern-Dashboard änderbar; Faktoren (Schwelle, Wochen, Mods) per Klick mit Audit. Einträge der Halle bewusst unveränderlich (Entscheidung 33), Widmung änderbar.
- **Datenschutz:** Halle zeigt dem Kind nur eigene Helden, Tablet nur die Anzahl; Benutzer werden nie gelöscht (`PROTECT` auf Einträge unkritisch); Prognose wird live berechnet, nicht gespeichert.

---

## Nachweis

- `pytest`: 1616 grün (Phase 2: 1533), 262 s.
- `ruff check .`: grün. `lint-imports`: 5 Verträge eingehalten. `manage.py makemigrations --check`: keine Änderungen.
- Browser: 72 + 22 + 11 Seiten, 0 Konsole/CSP/fehlgeschlagene/externe Requests (Läufe nach `/tmp`, Repo-Screenshots unverändert).
