# Changelog

🇬🇧 **English** · 🇩🇪 [Deutsch](CHANGELOG.de.md)

Entries are derived from the Git history and grouped by project phase. Work package numbers (AP) are listed in `docs/ARCHITECTURE.md` (German), section 12.

## Release preparation (08.11.2026)

### Added
- Security policy, code of conduct, issue and pull request templates, CI workflow and Dependabot configuration (English and German)
- Landing page: localized meta tags, noscript fallback, mobile navigation, dark mode, canonical links, `robots.txt`, `sitemap.xml` and a 404 page
- English architecture overview (`docs/en/ARCHITECTURE.md`) and a documentation index (`docs/README.md`)

### Changed
- Internal reviews, plans, phase screenshots and design drafts moved out of the public repository
- Landing page: the learning module is described as partly finished and continuously developed
- Ruff per-file ignores for fixtures and long lines; tests formatted with `ruff format`
- Private hosts, addresses and names in the documentation replaced by `xxx`

## Points and reflection, stage 14 (08.11.2026)

### Added
- **Points for the process, never per answer:** finishing a practice test (3), a mistake-review round ("Practise my stumbling blocks" with at least 5 answers, 3) and a filled-in look-back (1) each give a fixed amount, at most once per child and day, together with the daily goal (5) always under the daily limit. Settings `lernen.punkte_*`.
- **Rounds count in minutes:** warm-up / normal / challenge are 5 / 10 / 15 minutes with a soft limit (the open question is finished). Setting `lernen.runde_ziel` switches back to counting questions.
- **Break after time:** once per round, after 20 minutes (setting, 0 = off), a break is suggested, not only after frustration.
- **Calibration:** the end of a round says what the child expected and how many answers were right; the start page shows the weekly trend (from 2 rounds).
- **Reason for a mistake:** from grade 6 the child can choose "too fast", "didn't know it" or "miscalculated" after "not yet" (optional, saved on the attempt, the round ends without it).
- **Strategy has a function:** each strategy shows its first step on the question page; new strategies "write it down on paper" and "look at the example first" (opens the maths tip); the maths texts no longer talk about words.

### Changed
- **Daily limit for learning points is 8 (was 10).** A data migration lowers it only if it still has the old default. The "exam prepared" bonus (10) is therefore capped by the limit.
- Browser walkthrough fixes: subject names are translated on the children and levels page; the parents' week view addresses parents informally; the help text for new words no longer promises a per-child setting that has no screen yet.
- The strategy "I say the word out loud" is now "I say it out loud" (also fits maths).

## Relief for parents, stage 13 (07.11.2026)

