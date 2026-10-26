# Review Phase 2 (AP31)

- **Stand:** 24.10.2026, Basis `684373a` (AP20–AP30, AP27), Review-Commits `db1d4b0` … `a0ae3b7`
- **Umfang:** `apps/spielregeln`, `apps/avatar`, `apps/familienziel`, `apps/sondertag`, Ranking in `apps/oberflaeche`, Phase-2-Anteile in `aufgaben`, `benachrichtigung`, `ereignisse`, `kern`, Templates/CSS/JS, `deploy/crontab`; gegen SPEC, ARCHITECTURE (7 komplett), DATA_MODEL, Entscheidungen 1–32, offene Punkte aus `nestwerk-followups` und REVIEW_PHASE1 (B-15, B-19, B-22).
- **Ergebnis:** 18 Befunde: 0 kritisch, 1 hoch, 6 mittel, 11 niedrig. Behoben: der hohe, 5 von 6 mittleren, 7 niedrige. Offen: 1 mittlerer (Nutzerentscheidung Kalibrierung), 4 niedrige (Begründung je Befund).
- **Szenario:** 52 Wochen mit drei Kindern und drei App-Jahre mit einem Kind, alle Invarianten grün; die Startwerte (E14) treffen das Planungsziel "~2 Sondertage je Jahr" (Tabelle unten).
- **Migration Phase 1 -> Phase 2:** DB im Stand `a2df279` (produktiv) mit Beispieldaten erzeugt und auf den aktuellen Stand migriert: fehlerfrei, Backfill der Aktivitäten vollständig (32/32, 1 Storno), alle Jobs laufen doppelt ohne Änderung (Abschnitt "Migrationstest").
- **Browser-Prüfung:** `tools/oberflaeche/screenshots.py` (72 Seiten inkl. Phase 2 und Ranking) und `sondertag_screens.py` (10 Seiten): **0 CSP-Verstöße, 0 Konsolenfehler, 0 fehlgeschlagene/externe Requests**, kein Überlauf auf 390 px, keine Texte unter 14 px. Screenshots selbst angesehen (`docs/screenshots/phase2/`).
- **Nachweis:** `pytest` siehe Abschnitt "Nachweis", `ruff check .` grün, `lint-imports` 5 Verträge eingehalten (vorher 4).

---

## Übersicht

| Nr. | Schwere | Feld | Kurz | Status |
|---|---|---|---|---|
| P-01 | hoch | Sicherheit/Betrieb | Tablet-Polling nutzt htmx-Trigger-Filter (eval) -> CSP blockiert, Tablet aktualisiert sich nicht | behoben |
| P-02 | mittel | Korrektheit | Späte Bestätigung: Aktivität in der neuen Woche, Punkte in der schon abgeschlossenen (Familienziel/Held verlieren sie) | behoben |
| P-03 | mittel | Betrieb | `sondertag_sicherstellen` nicht in der Crontab, ohne Job-Sperre; keine Meldung, wenn ein wartender Sondertag einlösbar wird | behoben |
| P-04 | mittel | Datenschutz | B-15: keine Aufbewahrung für Ereignisse (inkl. Wunschtexte), Zustellungen, ungelesene Benachrichtigungen, Job-Läufe | behoben |
| P-05 | mittel | Korrektheit | Großziel aus der Historie: gesenkte Serienlänge erzeugt rückwirkend mehrere Großziele (Pop-up-/Push-Flut); Catch-up nach verfehlter Woche verliert eine geschaffte Folge | behoben |
| P-06 | mittel | Schichten | `avatar` importiert `spielregeln.raenge` direkt (an `selectors`/`services` vorbei), kein Vertrag dagegen | behoben |
| P-07 | mittel | Fachregel | XP-Schwellen sind bei 150–200 P/Woche nie bindend: Tempo nur über Mindest-Aktivwochen, Schwellen-Kalibrierung (K3/AP32) wirkt dann nicht | offen (Nutzerentscheidung) |
| P-08 | niedrig | Sicherheit/Struktur | SVG-Whitelist in `apps/avatar`, viewBox fest 32 x 48, Abzeichen-Test mit viewBox-Trick | behoben |
| P-09 | niedrig | Oberfläche | Überlauf auf 390 px (Tablet 419 px, Eltern-Mods 678 px), Ranking-Texte 12–13,6 px | behoben |
| P-10 | niedrig | Korrektheit | B-19: Wiederholte Zustellung konnte in die Ruhezeit fallen | behoben |
| P-11 | niedrig | Korrektheit | Familienwoche schließt in UTC + Puffer, Kinder-Wochen in lokaler Wanduhr (1 h Versatz bei großem Puffer über Zeitumstellung) | behoben |
| P-12 | niedrig | Oberfläche | Pausen-Formular: `type=date` bekam `24.10.2026` (Konsolenwarnung, leeres Feld) | behoben |
| P-13 | niedrig | Doku | B-22: DATA_MODEL/ARCHITECTURE weichen vom Code ab (Einstellungen, Ereignisse, Modelle, Jobs) | behoben |
| P-14 | niedrig | Lint | ruff E501 in `apps/avatar/einstellungen.py` | erledigt (schon im Bestand behoben, geprüft) |
| P-15 | niedrig | Grundregel | Einzelpreise/Bauzeiten je Mod, Themen an/aus und Mod-Overrides nicht im Eltern-Dashboard (nur Daten) | offen |
| P-16 | niedrig | Fachregel | Übergang Legendary -> God Mode: im 3. App-Jahr nur 1 Sondertag (50 Wochen Lücke) | offen (Hinweis Kalibrierung) |
| P-17 | niedrig | Korrektheit | Korrektur bucht am Tag der Korrektur (XP-Minus in der laufenden Woche, nicht in der ursprünglichen) | offen (bewusst, K2) |
| P-18 | niedrig | Sicherheit | Avatar-SVG unter `/avatar/<sha256>.svg` ohne Anmeldung abrufbar | akzeptiert |

