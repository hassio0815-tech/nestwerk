# Nestwerk: architecture overview

🇬🇧 **English summary** · 🇩🇪 [Deutsch (full document)](../ARCHITECTURE.md)

This is a short English overview. The full, authoritative document is the German [ARCHITECTURE.md](../ARCHITECTURE.md). Code identifiers are German by design (for example `aufgaben` = tasks, `belohnung` = rewards, `punkte` = points, `kern` = core).

## 1. Principles

- **Stack:** Python 3.13, Django 5.2 LTS, Gunicorn, HTMX, SQLite (WAL), Docker Compose.
- **Values live in the database.** The code holds only definitions (key, type, validation) and starting values for data migrations. At runtime no code default is read.
- **Time:** stored as UTC; business days and weeks use the family time zone (setting). Week = ISO week, Monday to Sunday. One utility (`kern.zeit`) is the only place that decides "today", "ISO week" and "app year".
- **One installation = one family.** No multi-tenancy.
- **Consistency before elegance:** points and rules are booked in a single database transaction through direct service calls. Domain events carry only side effects (notifications, badges, pop-ups, other modules).
- **Idempotency everywhere:** each creation has a business uniqueness key (database constraint); each status change is a conditional `UPDATE ... WHERE status = old`.

## 2. Layers and apps

| Layer | Apps | Role |
|---|---|---|
| 4 UI | `oberflaeche`, `einrichtung` | Layouts, dashboards for kids, parents and tablet, PWA, setup assistant |
| 3 Domain modules | `aufgaben`, `belohnung`, `avatar`, `sondertag`, `familienziel` | Tasks and proofs, rewards, avatars and mods, special day, family goal |
| 2 Shared cores | `punkte`, `ereignisse`, `benachrichtigung`, `spielregeln` | Points ledger, event bus with outbox, notifications, rule engine |
| 1 Identity | `konten` | Users, parent login, kid PIN, devices, rate limits |
| 0 Base | `kern` | Settings registry, time utilities, audit log, job locks, module registry |

Further modules (such as learning) are Layer 3 apps that plug in through the registry and events.

## 3. Dependency rules

- Imports point **downward only**.
- Domain modules **never import each other**. They communicate through **domain events** and the **registry** in `kern` (metric providers, progress providers, dashboard tiles, event types).
- Each app exposes only `services.py` (write), `selectors.py` (read), `events.py` and `registry.py`. Other apps' `models.py` are never imported.
- The rules are enforced by `import-linter` (contracts in `pyproject.toml`, section `tool.importlinter`), run by `lint-imports` and in the test suite.
- Dashboards render **tiles** from the registry. Each module registers its tiles in `AppConfig.ready()`, so a new module adds tiles without touching `oberflaeche`.

Example without a direct import: confirming a task calls, in one transaction, `spielregeln.services.aktivitaet_erfassen`, the streak bonus service and `punkte.services.buchen`. A special-day entitlement instead arises from an event (`meilenstein.erreicht`) that `sondertag` handles.

## 4. Runtime topology

One image, three containers:

| Container | Role |
|---|---|
| `web` | Gunicorn + Django + WhiteNoise: HTTP, templates, HTMX, protected proof images |
| `worker` | Works the event outbox, delivers push and e-mail, retries with backoff |
| `scheduler` | `supercronic` runs timed management commands (weekly evaluation, backups, retention) |

- No Redis or Celery: the queue is the outbox table in SQLite. This is enough for a family.
- SQLite is shared by three processes. It runs in WAL mode with `transaction_mode: IMMEDIATE`, a busy timeout and short transactions; no network I/O inside a transaction. The data volume must be on a local disk, never NFS or SMB.
- The app listens on the VM's LAN address only; TLS is terminated by a reverse proxy in front.
- Secrets (Django key, VAPID key, Fernet key) are generated on first start with mode 600 and belong in the backup.
- Backups: daily online backup through the SQLite backup API with integrity check and gzip, with daily, weekly and monthly retention. See [RUNBOOK.md](RUNBOOK.md).

## 5. Events and notifications

- `ereignisse.veroeffentlichen(...)` writes an event row **in the same transaction** as the change (transactional outbox). A rollback means no event.
- Handlers are mostly **asynchronous** (worker). Each handler runs exactly once per event (`unique(event, handler)`), with retries; failures show in the system status. Synchronous handlers are rare and stay inside Layer 2.
- Event types are declared in each module's `events.py` and synchronized into the database on `migrate`. Name, audience and default channels are editable.
- Notifications are routed by recipient preferences and quiet hours (checked again before each send) and delivered as web push, e-mail or in-app pop-up in the recipient's language.

## 6. Rule engine (`spielregeln`)

- All states (streak, active weeks, rank, upgrade level) can be **recomputed from history**. Stored values are caches that can be rebuilt with `manage.py spielregeln_neuberechnen`. Reached ranks, awarded badges and reached milestones are permanent facts.
- **Active week:** at least one non-cancelled activity in the ISO week. **Neutral week:** not active but covered by a pause. **Streak:** active +1, neutral unchanged, otherwise 0.
- **Reference date:** the report date counts, and a week is finalized only after a buffer, so late parent confirmations do not break streaks.
- **Streak bonus:** a percentage of the base points, with start, step and cap as settings; booked as its own ledger entry in the same transaction.
- **Ranks:** thresholds on XP and minimum active weeks, with a calibration factor. A rank never drops.
- **Badges and milestones:** generic definitions on top of metric providers that modules register. Milestones can create special-day entitlements.
- **Family goal and hero of the week** are computed from the weekly points; the forecast view helps parents calibrate thresholds.

## 7. Avatars and proofs

- Avatars are deterministic SVG block figures, generated from the theme and the owned mods and passed through an SVG whitelist.
- Proof photos are stored privately, have their EXIF data removed, are served through a protected view and are deleted after a retention period.

## 8. Tests

- Unit and service tests per app, scenario tests over 52 weeks and three app years (`tests/szenarien`), a migration test and the layer rules.
- `tools/oberflaeche/` renders screenshots with demo data and reports console errors, CSP violations and external requests.

For details (data model, event catalogue, scheduler jobs, work packages and open points) see the German [ARCHITECTURE.md](../ARCHITECTURE.md), [DATA_MODEL.md](../DATA_MODEL.md) and [SPEC.md](../SPEC.md).