### Added
- **Exception messages for parents (push):** material waits for approval (once per state, with a link that pre-selects the child's items), a child has not practised for 3 days (never during holidays or a pause, at most once a week), repeated mistakes in one operation type with the matching explanation card (once a week), a test in at most 3 days with under 50 % of the plan done (once per test). Daily job `lernen_eltern_hinweise`; each event exists once per period.
- **Tutor flags go out at once:** a role-change attempt or a held-back answer (solution suspected) is pushed immediately, once per conversation and kind. Plain requests for the solution are not pushed.
- **Weekly digest:** one message per week (default Sunday 18:00, day and time editable, push; mail can be added per parent), at most 8 lines, per child the practised days and one suggestion, open approvals and tests. No comparison between children, no ranking. Job `lernen_digest`.
- **Badge and links:** the parents' learning tile shows how many items wait for approval and links to the list.
- **Own settings page** for learning: daily goal, points, holidays, titles, tutor, new words per day, thinking pause, messages to parents and the list of operation types.

## Spaced repetition and mixing, stage 12 (07.11.2026)

### Added
- **FSRS scheduling:** each practice item now has stability and difficulty (library `fsrs`, pinned, MIT, default parameters, no training). Answers map to Again (not yet), Hard (correct with step 3+ help), Good, Easy (correct without help and faster than the child's median). Target retention 90 %, longest interval 60 days, no fuzzing, a wrong answer comes back tomorrow. Leitner boxes remain as a fallback setting (`lernen.wiederholung_algorithmus`) and apply automatically if the library is missing. Existing items continue from their box.
- **New-vocabulary limit:** 3 / 5 / 7 new words per day (up to grade 5 / grades 6-7 / grade 8+, unknown grade: 3), editable for the whole family (a per-child field exists, its screen follows).
- **Interleaving:** with "everything mixed", at least 30 % of the maths tasks of a round come from earlier operation types (setting).
- **Error type steers selection:** operation types with three or more recognised calculation errors in 14 days come up more often (form errors do not count).

### Changed
- **Exam planner** uses the real due date from the practice state for open reviews and the FSRS interval path (instead of the box grid) for planned ones.

## Learning foundation, stage 11 (07.11.2026)

### Added
- **History that stays:** every practice card now has a stable identity (`Karte`: child, subject, key). Attempts keep the card, topic, days since the previous attempt and the planned due date. Cleaning up generated maths tasks no longer deletes attempts, so the history can grow past 60 days. A data migration fills existing data.
- **Last reflection visible:** the start page shows what helped and what was hard last time. Parents see the last three reflections in the weekly view, and the child is told so.
- **Last choice pre-selected:** the start page remembers the last subject, topic, intention, strategy, expectation and effort.

### Changed
- **Help counts:** a correct answer with help level 3 or higher no longer moves the card forward (it stays in its box). Applies from now on, not to past answers.
- **"Too easy / too hard" works:** the answer from the last reflection shifts the first task of each calculation type in the next session by one step, within the allowed range.

## Learning module (03.11.2026)

### Added
- **Learning (`lernen`):** new module for kids and parents. Everything is optional, and no private data is part of the repository (start data is generic).
- **Practice:** vocabulary and questions with spaced repetition (boxes), intention and strategy before, two reflection questions after, "not yet" instead of "wrong", frustration detection that lowers the level and suggests a break. Help never costs points.
- **Daily goal and streak:** a small minimum day counts, the goal adapts gently to the last two weeks, the streak counts in weeks. Parents can set days off (illness, holidays); a broken streak never removes points.
- **Upload material:** kids add a photo or document to their own learning folder. Questions from uploads wait for the parents' approval unless parents allow them per child. Second entry: files dropped into an `inbox` folder, e.g. on a NAS. The storage is a Docker volume or a mounted folder.
- **Exam preparation:** plan backwards from the exam date with small portions and buffer days, a reality check that makes suggestions instead of a plan that does not fit, and a mock exam.
- **Optional AI with your own provider:** own server with an OpenAI-compatible interface (e.g. Ollama), Anthropic or OpenAI with your own key. **AI is off by default.** Cloud providers need explicit consent, keys are stored encrypted, and a queue works through AI jobs one at a time with retries.
- **Tutor:** explains and helps with a ladder of help steps, but does not solve homework. **Off by default**, switched by parents for the whole family, with a log. The check against leaked solutions is a heuristic, not a guarantee.
- **Practice week and titles:** participation instead of volume. The weekly titles (Practice Master, Climber, Stayer, Explorer) are only a display, give no points and can be switched off. Parents get a weekly picture per child with suggestions, without grades and without sibling comparison.
- **Setup wizard:** four optional steps "Learning" (basics, storage, kids, AI). New registry extension `EinrichtungsSchritt` in `kern` lets modules add skippable wizard steps.
- **Parents page "Children and levels":** change grade, school type, level per subject and the approval of upload questions at any time, using the same services as the wizard. **New school year** raises all entered grades by 1 (up to 13) after a confirmation; learning progress is never deleted.
- **Maths generator:** maths tasks are created locally without AI (random numbers, always calculated solution) for grades 3, 6 and 8: arithmetic, fractions, decimals, percent, units, terms and equations, rule of three, powers and roots. Difficulty adapts to the level, the intensity and the last answers (target 70 to 85 % correct); due repetitions come as new tasks of the same kind. Answers are read generously (comma or dot, fractions, mixed numbers, remainder, `x = 5`, units); parents switch operations on or off in the settings.
- **Maths help (local, without AI):** help ladder with five steps per type of calculation (asking, nudge, similar example with other numbers, calculation tip, solution frame with blanks instead of results), each step only when the child asks, no point deduction. The solution of the real task never appears in the help (property test over all types). **Calculation tips:** explanation cards per type in three language levels, expandable while practising and as a separate area, also for parents. **Error analysis:** recognises typical calculation mistakes (for example a forgotten carry, a denominator calculated too, a misplaced decimal point, order of operations), gives a hint without the solution and a second try; the weekly picture lists the most common error types. Local word problem templates (adjustable share, default 0).
- **Optional AI for maths (off, opt-in only):** formulating word problems (only with the switch and an assigned provider, in the background, output strictly checked, otherwise the local template) and "Explain it differently" (only with the tutor, tutor limits, checked against the solution). Numbers and solution always come from the generator.
- Background jobs `ki_auftraege_verarbeiten`, `lernen_inbox_scannen` and `tutor_aufraeumen` in `deploy/crontab`.
- Documentation: user guide chapter "Learning", installation steps for storage, AI provider and jobs, architecture section 14, data model section 16, section 5a in "Extending modules".

### Notes
- The AI adapters are tested against a fake transport. The module has **not** been tested against a real AI (Ollama, Anthropic, OpenAI) or in a browser.
- Upload requests are limited by the existing `UploadGrenze` middleware from `aufgaben` (about 46 MB per request with default values).
## Parent navigation and "Done today" tile (08.11.2026)

### Changed
- New parent navigation: the header has Home, a gear icon (Settings) and Log out; the side menu has Overview, Weekly plan, Family, Notifications and Dungeon
- Pauses, events, system status and devices moved into Settings; quick access no longer lists duplicate targets
- Family page: one box per member with avatar; the duplicate devices box is gone
- Quick-button starter value "Tidy the room" is worth 20 points; the thorough variant stays at 50

### Fixed
- The "Done today" tile now shows all of today's completions

## Library becomes quick buttons (07.11.2026)

### Changed
- The task library (template UI) is gone; every entry is now a quick button. The old address `/eltern/bibliothek/` redirects to the new "Quick buttons" page. The "Template" model stays as history
- Parents tap a button and choose in a small window: "One for all" (all children are notified), "Each child" (one reserved task per child; children with a running task are skipped) or "One specific child"; "Go" confirms
- New per-button field "Default when pressed" (preselected in the window). Kid and tablet buttons stay as before
- Starter values: every active template becomes a button (data migration plus hourly job). New: "Vacuum the room" (15 pts), "Empty the washing machine" (10 pts); "Zimmer gründlich" is now "Clean and tidy the room thoroughly" (50 pts)
- Kid page: the button tile and the task list refresh together, the notice shows only once

### Fixed
- An invalid child in a button press shows a notice instead of a 500 error; kids can no longer report a button assigned to another child
- "Split task per child": running and finished instances follow their child; active tasks only; command with `--dry-run`, collects errors per ID
- Duplicate protection when creating a task (same title, repeat and assignment) with an "create anyway" box; "For every child" without active children shows a notice
- Hygiene: `.gitignore` and `.dockerignore` (backups, wheels, `.env.*`, handoffs)

## Recognition, My settings and moods (02.11.2026)

### Added
- **Recognition (parents):** give points without a task. New booking type "Recognition" (1 point = 1 balance and 1 XP), note required, parents only. 1 to 25 points per award, at most 50 points per child per week (Monday to Sunday); both limits are parent settings (`aufgaben.anerkennung_max_punkte`, `aufgaben.anerkennung_woche_max`). The child gets a push message, the points count for XP and the family goal, and a reversal frees the weekly room again
- **My settings (kids):** gear icon in the header. Name (unique, case-insensitive), optional nickname (shown in the greeting and tiles), change code (old code required, new code twice; wrong attempts count and lock like at login)
- **Moods:** catalogue of 50 kid-friendly moods (memes, movies, tired, happy, grumpy, calm) plus "No mood". The chosen mood appears as a small line under the name on the start page and on the kid dashboard
- **Mood suggestions:** kids suggest new moods (at most 40 characters, at most 3 open). Parents see a counter and list under "Moods", approve or decline, hide catalogue moods and add their own. Approved moods apply to all kids. Push to the parents for a new suggestion, to the kid for the decision
- Kid dashboard: "Latest points" (point history including recognition and its note)

### Changed
- Parents can reset a child's code at any time (Family area); now covered by tests

## Quick buttons (30.10.2026)

### Added
- Quick buttons: "on demand" tasks (e.g. general waste) that sleep until someone presses the button; one press creates exactly one open task
- Two modes: "I'll do it" (reserved for the kid) and "Just report it" (open for all, notification to the kids)
- Tiles for parents, kids and the hallway tablet (no PIN there, only on the registered kiosk device)
- Task form: repeat option "On demand", emoji and "Who may press it?"
- Library templates General waste, Organic waste and Recycle glass (5 points)

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
- Final review phase 3 (AP36)

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
