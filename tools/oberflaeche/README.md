# Oberflächen-Screenshots und Browser-Prüfung

Wiederverwendbares Werkzeug (Python-Playwright, kein MCP) für alle Agents ab Phase 2.

## Einmalig

    .venv/bin/pip install -e ".[dev]"      # enthält playwright (gepinnt)
    .venv/bin/playwright install chromium  # nur Browser-Cache, kein apt, kein --with-deps

## Lauf

    .venv/bin/python tools/oberflaeche/screenshots.py [--ziel docs/screenshots/phaseN] [--sichtbar]

Das Skript
1. legt eine Demo-DB unter `/tmp/nestwerk-demo` an (Entwicklungs-Settings, `migrate`, `runserver` auf `127.0.0.1:8765`),
2. durchläuft den Einrichtungs-Assistenten im Browser (Mama/Papa, Kind A/B/C mit PIN 1111/2222/3333, Passwort `Sonnenblume-4711-Demo`),
3. erzeugt Demo-Daten (`demo_daten.py`: Aufgaben aus der Bibliothek, Reservierung, Meldung, Einlöseantrag),
4. fotografiert jede Seite in **Handy 390x844** und **Tablet/Eltern 1280x800** (`<label>__handy.png`, `<label>__tablet.png`, ganze Seite),
5. sammelt je Seite Konsolenfehler, CSP-Verstöße, 4xx/5xx- und fehlgeschlagene Requests, externe Requests sowie DOM-Heuristiken (Überlauf, Ziele unter 44 px, Text unter 14 px, Knöpfe ohne Beschriftung) -> `ergebnisse.json` und `ergebnisse.md`,
6. stoppt den Server und löscht die Demo-DB.

Die PNGs mit dem Read-Tool ansehen und die Befunde von Hand in `BEFUNDE.md` bewerten; die Heuristiken ersetzen das nicht.

## Erweitern

- Neue Seite: Eintrag `(label, pfad)` in `SEITEN_KIND` bzw. `SEITEN_ELTERN` in `screenshots.py`.
- Neue Demo-Daten (neue Fach-Apps): `demo_daten.py` ergänzen. Es läuft gegen die Demo-DB und nutzt nur Services/Selectors.
- Neue Einrichtungs-Schritte: Funktion `einrichtung()` anpassen (Feldnamen aus den Templates).
- Port/Pfade: Umgebungsvariablen `NESTWERK_DEMO_PORT` (Standard 8765) und `NESTWERK_DEMO_DIR` (Standard `/tmp/nestwerk-demo`) für parallele Läufe; `--nur ranking` nimmt nur das Familien-Ranking auf (AP30).

## Hinweise

- Der Headless-Browser meldet Notification-Berechtigung als blockiert (Push-Seite zeigt daher "blockiert") und nutzt US-Datumsformat; das ist kein App-Fehler.
- Ganzseiten-Screenshots zeigen sticky Kopfzeilen mitunter mitten im Bild (Artefakt von `full_page`).
- Läuft nur lokal; es werden keine externen Hosts angesprochen (jeder externe Request wäre ein Befund).
