# Visuelle Befunde Phase 1 (Screenshot-Prüfung)

Erzeugt mit `tools/oberflaeche/screenshots.py` (Handy 390x844 und Tablet 1280x800, je `*__handy.png` / `*__tablet.png`). Rohdaten: `ergebnisse.md`, `ergebnisse.json`. Alle Seiten wurden angesehen.

## Automatische Prüfung
- Konsolenfehler: **0** auf allen 24 Seiten.
- CSP-Verstöße: **0**. Externe Requests: **0**. Fehlgeschlagene Requests / 4xx / 5xx (auch static): **0**.

## Behoben in diesem Lauf
1. **Push-Seite**: Alle Zustandsblöcke gleichzeitig sichtbar (Anleitung iOS, "aktivieren", "aktiv", "blockiert"). Ursache: `.stapel` (display:flex) überschrieb das `hidden`-Attribut. Fix: globale Regel `[hidden] { display:none !important }` in `nestwerk.css`. Betraf alle `hidden`-Elemente mit Layout-Klassen.
2. **Eltern-Meldungen ("Reserviert") und Bibliothek**: Karten riesig hoch, Text mittig, Knöpfe unten. Ursache: `.karte__inhalt` (flex-direction column) gewann gegen `.zeile`, dadurch `flex: 1 1 16rem` als Höhe. Fix: `flex-direction: row` in `.zeile` (aufgaben.css, oberflaeche.css).
3. **Wochenplan**: Datumsfeld und "Verschieben"-Knopf ragten aus der schmalen Tagesspalte. Fix: Feld/Knopf auf Spaltenbreite begrenzt, kleinere Schrift im Feld.
Tests: `test_hidden_attribut_gewinnt_gegen_komponenten_display`, `test_zeile_ist_eine_reihe`.

## Pro Seite
| Seite | Status | Anmerkung |
|---|---|---|
| Einrichtung 1-4, 8, 9 | OK | Klar, Fortschrittsbalken, große Knöpfe. Schritt 8: Abschluss-Knopf nutzt Pfeil statt Haken, Text umbricht auf zwei Zeilen. |
| Tablet-Startseite | OK | Kinderkacheln groß, gut tippbar. Avatar ist nur Platzhalter "K" (alle gleich, nur Farbe). |
| PIN-Eingabe | OK | Große Tasten, 4 Felder. "OK" bei leerer PIN stark abgedunkelt (Kontrast niedrig, gewollt als deaktiviert). |
| Kinder-Dashboard | Problem (klein) | Karte oben: Avatar mittig, Name/Punkte versetzt und nicht zentriert. Zeile "Mülltonnen rausstellen" bricht Punkte auf eigene Zeile (Handy). Kleiner Text (Punkte-Beschriftung) unter 14 px. |
| Kinder-Aufgaben | OK | Klar, Hauptknopf "Erledigt melden" groß. |
| Kinder-Belohnungen | OK | Gesperrte Belohnung erkennbar ("Noch 5 Punkte"), Kontrast der gesperrten Karte niedrig. |
| Eltern-Login | OK (klein) | Checkbox "vertraut" ist winzig und steht über dem Label statt daneben. |
| Eltern-Dashboard | Problem (klein) | Zahlenlinks (1/0/1) im Browser-Standardblau, 7x24 px, schwer tippbar. Badge "NEU" bei Benachrichtigungen, obwohl "Noch nichts passiert". Systemstatus "ACHTUNG" (Worker ohne Rückmeldung, im Demo erwartet). 10 Textelemente unter 14 px. |
| Eltern-Meldungen | OK (nach Fix) | Formularfelder Sonderpunkte/Begründung/Rückfrage ohne Platzhalter, Felder wirken leer und breit. |
| Wochenplan | Problem | Handy: sieben sehr hohe, fast leere Tagesspalten im horizontalen Scroll, erste Aufgabe erst nach langem Wischen. Tablet: Spalten schmal (Titel umbrechen), Datumsfeld nur knapp passend. Kein Platz für Namen/Farbe der Kinder. |
| Aufgabenformular | OK (klein) | Alle Wiederholungsfelder (Start, Ende, Zeiten, Limit) immer sichtbar, auch bei "Einmalig". Sehr lang. Datum/Uhrzeit im US-Format (Headless-Browser, kein App-Fehler). |
| Bibliothek | OK (nach Fix) | 15 Vorlagen untereinander; Liste lang, keine Filter nach Kategorie. Chips (Kategorie, Freigabeart) in Großbuchstaben, 12 px, schwer lesbar. |
| Einstellungen-Editor | Problem (klein) | Sehr lange Einzelseite (Handy ca. 7000 px), Gruppen-Chips oben 28 px hoch (<44 px) als Sprungmarken. Hilfetexte klein. |
| Familie | OK (klein) | "Geräte"-Karte hat zentrierte Überschrift, die anderen linksbündig. "Deaktivieren" (Summary) nur 24 px hoch. |
| Push-Seite | OK (nach Fix) | Im Headless-Browser Zustand "blockiert" (korrekt). |
| Styleguide | OK | Drei Themes sichtbar, konsistent. Ganzseite sehr lang. |