Weiter offen aus Phase 1 (unverändert bewertet): B-17 (Urgency), B-18, B-20 (bewusst), B-21 (AP36), B-23.

---

## Behobene Befunde

### P-01 (hoch) Tablet-Polling braucht eval, CSP blockiert

- **Beleg:** `apps/oberflaeche/templates/oberflaeche/tablet.html:13` (alt) `hx-trigger="every Ns [document.visibilityState === 'visible']"`. htmx wertet Trigger-Filter per `Function()` aus; die CSP (`script-src 'self'`, kein `unsafe-eval`) blockiert das. Screenshot-Lauf AP29: 2 CSP-Fehler je Tablet-Seite (`EvalError ... htmx.min.js`).
- **Folge:** Live-Aktualisierung der Flur-Tablet-Startseite (Familienziel-Leiste, Ranking, offene Aufgaben) läuft nicht; sichtbar erst nach dem 6-h-Neuladen.
- **Behebung:** Filter entfernt; Polling-Elemente tragen `data-nur-sichtbar`, `static/js/nestwerk.js` bricht deren Requests bei verstecktem Tab ab (`htmx:beforeRequest`). htmx-Config `allowEval: false`, `allowScriptTags: false`. Auch Benachrichtigungsliste/-zähler und Pop-up-Abruf pausieren jetzt verdeckt (ARCHITECTURE 5.4).
- **Tests:** `tests/test_sicherheit.py::test_templates_ohne_htmx_eval` (Trigger-Filter, `hx-on`, `hx-vars`, `js:`), `::test_htmx_eval_ist_abgeschaltet_und_csp_ohne_unsafe_eval`, `::test_polling_pausiert_per_skript_statt_filter`; Browser-Lauf 0 CSP-Verstöße.
- **Commit:** `db1d4b0`

### P-02 (mittel) Späte Bestätigung: Punkte und Aktivität in verschiedenen Wochen

