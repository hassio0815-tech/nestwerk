# Mitwirken an Nestwerk

Danke für dein Interesse. Nestwerk ist ein Familien-Dashboard für den eigenen Server. Beiträge sollen die Familien-Installation sicher und verständlich halten.

## Grundregeln

- **Keine Fremddienste:** Keine Analyse, kein Tracking, keine CDN-Skripte und keine externen Requests aus der Oberfläche. Die Prüfung `tools/oberflaeche/screenshots.py` meldet jeden externen Request als Befund.
- **Keine fremden Marken:** Grafiken und Namen sind eigene Entwürfe. Keine Figuren, Texturen oder Namen aus Spielen oder anderen Marken.
- **Werte in der Datenbank:** Regeln und Startwerte liegen in der Datenbank, nicht fest im Code. Im Code stehen nur Definitionen und Startwerte für Datenmigrationen.
- **Alles freiwillig:** Keine Pflichtaufgaben, keine Strafen, keine Punktabzüge.

## Entwicklungsumgebung

Voraussetzung: Python 3.13 oder neuer.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate          # legt data/db/nestwerk.sqlite3 an
python manage.py runserver        # http://127.0.0.1:8000/gesundheit/
```

Die Konfiguration erfolgt über Umgebungsvariablen mit dem Präfix `NESTWERK_`. Eine Vorlage liegt in `.env.example`. Die Einstellungsmodule sind `nestwerk/settings/{basis,entwicklung,produktion,test}.py`.

## Prüfungen vor jedem Commit

```bash
pytest                            # Tests (inkl. Szenario-Tests in tests/szenarien)
ruff check . && ruff format --check .
lint-imports                      # Schichtenregeln
```

Alle drei Befehle müssen grün sein. Die Schichtenregeln sind in `pyproject.toml` (Abschnitt `tool.importlinter`) hinterlegt und laufen auch in den Tests.

## Modul-Schichten

Nestwerk besteht aus Django-Apps mit festen Schichten. Imports dürfen nur **nach unten** gehen:

| Schicht | Apps |
|---|---|
| 4 Oberfläche | `oberflaeche`, `einrichtung` |
| 3 Fach-Module | `aufgaben`, `belohnung`, `avatar`, `sondertag`, `familienziel` |
| 2 Gemeinsame Kerne | `punkte`, `ereignisse`, `benachrichtigung`, `spielregeln` |
| 1 Identität | `konten` |
| 0 Basis | `kern` |

- Fach-Module importieren einander **nicht**. Sie kommunizieren über Domain-Ereignisse und die Registry in `kern`.
- Jede App hat nur diese öffentlichen Schnittstellen: `services.py` (schreibend), `selectors.py` (lesend), `events.py` und `registry.py`.
- Fremde `models.py` werden nie importiert.

Details: `docs/ARCHITECTURE.md`, Abschnitt 2. Eine Anleitung für neue Module steht in `docs/MODULE-ERWEITERN.md`.

## Oberflächen-Screenshots

Das Werkzeug `tools/oberflaeche/` erzeugt Screenshots mit Demo-Daten (Python-Playwright). Es prüft außerdem Konsolenfehler, CSP-Verstöße und externe Requests.

```bash
.venv/bin/playwright install chromium   # nur Browser-Cache
.venv/bin/python tools/oberflaeche/screenshots.py --ziel docs/screenshots/phaseN
```

Die Demo-Daten sind fiktiv. Vor dem Commit die PNGs ansehen. Die Heuristiken ersetzen die Sichtprüfung nicht. Details: `tools/oberflaeche/README.md`.

## Commits und Pull Requests

- Format: [Conventional Commits](https://www.conventionalcommits.org/) mit Modul in Klammern, z. B. `feat(sondertag): Wunsch-Pop-up`, `fix(punkte): Rundung im Serienbonus`, `docs: Installationsanleitung`.
- Ein Commit ist ein abgeschlossener Schritt mit Tests.
- Pull Requests beschreiben, **warum** die Änderung nötig ist, und nennen die betroffenen Schichten.

## Datenschutz

- Keine echten Namen, E-Mail-Adressen, IP-Adressen oder Domains in Code, Tests, Screenshots oder Doku. Verwende Platzhalter wie `nestwerk.example.org`, `<VM-IP>` oder `Mama`/`Papa` mit Demo-Daten.
- Keine Zugangsdaten, Tokens oder Schlüssel ins Repository. Die `.env` gehört nie ins Git.