## UX-Auffälligkeiten (Stand erster Lauf; behoben siehe Nachbesserung)
- Zielgrößen unter 44 px: Dashboard-Zahlenlinks, Gruppen-Chips im Editor, "Deaktivieren", Checkbox im Login. Kinderseiten sind unauffällig.
- Text unter 14 px auf Eltern-Seiten (Chips, Metazeilen, Hilfetexte): Bibliothek 51, Aufgabenliste 24, Wochenplan 12 Elemente.
- Pixel-Schrift der Überschriften (Kinder) gut lesbar; Kontrast in allen Themes optisch ausreichend, nicht gemessen.
- Das Eltern-Layout hat keine Ansicht "was ist neu" auf der Startseite außer Zähler; Meldungen/Einlöseanträge sind je einen Klick entfernt (gut).

## Empfehlungen
1. Wochenplan auf Handy als Tagesliste (Akkordeon je Tag) statt 7 Spalten; auf Tablet Spaltenbreite oder Verschieben-Formular hinter Menü.
2. Mindestgröße 44 px für alle Eltern-Links/Chips, die tippbar sind; Metatexte auf mindestens 14 px.
3. Aufgabenformular: Wiederholungsfelder je nach Auswahl ein-/ausblenden (CSS `:has` ist für Wochentage/Intervall schon da, Zeitfelder nicht).
4. Kinder-Dashboard-Profilkarte zentrieren oder linksbündig ausrichten.
5. Login-Checkbox mit Label in eine `.reihe` setzen.
6. Screenshot-Werkzeug bei jedem neuen Phase-2-Modul laufen lassen (README in `tools/oberflaeche/`).

## Nachbesserung (Phase-1-Politur)
Neuer Screenshot-Lauf: Konsole 0, CSP 0, externe Requests 0, 4xx/5xx 0 auf allen 24 Seiten; Heuristiken melden keine Ziele unter 44 px und keinen Text unter 14 px mehr.
- **Wochenplan Handy**: Tage untereinander (eine Spalte), leere Tage kompakt (`wochenplan__tag--leer`); Ziehen zwischen Tagen bleibt, "Verschieben"-Datumsformular ist der sichtbare Fallback, Hinweistext angepasst. Tablet unverändert (7 Spalten).
- **Touch-Ziele >= 44 px**: Dashboard-Zahlenlinks, Chip-Links, `summary` ("Deaktivieren"), Login-Checkbox-Zeile (`label.reihe`, Checkbox 24 px), Logo-Link.
- **Schrift**: Chips, Hilfetexte, Punkte-Einheit, Wochenplan-Meta mindestens 14 px (rem statt em).
- **Aufgabenformular**: Start/Ende/Limit nur bei "Wöchentlich"/"Intervall" sichtbar (reines CSS `:has`, kein JS; ohne `:has`-Support sind alle Felder sichtbar). Zeitfenster bleibt immer sichtbar.
- **Kinder-Dashboard**: Profilkarte (Avatar, Name, Punkte/XP) zentriert.
- **Einstellungen-Editor**: Modul-Abschnitte als `<details>`, standardmäßig zu; nach Speichern/Fehler öffnet der betroffene Abschnitt.
- **Tablet-Startseite (Login-Start)**: Familienziel-Platzhalter "0 / 100" entfernt; Block `familienziel_abschnitt` bleibt leer, bis Modul familienziel (Phase 2) ihn füllt.
- Offen: Ranking-Platzhalter ("Noch kein Ranking") bleibt als ehrlicher Leerzustand; keine Kontrastmessung.
Tests: `test_designsystem.py` (Wochenplan-Mobil, Fake-Wert, Formular-CSS, details, Touch/Schrift).
