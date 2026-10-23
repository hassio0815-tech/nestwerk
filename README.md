# FamKo

Modulares Familien-Dashboard (Aufgaben, Belohnungen, Spielebene). Django 5.2 LTS, SQLite (WAL), Docker Compose.
Konzept: `docs/SPEC.md`, Architektur: `docs/ARCHITECTURE.md`, Datenmodell: `docs/DATA_MODEL.md`.
Das Betriebs-Runbook (Backup, Update, Rollback) folgt mit AP18.

## Entwickler-Schnellstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate        # legt data/db/famko.sqlite3 an
python manage.py runserver      # http://127.0.0.1:8000/gesundheit/
pytest                          # Tests
ruff check . && ruff format --check .
lint-imports                    # Schichtenregeln (ARCHITECTURE 2.2)
```

Konfiguration per Umgebungsvariablen mit Präfix `FAMKO_` (siehe `.env.example`).
Settings: `famko/settings/{basis,entwicklung,produktion,test}.py`.

## Docker

```bash
cp .env.example .env
docker compose build && docker compose up -d
curl http://127.0.0.1:8000/gesundheit/
docker compose down
```
