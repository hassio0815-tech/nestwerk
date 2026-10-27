# Changelog

🇬🇧 **English** · 🇩🇪 [Deutsch](CHANGELOG.de.md)

Entries are derived from the Git history and grouped by project phase. Work package numbers (AP) are listed in `docs/ARCHITECTURE.md` (German), section 12.

## Bilingual release: German and English (27.10.2026)

### Added
- UI in German and English, with a language switch on the start screen
- Per-user language; family language for notifications
- Push and email notifications are sent in the recipient's language
- English documentation in `docs/en/`

## Renamed to Nestwerk (25.10.2026)

Until now the project was called **FamKo**; it is now called **Nestwerk** (subtitle: "Nestwerk – the family hub for chores, rewards & learning"). License: AGPL-3.0-or-later.

### Changed
- Django project package `famko/` is now `nestwerk/`; Docker, deploy and documentation files, UI, PWA name and default app name use the new name
- Environment variables: prefix `NESTWERK_*`. The old `FAMKO_*` variables remain as fallback (centrally in `apps/kern/umgebung.py`)
- New installations use `/opt/nestwerk`, Compose project `nestwerk`, volume `nestwerk_data`, image `nestwerk:<tag>`, firewall `/etc/nestwerk`, database `nestwerk.sqlite3`
- `LICENSE` (GNU AGPL-3.0); `docs/LIZENZ-OFFEN.md` is removed, the license notice is in the README

### Compatibility (existing FamKo installations)
- `deploy/update.sh` detects an old `.env` (with `FAMKO_*`) and the old volume and writes project, volume and image names into the `.env`; no data loss, no manual renaming needed
- The existing database file `famko.sqlite3` and backups `famko-*.sqlite3.gz` are still recognized; app labels and migrations are unchanged
- Details: `docs/en/RUNBOOK.md`, section "Converting an existing FamKo installation"

## Phase 3: Polish (25.10.2026)

### Added
- Forecast and calibration view with one-click apply (AP32)
- Hall of fame: heroes on pedestals, dedications and badges (P3-A)
- Uniform, animated pop-ups (confetti, rank-up, hall of fame) that respect "reduced motion" (AP33)
- Documentation for sharing: installation, user guide, extending modules, sanitized sample data

### Changed
- Hall of fame only appears once all build orders in the current theme are finished (AP36)
- `deploy/install.sh` points to `docs/INSTALLATION.md` at the end (AP36)
- Final review phase 3: `docs/reviews/REVIEW_PHASE3.md` (AP36)

### Still open
- God-mode mod sets and further mods, AP34
- Price and build time per mod, themes on/off in the parent dashboard (P-15)

## Phase 2: Game layer (23.10. to 24.10.2026)

### Added
- Rule engine `spielregeln`: activity, pauses for child or family, weekly evaluation, streak and daily streak (AP20)
- Streak bonus when tasks are confirmed (AP21)
- Ranks with thresholds, active weeks and calibration factor (AP22)
- Generic badge and milestone engine with metric registry (AP23)
- Avatar generator: deterministic SVG block figures, themes and SVG whitelist (AP24)
- 10 themes with 36 mod blueprints each (AP25)
- Mod shop with purchase via the ledger, build time, upgrade level and theme change with warning (AP26)
- Special day: entitlements from milestones, limits, wish, companion and acceptance (AP27)
- Badge graphics (AP28)
- Family goal with weekly progress, voting and big goal (AP29)
- Family ranking with Hero of the Week and switchable mode (AP30)
- Data protection: retention periods for events, deliveries and notifications (B-15)
- Special-day job in the crontab, notification "redeemable now"

### Fixed
- Quiet hours are checked again before each send (B-19)
- Late confirmations count in the week of the activity
- Big goal counted exactly once per cycle
- Tablet works without htmx-eval (CSP), no overflow at 390 px, font size from 14 px
- ISO date format for pauses

### Review
- Review phase 2 (AP31): scenario tests over 52 weeks and three app years, comparison of DATA_MODEL and ARCHITECTURE with the code (B-22)

## Phase 1: Core (23.10.2026)

### Added
- Project scaffold, settings registry, time utilities, audit log and job locks (AP01, AP02)
- Design system and base templates (AP06)
- Transactional outbox for domain events with worker (AP05)
- Users, parent login, child PIN with rate limit and kiosk sessions (AP03)
- Immutable points ledger with idempotent booking (AP04)
- Notifications: router, preferences, quiet hours, email, pop-up, PWA manifest and web push (AP07, AP08)
- Tasks: categories, library, recurrence and instance creation, reservation, proofs with EXIF removal, confirmation and bonus points, weekly planner with drag and drop (AP10 to AP14)
- Rewards: catalog, redemption requests, monthly allowance limit (AP15)
- Setup assistant with setup token (AP16)
- Dashboards for kids, parents and tablet, settings editor, family management (AP17)
- Operations: crontab scheduler, database backups, backup test, update and rollback, runbook (AP18)

### Fixed and hardened
- Layer rules with import-linter, read access only via selectors (AP19)
- Security: X-Forwarded-For uses only the rightmost entry, CSP header, sessions reset on password change and device revocation, tight file permissions, deep links internal only
- Web push endpoints restricted to allowed push services (B-14)
- Proof photos never attached to someone else's submission; upload limit
- One write lock for points and rewards (concurrency)
- Healthcheck host always allowed
- Installer and update: bundle instead of Git remote, git safe.directory, egress block for containers
- UI: mobile weekly planning, touch targets, font sizes