- **Beleg:** `aufgaben/ablauf.py` buchte Basis/Sonderpunkte mit `bezugsdatum = Meldedatum`, `spielregeln.serienbonus_buchen` ebenso; die Aktivität nutzt seit AP20 das wirksame Datum (K1: nach dem Puffer zählt der Tag der Bestätigung).
- **Folge:** Meldung So, Bestätigung Mi: Aktivität in KW n+1, Punkte in KW n (schon abgeschlossen). Familienziel KW n ist ausgewertet, KW n+1 bekommt die Punkte nie; Held der Woche (Fakt) ebenso; KW n+1 zeigt eine aktive Woche mit 0 XP. Tritt regelmäßig auf (Eltern bestätigen später).
- **Behebung:** Eine Regel für alles: `spielregeln.selectors.wirksames_datum` (Puffer, lokale Zeit) für Aktivität, Grundpunkte, Serienbonus, Sonderpunkte. ARCHITECTURE 7.2 ergänzt.
- **Test:** `tests/szenarien/test_spielregeln_aufgaben.py::test_spaete_bestaetigung_punkte_und_aktivitaet_in_derselben_woche` (rot vor der Korrektur).
- **Commit:** `a4b1976`

### P-03 (mittel) Sondertag-Catch-up und Meldung "jetzt einlösbar"

- **Beleg:** `deploy/crontab` ohne `sondertag_sicherstellen`; Kommando als `BaseCommand` (keine Sperre, kein `JobLauf`). Früh verdiente Ansprüche ("einlösbar ab X") erzeugten zum Datum X keine Meldung.
- **Behebung:** Kommando als `JobBefehl`, stündlich `25 * * * *`. Neuer Service `sondertag.services.einloesbar_melden`: Wird der erste offene Anspruch eines Kindes einlösbar, gehen `sondertag.einloesbar` (Kind: Pop-up + Push) und `sondertag.einloesbar_eltern` (Eltern: Push, mit Wunsch falls vorhanden) **genau einmal** raus: bedingtes Update auf neues Feld `einloesbar_gemeldet_am` + Ereignis-Schlüssel. Sofort einlösbare Ansprüche setzen das Feld bei der Freischaltung (keine Doppelmeldung). Migration `sondertag/0003` (additiv).
- **Tests:** `apps/sondertag/tests/test_sondertag.py::test_wartender_anspruch_meldet_einloesbar_genau_einmal`, `::test_sofort_einloesbar_meldet_nur_die_freischaltung`, `::test_zweiter_in_der_warteschlange_meldet_erst_nach_annahme_des_ersten`, `::test_job_sondertag_sicherstellen_mit_joblauf`; `tests/test_crontab.py` (Pflichtjob).
- **Commit:** `c3d257b`

### P-04 (mittel) Aufbewahrung (B-15)

- **Beleg:** REVIEW_PHASE1 B-15; seit Phase 2 stehen zusätzlich Sondertag-Wünsche (Freitext des Kindes) in `Ereignis.daten`.
- **Behebung:** Job `benachrichtigungen_aufraeumen` (täglich 04:20, `JobBefehl`) ruft `benachrichtigung.services.aufbewahrung`: gelesene Benachrichtigungen nach `benachrichtigung.aufbewahrung_tage` (90), ungelesene nach `benachrichtigung.aufbewahrung_ungelesen_tage` (180), Zustellungen nach `benachrichtigung.zustellung_aufbewahrung_tage` (90), Ereignisse nach `ereignisse.aufbewahrung_tage` (180; nur verteilt, alle Handler `ok`, nicht mehr von einer Benachrichtigung referenziert; Verarbeitungen per CASCADE), Job-Läufe nach `allgemein.joblauf_aufbewahrung_tage` (90). Alle Fristen als Einstellung (Editor), Startwerte per Datenmigration (`ereignisse/0004`, `benachrichtigung/0005`, `kern/0005`). Ledger und Audit werden nie gelöscht; fehlerhafte/aufgegebene Verarbeitungen bleiben im Systemstatus.
- **Geprüft:** Keine Fachlogik hängt an alten Ereignissen. Idempotenz stützt sich überall auf DB-Zustand (Fakten, bedingte Updates), Ereignis-Schlüssel sind nur zweite Schicht. `MeilensteinErreicht.ereignis` ist `SET_NULL`. Einzige Ausnahme: `spielregeln_neuberechnen --nachtragen` liest `aufgabe.erledigt`-Ereignisse – der Backfill lief bereits in Migration `spielregeln/0003`; danach nur noch Reparaturwerkzeug für die letzten 180 Tage (dokumentiert).
- **Tests:** `tests/test_aufbewahrung.py` (Fristen = Einstellungen, alte Daten weg / junge bleiben, Ledger + Audit unverändert, Doppellauf ändert nichts, aufgegebene Verarbeitung bleibt, Job protokolliert).
- **Commit:** `943f0ec` (Test-Ort `a3cdf41`)

