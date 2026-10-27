# Contributing to Nestwerk

🇬🇧 **English** · 🇩🇪 [Deutsch](CONTRIBUTING.de.md)

Thanks for your interest. Nestwerk is a family dashboard for your own server. Contributions should keep the family installation secure and easy to understand.

## Ground rules

- **No third-party services:** No analytics, no tracking, no CDN scripts and no external requests from the interface. The check `tools/oberflaeche/screenshots.py` reports every external request as a finding.
- **No third-party brands:** Graphics and names are our own designs. No characters, textures or names from games or other brands.
- **Values in the database:** Rules and starting values live in the database, not in the code. The code contains only definitions and starting values for data migrations.
- **Everything is optional:** No mandatory tasks, no penalties, no point deductions.

## Language

- Code identifiers and code comments are in German by design.
- UI texts use German msgids with English translations. See [docs/en/i18n.md](docs/en/i18n.md).

## Development environment

Requirement: Python 3.13 or newer.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate          # creates data/db/nestwerk.sqlite3
python manage.py runserver        # http://127.0.0.1:8000/gesundheit/
```

Configuration uses environment variables with the prefix `NESTWERK_`. A template is in `.env.example`. The settings modules are `nestwerk/settings/{basis,entwicklung,produktion,test}.py`.

## Checks before every commit

```bash
pytest                            # tests (incl. scenario tests in tests/szenarien)
ruff check . && ruff format --check .
lint-imports                      # layer rules
```

All three commands must pass. The layer rules are defined in `pyproject.toml` (section `tool.importlinter`) and also run as part of the tests.

## Module layers

Nestwerk consists of Django apps with fixed layers. Imports may only point **downward**:

| Layer | Apps |
|---|---|
| 4 UI | `oberflaeche`, `einrichtung` |
| 3 Domain modules | `aufgaben`, `belohnung`, `avatar`, `sondertag`, `familienziel` |
| 2 Shared cores | `punkte`, `ereignisse`, `benachrichtigung`, `spielregeln` |
| 1 Identity | `konten` |
| 0 Base | `kern` |

- Domain modules do **not** import each other. They communicate through domain events and the registry in `kern`.
- Each app exposes only these public interfaces: `services.py` (write), `selectors.py` (read), `events.py` and `registry.py`.
- Other apps' `models.py` are never imported.

Details: `docs/ARCHITECTURE.md` (German), section 2. A guide for new modules is in [docs/en/EXTENDING-MODULES.md](docs/en/EXTENDING-MODULES.md).

## UI screenshots

The tool in `tools/oberflaeche/` creates screenshots with demo data (Python Playwright). It also checks for console errors, CSP violations and external requests.

```bash
.venv/bin/playwright install chromium   # browser cache only
.venv/bin/python tools/oberflaeche/screenshots.py --ziel docs/screenshots/phaseN
```

The demo data is fictional. Look at the PNGs before committing. The heuristics do not replace a visual check. Details: `tools/oberflaeche/README.md`.

## Commits and pull requests

- Format: [Conventional Commits](https://www.conventionalcommits.org/) with the module in parentheses, e.g. `feat(sondertag): wish pop-up`, `fix(punkte): rounding in the streak bonus`, `docs: installation guide`.
- A commit is one completed step, with tests.
- Pull requests explain **why** the change is needed and name the affected layers.

## Privacy

- No real names, email addresses, IP addresses or domains in code, tests, screenshots or docs. Use placeholders such as `nestwerk.example.org`, `<VM-IP>` or `Mama`/`Papa` with demo data.
- No credentials, tokens or keys in the repository. The `.env` file never belongs in Git.