### P-05 (mittel) Großziel-Ableitung

- **Beleg:** `familienziel/services.py:grossziel_pruefen` (alt) legte beim ersten Erreichen der Schwelle an und kehrte zurück; jeder weitere Aufruf (im selben Joblauf drei Mal) fand die nächste Teilfolge.
- **Folge:** Eltern senken `familienziel.grossziel_serie` von 4 auf 1 bei 3 erreichten Wochen -> 3 Großziele mit je Pop-up/Push. Umgekehrt: Prüfung erst nach einer verfehlten Woche (Ausfall) -> geschaffte Folge verloren (Fall war im Alt-Code abgedeckt, im ersten Umbau nicht – mit Test abgesichert).
- **Behebung:** Auslösende Woche = jüngste erreichte Woche der Folge, höchstens ein Großziel je Aufruf; endet eine Folge (Lücke, verfehlt, laufend), zählt sie, wenn sie die Schwelle erreicht hat.
- **Tests:** `apps/familienziel/tests/test_familienziel.py::test_gesenkte_serie_gibt_genau_ein_grossziel_an_der_juengsten_woche`, `::test_catch_up_nach_ausfall_verliert_geschaffte_folge_nicht`.
- **Weitere AP29-Prüfpunkte ohne Befund:** synchroner Erfolg läuft im Savepoint (Fehler kippt die Buchung nicht, Rollback der Buchung nimmt den Erfolg mit), Bestätigung bucht vor der Aktivität – der zweite Handler (`aktivitaet.erfasst`) prüft erneut; Stimmen für deaktivierte Belohnungen zählen nicht; neutrale Familienwoche nur, wenn alle aktiven Kinder pausiert sind.
- **Commit:** `50070f1`

### P-06 (mittel) Versteckte Kopplung avatar -> spielregeln.raenge

- **Beleg:** `apps/avatar/mods.py:41`, `services.py:21`, `views_mods.py:13-14` (alt) importierten `apps.spielregeln.raenge`. Der Layers-Vertrag erlaubt das (Schicht 3 -> 2), ARCHITECTURE 2.2 aber nur `services`/`selectors`.
- **Behebung:** Mod-Konditionen in `spielregeln.selectors` (`mod_preis`, `mod_bauzeit_stunden`, `preis_faktor`, `bauzeit_faktor`, `rang_zur_stufe`), Mod-Standards in `spielregeln.services` (`mod_standard_aendern`, `mod_faktoren_setzen`). Neuer Vertrag "spielregeln nur über seine öffentliche Schnittstelle" (Fach-Module, Oberfläche, Einrichtung dürfen `raenge`, `abzeichen`, `held`, `auswertung`, `kontinuitaet`, `serienbonus` nicht importieren).
- **Weitere Kopplungen geprüft (AST-Scan aller Querimporte):** `<modul>/events.py -> benachrichtigung.texte` (Text-Registry, bewusst, dokumentiert), `einrichtung -> benachrichtigung.models.SmtpSicherheit` (Enum, wie `konten.Rolle`), `benachrichtigung -> ereignisse.models` (Schicht 2 untereinander, Phase 1). Keine dynamischen Importe (`apps.get_model`) außerhalb von Migrationen.
- **Nachweis:** `lint-imports` 5 Verträge eingehalten.
- **Commit:** `a3cdf41`

### P-08 (niedrig) SVG-Sanitizer gemeinsam in kern

- **Behebung:** `apps/kern/svg.py`: Whitelist-Parser aus avatar verschoben; `viewbox` konfigurierbar (`None` = beliebig), `verlaeufe=True` erlaubt `defs`/`linearGradient`/`radialGradient`/`stop` mit `id`, Koordinaten, `offset`, `stop-color` (nur Hex), `stop-opacity`, `gradientUnits`; `fill="url(#id)"` nur auf im Dokument definierte ids (keine externen Referenzen, keine doppelten ids, kein `href`/`gradientTransform`). `avatar.generator.svgsicher` = Avatar-Fläche 32 x 48 ohne Verläufe. Abzeichen: `spielregeln.abzeichen.grafik_pruefen` (64 x 64, Verläufe erlaubt); Badge-Test ohne viewBox-Ersetzung.
- **Tests:** `apps/kern/tests/test_svg.py`, `apps/spielregeln/tests/test_abzeichen_svg.py`, bestehende `apps/avatar/tests/test_svgsicher.py` unverändert grün.
- **Commit:** `9f52292`

### P-09 (niedrig) Überlauf und kleine Schrift

- **Beleg:** Screenshot-Heuristik: Tablet-Seite auf 390 px 419 px breit (Zeile "Punkte + n offen" in der Avatar-Kachel), Eltern-Mods 678 px (Raster `1fr 1fr` mit Eingabefeldern); `.rk-karte__punkte` 0,85rem (13,6 px), `.rk-fakten dt` 0,75rem auf Kinder-/Tablet-Seiten.
- **Behebung:** Kachelzeile bricht um (`flex-wrap`, `min-width: 0`), Mod-Standards `minmax(0, 1fr)`; Ranking-Texte 0,875rem.
- **Test:** `apps/oberflaeche/tests/test_designsystem.py::test_keine_schrift_unter_14px_im_css`; Browser-Lauf ohne Überlauf/Kleintext.
- **Commits:** `db1d4b0`, `a0ae3b7`

### P-10 (niedrig) Ruhezeit vor Wiederholung (B-19)

- **Behebung:** `benachrichtigung/versand.py` prüft vor jedem Versand die Ruhezeiten des Elternteils; fällt der Versuch hinein -> `unterdrueckt_ruhezeit` (kein Nachholen, wie beim Routing).
- **Test:** `apps/benachrichtigung/tests/test_versand.py::test_wiederholung_in_der_ruhezeit_bleibt_stumm`.
- **Commit:** `faf05b9`

### P-11 (niedrig) Abschlusszeitpunkt Familienwoche

- **Beleg:** `familienziel/zeitplan.py:abschluss_zeitpunkt` (alt): UTC + Puffer; `spielregeln.kontinuitaet.finalisiert_ab`: lokale Wanduhr. Bei Puffer über eine Zeitumstellung (Einstellung bis 168 h) 1 h Versatz.
- **Behebung:** eine Quelle `spielregeln.selectors.woche_abgeschlossen_ab`.
- **Test:** `test_familienziel.py::test_abschluss_wie_spielregeln_auch_ueber_zeitumstellung` (rot vor der Korrektur).
- **Commit:** `5be8362`

### P-12 (niedrig) Pausen-Formular Datumsformat

- **Behebung:** `DateInput(format="%Y-%m-%d")` (wie in `aufgaben`). **Test:** `apps/spielregeln/tests/test_services.py::test_pausenformular_datum_im_iso_format`. **Commit:** `a0ae3b7`

### P-13 (niedrig) Doku an den Code angeglichen (B-22)

- DATA_MODEL: 5.8 Popup, 6 (spielregeln), 9–11 (avatar, sondertag, familienziel), 12 (Modellübersicht), 14 (Idempotenz), 15.2 (alle Einstellungen mit Startwerten) aus Modellen/Registry/Datenmigrationen erzeugt. Abweichungen u. a.: `spielregeln.puffer_stunden` (statt `wochen_puffer_stunden`), `spielregeln.neutral_ab_pausentagen`, `aufgaben.vorwarnung_stunden_vorher`, `familienziel.grossziel_serie`, `oberflaeche.ranking_modus = schaufenster`, `Prognose` erst AP32, `ModDefinition.seltenheit` als Zahl, `Avatar.angelegt` mit Mod-Schlüsseln.
- ARCHITECTURE: 2.2 (Verträge), 5.2 (vollständiger Ereigniskatalog aus der Registry, 51 Typen), 6 (Jobs laut Crontab inkl. Aufbewahrung), 7.2/7.6/7.7 (P-02, P-03, P-05), 8 (SVG-Sanitizer), 12 (AP31 erledigt).

---

## Offene Befunde (mit Begründung und Empfehlung)

### P-07 (mittel) XP-Schwellen nicht bindend

- **Beleg:** Szenario (Tabelle unten): bei 150, 175 und 200 P/Woche fallen alle Rangaufstiege exakt auf die Mindest-Aktivwochen (20/42/64/90/120 + Abschluss-Dienstag). XP liegen dann weit über der Schwelle (z. B. Woche 20: ≈ 3.700 XP bei 150 P/Woche inkl. Serienbonus, Schwelle 2.000). Bindend würden die Schwellen erst unter ≈ 120 XP/Woche.
- **Folge:** Der Kalibrierungsfaktor (K3, Entscheidung 14 "nach 4–6 Wochen kalibrieren") wirkt nur auf XP-Schwellen und ändert das Tempo bei normalem Fleiß nicht; sehr fleißige Kinder werden nicht schneller, nur unregelmäßige langsamer (gewollt: Kontinuität vor Menge).
- **Empfehlung:** Für AP32 (Prognose/Kalibrierung) entscheiden: entweder (a) so lassen (Rang = Ausdauer, XP nur Untergrenze) und die Kalibrierungsansicht auf die Mindestwochen beziehen, oder (b) XP-Schwellen anheben (z. B. ×1,5), damit Fleiß sichtbar zählt. Keine Startwerte geändert (Entscheidung 14 ist Nutzerentscheidung).

### P-15 (niedrig) Grundregel: Mod-Details nur als Daten

- Einzelpreis/Bauzeit je Mod (`ModDefinition.preis/bauzeit_stunden`), Themen an/aus und SVG-Overrides sind im Eltern-Dashboard nicht änderbar (nur Rang-Standards und Faktoren). Alle Familienregeln (Preise je Seltenheit, Bauzeiten, Zeitbremse, Zyklus, Sondertag-Grenzen, Ränge, Abzeichen, Meilensteine, Familienbelohnungen, Ranking-Modus, Aufbewahrung) sind änderbar. **Empfehlung:** Mod-Verwaltung (Einzelpreis, aktiv, Thema aktiv) in Phase 3 (AP34 "weitere Mods").

### P-16 (niedrig) Sondertag-Takt im 3. App-Jahr

- Zwischen Legendary-Sondertag (Woche 97) und erstem God-Mode-Zyklus (Woche 147) liegen 50 Wochen: App-Jahr 3 hat 1 statt 2 Sondertage; danach wieder alle 26 aktiven Wochen (≈ 2/Jahr). **Empfehlung:** bei AP32 prüfen, ob God Mode früher (z. B. Mindestwochen 110) oder der erste Zyklus kürzer sein soll. Grenzen werden nie verletzt.

### P-17 (niedrig, bewusst) Korrektur am Korrekturtag

- `punkte.gegenbuchen` setzt `bezugsdatum = heute`. Eine Korrektur mindert die XP der laufenden Woche (Familienziel, Held), nicht der ursprünglichen; die Aktivität der ursprünglichen Woche wird storniert. Entspricht K2 ("es war nie verdient") nur halb, ist aber für Kinder nachvollziehbar und verändert keine abgeschlossenen Wochen. Keine Änderung.

### P-18 (niedrig, akzeptiert) Avatar-SVG ohne Anmeldung

- `/avatar/<sha256>.svg` ist öffentlich (Cache `immutable`, auch auf der Tablet-Startseite ohne Anmeldung genutzt). Hash nicht erratbar, Inhalt nur Grafik, nur im Heimnetz erreichbar.

---

## Startwert-Kalibrierung (Entscheidung 14, Planung 150–200 P/Woche)

Gemessen im Szenario (`tests/szenarien/test_gesamtjahr.py`, `NESTWERK_KALIBRIERUNG=<datei>`). Wochen ab Go-live (Woche 1). Kinder kaufen Mods, sobald das Guthaben reicht (nur Seltenheiten ab 2 bis zum eigenen Rang, ab God Mode die Sets), wünschen sich Sondertage sofort, Eltern nehmen sofort an. Ø XP enthält Serienbonus (bis +25 %).

**52 Wochen, drei Kinder (Startwerte)**

| Kind | Soll P/Woche | Ø XP/Woche | Rang 2 | Rang 3 | Rang 4 | Rang 5 | Rang 6 | Sondertage verdient (Woche) | angenommen (Woche) | je App-Jahr |
|---|---|---|---|---|---|---|---|---|---|---|
| Anna (fleißig) | 200 | 244 | 21 | 44 | – | – | – | 26, 49 | 26, 49 | J1: 2 |
| Ben (mittel, Freigabe So, 2 Korrekturen) | 175 | 211 | 21 | 43 | – | – | – | 26, 48 | 26, 48 | J1: 2 |
| Carl (wechselhaft: 2 Wochen Pause, 3 faule Wochen) | 150 | 159 | 25 | 49 | – | – | – | 30 | 30 | J1: 1 |

Familienziele erreicht: 47 von 52, Großziele: 11, Held-der-Woche-Titel: 33 (eine Familienurlaubswoche neutral).

**156 Wochen (3 App-Jahre), ein Kind, jede Woche aktiv**

| Soll P/Woche | Ø XP/Woche | Rang 2 | Rang 3 | Rang 4 | Rang 5 | Rang 6 | Sondertage (Woche) | je App-Jahr |
|---|---|---|---|---|---|---|---|---|
| 150 | 187 | 21 | 43 | 65 | 91 | 121 | 26, 48, 70, 97, 147 | J1: 2, J2: 2, J3: 1 |
| 200 | 249 | 21 | 43 | 65 | 91 | 121 | 26, 48, 70, 97, 147 | J1: 2, J2: 2, J3: 1 |

**Bewertung:** Das Planungsziel "~2 Sondertage je App-Jahr" wird im ersten und zweiten Jahr genau getroffen (Rang 2 nach 20 aktiven Wochen + 6 Wochen Zeitbremse = Woche 26; zweiter Sondertag durch Rang 3 und den 150-Tage-Abstand Woche 48/49). Unregelmäßige Kinder liegen bei 1–2. Grenzen nie verletzt. Siehe P-07 (Tempo hängt nur an den Mindestwochen) und P-16 (Jahr 3).

(Die 200-P-Zeile des Mehrjahreslaufs stammt aus einem Einzellauf während des Reviews; im Testlauf ist nur die Untergrenze 150 P aktiv, um die Laufzeit zu begrenzen.)

---

## Szenario-Tests (Invarianten)

- `tests/szenarien/simulation.py`: treibt alle Module über Services mit simulierter Zeit (`zeit.jetzt`), täglich die Jobs `wochen_sicherstellen`, `familienwoche_sicherstellen`, `mods_fertigstellen`, `sondertag_sicherstellen`; je Woche Dienstag 01:00 Jobs **zweimal** und Vergleich der Zeilenzahlen aller Fakten-/Ergebnistabellen (Ereignisse, Wochenauswertungen, Ränge, Abzeichen, Meilensteine, Familienwochen + Status, Großziele, Ansprüche, Buchungen, Mod-Besitz, Mod-Sets, Helden).
- Abläufe: Vertrauen (sofort), Eltern-Freigabe So -> Mo im Puffer, jede 10. Woche erst Mi (P-02), Korrekturen, Kind-Pause (2 Wochen), Familienurlaub (1 Woche), faule Wochen, Mod-Käufe mit Zeitbremse, Themen (ritter, pirat), Abstimmung sonntags, Wunsch + Annahme.
- Invarianten (alle grün): Sondertage ≤ 2 je App-Jahr und ≥ 150 Tage; Salden = Summe Ledger, Guthaben ≥ 0, Mod-Käufe = `modkauf`-Buchungen = bezahlte Preise, Ausgaben ändern XP nie; keine doppelten Abzeichen/Ränge/Meilensteine/Ansprüche; `spielregeln.neu_berechnen() == []`; Jobs idempotent bei Doppellauf (52 bzw. 156 Prüfungen).
- AP26 Zeitbremse: Sondertag genau 5 Wochen nach Rangaufstieg (6 Mods, 1 zählend je Woche, Warteschlange); AP30 Held: Doppellauf ändert keine Titel; AP27 Grenzen: s. o.

---

## Migrationstest Phase 1 -> Phase 2

1. Worktree auf `a2df279` (produktiver Phase-1-Stand), frische DB `migrate` (42 Migrationen).
2. Beispieldaten mit den Phase-1-Services: 2 Eltern-Profile/3 Kinder, 36 Aufgaben (Vertrauen und Eltern-Freigabe, über 3 Wochen verteilt, mit Sonderpunkten), 32 bestätigt, 1 Korrektur, 1 offener Einlöseantrag, Worker-Läufe (Benachrichtigungen, Zustellungen).
3. Kopie der DB, dann `migrate` mit dem aktuellen Code: alle Phase-2-Migrationen (spielregeln 0001–0009, avatar 0001–0004, familienziel, sondertag 0001–0003, oberflaeche 0002, ereignisse 0004, benachrichtigung 0005, kern 0005) fehlerfrei; zweiter `migrate`-Lauf: nichts zu tun; `makemigrations --check`: keine Änderungen; `manage.py check` ohne Befund.
4. Datenmigrationen/Backfills: Aktivitäten aus `aufgabe.erledigt` nachgetragen (32 aktiv = 32 bestätigt, 1 storniert = 1 korrigiert), Ränge (6), Abzeichen (12), Meilensteine (5), 11 Themen mit 360 Mods, 5 Familienbelohnungen, alle neuen Einstellungen mit Startwert (fehlend nur `allgemein.anzeigename`/`sprache`, die der Assistent setzt – im Testdatensatz ohne Assistent, auf der Produktions-DB vorhanden).
5. Jobs `wochen_sicherstellen`, `familienwoche_sicherstellen`, `mods_fertigstellen`, `sondertag_sicherstellen`, `benachrichtigungen_aufraeumen` je zweimal: erster Lauf legt 9 Wochenauswertungen, 1 Held, 1 Familienwoche an, zweiter Lauf ändert nichts; `spielregeln.neu_berechnen()` ohne Abweichung.
- **Hinweis für das Update auf der VM:** Rückweg nur über das Pre-Update-Backup (`update.sh` sichert vor `migrate`); die Startwert-Migrationen sind rückwärts bewusst No-op.

---

## Geprüft ohne Befund (Auszug)

- **AuthZ Phase-2-Views:** alle Eltern-Views `nur_eltern` (Pausen, Ränge, Kalibrierung, Abzeichen, Meilensteine, Mods/Standards/Sofort-fertig, Familienziel, Sondertage, Ranking-Modus); Kind-Views `nur_kind` mit Eigentumsprüfung im Service (Mod kaufen/anlegen nur eigenes Thema/eigener Besitz, Wunsch nur erster eigener Anspruch, Abstimmung nur eigene Stimme); Galerien nur bei `DEBUG`; Tablet-Teil passiv + Heimnetz-Prüfung. Kein `csrf_exempt`, kein `|safe` in Phase-2-Templates; einzige `mark_safe`-Stellen geben Renderer-Ausgabe (deterministisch, Overrides durch die Whitelist) aus.
- **Nebenläufigkeit:** Mod-Kauf und Themenwechsel unter `punkte.schreibsperre` (IMMEDIATE), Fertigstellung bedingtes Update, Zeitbremse unter Sperre des Kindes; Fakten (Rang, Abzeichen, Meilenstein, Anspruch, Großziel) per Unique + `get_or_create`/IntegrityError; Familienziel-Erfolg und Abstimmung bedingte Updates; Held-Bewertung idempotent (Ereignis-Schlüssel gegen parallele Läufe); Sondertag-Annahme prüft Grenzen in derselben Transaktion.
- **Datenschutz:** Wunschtexte nur in Anspruch (Historie, Eltern sichtbar) und Ereignis (jetzt 180 Tage); keine Nachweise in Phase-2-Ereignissen; Audit ohne Freitext (nur Zeichenzahl beim Wunsch).
- **Sondertag-Grenzen (AP27):** App-Jahr inkl. 29.02., Abstand auch zu später datierten Korrekturen, Warteschlange FIFO, manuelle Historie vor Go-live zählt nur für den Abstand; Annahme serverseitig erneut geprüft. Eltern können Bezugsdaten bewusst korrigieren (Audit).
- **AP21:** Bezugswoche des Serienbonus nach dem Puffer = Woche der Bestätigung (jetzt auch für die Buchung, P-02).

---

## Nachweis

- `pytest`: 1533 grün (vorher 1496), 247 s (Szenario-Tests ≈ 3 min davon).
- `ruff check .`: grün. `lint-imports`: 5 Verträge eingehalten.
- Browser: `docs/screenshots/phase2/ergebnisse.md`, `docs/screenshots/phase2/sondertag/ergebnisse.md`.
