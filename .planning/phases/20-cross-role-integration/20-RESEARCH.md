# Phase 20: Cross-Role Integration — Research

**Researched:** 2026-04-17
**Domain:** End-to-end Playwright cross-role scenarios + manual smoke checklist + doc sweep
**Confidence:** HIGH

## Summary

Phase 20 is the v1.2-prod acceptance gate. The three role pillars (participant Phase 15,
admin Phases 16/17/18, organizer Phase 19 rescoped) have all shipped. The job now is to
prove they compose — one event driven admin → organizer → participant → admin audit log —
and to clean stale copy from the few docs that still reference retired concepts.

The existing Playwright suite has 5 spec files running across 6 device projects (Chromium,
Firefox, WebKit, Pixel 5, iPhone 12, iPhone SE 375). All infrastructure Phase 20 needs
already exists: `EXPOSE_TOKENS_FOR_TESTING=1` exposes `confirm_token` from signup
responses, `seed_e2e.py` idempotently seeds an event + slots + organizer + admin, the
`test_helpers` router (`seed-cleanup`, `event-signups-cleanup`) handles re-run cleanup,
rate limits are bypassed in test mode, and slot capacity 200 prevents parallel-worker
exhaustion. CI (`.github/workflows/ci.yml`) already boots docker compose and runs
`npx playwright test` across all projects.

**Primary recommendation:** Write 4–5 new cross-role specs in `e2e/` that compose existing
patterns (admin login from `admin-smoke`, public signup from `public-signup`, organizer
check-in from `organizer-check-in`). Do NOT extract a shared helpers module in this phase —
`admin-a11y.spec.js` already flagged that as a future refactor; doing it now expands PR
surface. Write `docs/smoke-checklist.md` as a plain markdown checklist driven by a
single running docker stack. The doc sweep is small: `IDEAS.md` is the only source file
with live stale "yearly" references; `README.md` is effectively empty and needs a real
v1.2-prod writeup.

<user_constraints>
## User Constraints

**No CONTEXT.md exists for Phase 20 yet.** This research is the input to `/gsd-discuss-phase`
or `/gsd-plan-phase 20`. Constraints below are inferred from CLAUDE.md, the ROADMAP, and the
REQUIREMENTS doc.

### Locked Decisions (from CLAUDE.md + ROADMAP + REQUIREMENTS-v1.2-prod.md)

- **No new product capabilities.** Phase 20 is test + doc sweep only. Any cross-role bug
  surfaced is either fixed or filed as an explicit out-of-scope follow-up (INTEG-05).
- **Docker-network test pattern** is mandatory for backend tests (CLAUDE.md).
- **Loginless participants.** No volunteer accounts anywhere in scenarios.
- **Branch:** Phase 20 runs on `main` (or a new `feature/v1.2-integration` short-lived
  branch merged via PR) — it's the shared integration phase. The currently checked-out
  branch is `v1.2-final` (merge branch from c27cd25).
- **`docs/smoke-checklist.md` is a NEW file** (not found on disk).
- **Andy is the single Alembic writer** — unlikely to matter for Phase 20 (no schema
  changes expected), but if any INTEG-05 bug fix needs a migration, Andy writes it.
- **PR-only files** (per `docs/COLLABORATION.md`) include `frontend/src/lib/api.js`,
  `frontend/src/App.jsx`, `CLAUDE.md`, `README.md`, `.github/workflows/*`,
  `docker-compose.yml`, `.planning/STATE.md`, `.planning/ROADMAP.md`,
  `.planning/REQUIREMENTS-v1.2-prod.md`, `docs/COLLABORATION.md`. Several of these are
  directly in the doc-sweep target list (INTEG-06) — coordinate with Hung before landing.
- **Playwright suite green in CI on every PR** is a hard gate (INTEG-03).

### Claude's Discretion

- Exact count and structure of new cross-role scenarios (4 minimum per INTEG-02;
  recommending 4–5 below, one per composition pattern).
- Smoke checklist depth and format (plain markdown vs. script + markdown).
- Whether to extract a shared `e2e/helpers/login.js` module (recommend: NOT this phase).
- Naming conventions for new spec files (recommend: `cross-role-*.spec.js`).
- Which doc-sweep occurrences in archived `.planning/phases/` to touch (recommend:
  NONE — those are frozen historical artefacts per `docs/ORG-AUDIT.md` line 97).

### Deferred Ideas (OUT OF SCOPE)

- UCSB production deployment (Phase 8, separate milestone).
- Roster polish / end-of-event prompt / ORG-14 / organizer WCAG audit (v1.3).
- Participant accounts, AI matching, WebSockets, i18n, multi-tenant.
- Extracting a shared e2e helpers module (deferrable refactor; flagged in
  `admin-a11y.spec.js` comment).
- Fixing the latent Alembic downgrade-enum round-trip bug.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTEG-01 | Cross-role E2E: admin creates event → organizer manages roster → participant signs up → admin sees signup + check-in in audit log | See "Proposed Cross-Role Scenarios" § Scenario 1 below; uses existing admin-smoke login + public-signup form + organizer-check-in pattern + audit-logs page |
| INTEG-02 | ≥4 new cross-role Playwright scenarios on top of v1.1's 16 | See "Proposed Cross-Role Scenarios" — 5 proposed, one per composition pattern |
| INTEG-03 | Full Playwright suite green in CI on every PR | CI already runs `npx playwright test` with no grep filter; new specs automatically picked up. See `.github/workflows/ci.yml` lines 236–242 |
| INTEG-04 | Manual smoke pass per `docs/smoke-checklist.md` (new file) | See "Smoke Checklist Structure" § below |
| INTEG-05 | Cross-role bugs fixed or filed as explicit out-of-scope | See "Expected Bug Surfaces" § — what to watch for during integration runs |
| INTEG-06 | Doc sweep: PROJECT.md, README, CLAUDE.md, in-app copy reflect v1.2-prod | See "Stale Reference Inventory" § — precise file:line list |
</phase_requirements>

## Existing Playwright Inventory (baseline)

5 spec files in `/Users/andysubramanian/uni-volunteer-scheduler/e2e/`:

| Spec | Tests | Pattern | Relevance to Phase 20 |
|---|---|---|---|
| `public-signup.spec.js` | 7 tests (serial describe) | Full participant flow: browse → event detail → select orientation+period slots → form → confirm_token → confirm → manage → cancel one → cancel all | Canonical participant flow — reuse `clickSlotByLabel`, identity-form fill pattern |
| `organizer-check-in.spec.js` | 1 test | Direct API signup + confirm, then UI login as organizer → roster → click row → assert `checked in` chip | Canonical organizer roster flow — reuse login helper + roster row locator |
| `orientation-modal.spec.js` | 2 tests | Period-only signup triggers modal (Test A); attended volunteer suppresses modal (Test B via `GET /orientation-status`) | Reference for modal copy (`Have you done a Sci Trek orientation?`) — not needed directly in cross-role specs |
| `admin-smoke.spec.js` | 5 tests | Shallow: login → `/admin` → `/admin/audit-logs` → `/admin/templates` → `/admin/exports` each load without crash | Canonical admin login + page-load pattern — reuse `loginAsAdmin` pattern |
| `admin-a11y.spec.js` | 7 tests | axe-core sweep of every admin route at 1280×800 + event detail | Confirms `/admin/audit-logs` + all admin routes are mountable. Contains the comment flagging a future shared helpers extraction — defer per CLAUDE's-discretion above |
| `a11y.spec.js` | ~12 dynamic tests | axe-core WCAG 2.1 AA sweep of every public route + 375px h-scroll assertion on iPhone SE 375 project | Confirms public routes mount cleanly; irrelevant to cross-role scenarios |

**Total test counts are approximate — Playwright multiplies each test by 6 device
projects per `playwright.config.js`. The ROADMAP's "16 scenarios from v1.1" likely
refers to unique test names, not project-multiplied runs.**

**Key fixtures** (`e2e/fixtures.js`):
- `ADMIN = { email: 'admin@e2e.example.com', password: 'Admin!2345' }`
- `ORGANIZER = { email: 'organizer@e2e.example.com', password: 'Organizer!2345' }`
- `VOLUNTEER_IDENTITY` + `ephemeralEmail(tag)` for collision-free per-test emails
- `getSeed()` reads `process.env.E2E_SEED` — JSON blob from `seed_e2e.py` with
  `event_id`, `period_slot_id`, `orientation_slot_id`, `confirm_token`,
  `a11y_confirm_token`, `attended_volunteer_email`, `portal_slug`, etc.

**Global setup** (`e2e/global-setup.js`): shells out to
`backend/tests/fixtures/seed_e2e.py` against the running backend, captures the
last JSON line of stdout into `process.env.E2E_SEED`. Idempotent.

**Test-only backend router** (`backend/app/routers/test_helpers.py`, gated by
`EXPOSE_TOKENS_FOR_TESTING=1`):
- `DELETE /api/v1/test/seed-cleanup?emails=a@b.com,c@d.com` — deletes cancelled
  signups for those emails (works around UNIQUE(volunteer_id, slot_id) on re-run)
- `DELETE /api/v1/test/event-signups-cleanup?event_id=X&keep_emails=...` — cancels
  non-essential signups to prevent capacity exhaustion

## Proposed Cross-Role Scenarios (≥4 new, INTEG-02)

All live in a new file `e2e/cross-role.spec.js` (or split per scenario if they
get long — start with one file). Each scenario opens ONE Playwright page and
switches roles by logging out + logging in; running multiple browser contexts
side-by-side is a later-phase refinement.

### Scenario 1 — Admin creates → participant signs up → organizer checks in → admin sees in audit log (INTEG-01, the canonical one)
**Steps:**
1. Login as admin → navigate to admin event detail for the seeded `event_id`
   (event creation UI is admin-managed; the seed already creates one, so
   "admin creates" is satisfied by the seed — document this in the spec
   comment. If Andy wants a literal admin-creates-via-UI step, the admin event
   create form lives at `/admin/events/:id` edit flow; inspect
   `AdminEventPage.jsx` first.)
2. Log out → go to `/events` → open event → select period slot → submit form
   with `ephemeralEmail('xrole-1')` → capture `confirm_token` from POST
   response → GET `/signup/confirm?token=...` → expect "confirmed" banner.
3. Login as organizer → navigate to `/organizer/events/:id/roster` → click the
   new signup row → expect status chip flips to "checked in".
4. Log out → login as admin → navigate to `/admin/audit-logs` → filter by
   actor email OR search the volunteer's ephemeral email → expect two entries
   (`signup.created` + `signup.checked_in`, or whatever `kind` values audit
   emits — verify by reading `AuditLogsPage.jsx` once).

### Scenario 2 — Admin sees live overview stats update after participant signs up
**Steps:**
1. Login as admin → `/admin` → capture current "Signups (all time)" count
   from `OverviewSection.jsx` (text: `{n} students have signed up`).
2. Log out → public signup flow (like Scenario 1 steps 2).
3. Login as admin → `/admin` → assert count incremented by 1.

This is a small scenario but tests the live-DB wiring of the Overview (ADMIN-04).

### Scenario 3 — Organizer can see a freshly-created signup reach their roster without reload
**Steps:**
1. Login as organizer → navigate to `/organizer/events/:id/roster` → capture
   current "X of Y checked in" header count.
2. Direct API POST to `/api/v1/public/signups` (same pattern as
   `organizer-check-in.spec.js`) with a fresh ephemeral email, slot = seed's
   `period_slot_id`. Confirm via token.
3. Wait 6 seconds (the 5s poll interval from ORG-07 + buffer) OR reload the
   page — assert the new row appears in the roster list.

Tests the organizer 5s polling behaviour end-to-end (ORG-07 is in v1.3 scope,
but 5s polling already exists in `OrganizerRosterPage.jsx` from Phase 3). If
polling is broken or absent, this test catches it; downgrade to a reload-based
assertion with a comment if polling turns out to be more fragile than expected.

### Scenario 4 — Cancel flow surfaces in admin audit log
**Steps:**
1. Public signup → confirm (same as Scenario 1 steps 2).
2. Navigate `/signup/manage?token=...` → cancel the signup via UI.
3. Login as admin → `/admin/audit-logs` → search for the volunteer's email →
   expect both `signup.created` and `signup.canceled` entries.

Validates the cancel path's audit wiring and the manage page's UI.

### Scenario 5 — Organizer-scoped RBAC: organizer can't reach admin-only pages
**Steps:**
1. Login as organizer.
2. Attempt to navigate to `/admin/users` → expect redirect to `/organizer` OR a
   403/empty state (inspect `ProtectedRoute` behaviour in `App.jsx`).
3. Attempt to navigate to `/admin/audit-logs` → expect same.
4. Attempt to navigate to `/admin/exports` → expect same.
5. Navigate to `/admin/templates` → should load (templates are shared admin +
   organizer surface per `docs/ORG-AUDIT.md` line 31).

Tests the Phase 19 RBAC work holds up. Small but high-value because RBAC
regressions are silent — you don't get a stack trace, you get a security bug.

**Minimum for INTEG-02: Scenarios 1, 2, 3, 4 (4 new).** Scenario 5 is a bonus
that also serves as a regression guard for Phase 19.

## Smoke Checklist Structure (`docs/smoke-checklist.md`)

**Format:** Plain markdown with checkbox sections. No script automation — the
point is human eyes on the product.

**Preconditions:**
- Fresh docker stack: `docker compose down -v && docker compose up -d` and
  `docker compose run --rm migrate`.
- Seed: run `EXPOSE_TOKENS_FOR_TESTING=1 python3 backend/tests/fixtures/seed_e2e.py`
  OR trigger it via Playwright globalSetup OR manually create an event via admin
  UI (if Andy wants the "no-seed" path documented).
- Three browser tabs open: admin (logged in), organizer (logged in on a phone
  emulator or narrow window), participant (clean/incognito).

**Section proposals:**
1. **Participant flow (phone-sized window, 375px)** — 8–10 checkboxes covering
   every route from `/events` through `/signup/manage`. Mirror the PART-01..14
   success criteria. Call out: no horizontal scroll, no console errors, no
   stuck spinners, 44px tap targets.
2. **Admin flow (desktop, 1280px)** — 8–10 checkboxes covering every sidebar
   item: Overview / Audit Log / Users / Templates / Imports / Portals /
   Exports / Help. Mirror Phase 16 success criteria.
3. **Organizer flow (phone)** — 4–6 checkboxes: login, `/organizer` dashboard
   (Today tab default, tab switch to Upcoming, tap "Open roster"), roster
   view, check-in a signup, logout.
4. **Cross-role loop** — 6 checkboxes that mirror Scenario 1 above but done by
   human fingers in three tabs. This is the INTEG-04 "all three roles in one
   sitting" requirement.
5. **Regressions to watch** — 4–6 bullets of known-gotcha checks: modal copy,
   audit log entries visible, magic link email actually arrives (check Mailpit
   on `localhost:8025`), no console errors in any role, no failed network
   requests in any role (DevTools Network tab should be all green).

**Exit criteria:** every box checked in one sitting, no manual DB nudges, no
failed requests. Sign off with date + reviewer initials.

## Stale Reference Inventory (INTEG-06 doc sweep)

### Live code — already clean

Confirmed via grep on `frontend/src` + `backend/app` + `docs/`:
- **"yearly" / "annually"** — ZERO occurrences in `frontend/src` or
  `backend/app`. In `docs/`: only `docs/ADMIN-AUDIT.md` line 50, which is a
  correctness note ("not yearly — quarterly") and should stay.
- **"student account" / student register / student login** — ZERO occurrences
  in `frontend/src` or `backend/app`. `frontend/src/pages/UsersAdminPage.jsx`
  line 157 reads "other admins — students don't have accounts" which is
  CORRECT copy and should stay. References to "student_name" as a DB column
  are model-level and correct.
- **`/organize` (legacy route, not `/organizer`)** — ZERO code references.
  Only `frontend/src/App.jsx` line 78 (the `RedirectOrganizeRoster` catch-all),
  which is deliberate per Phase 19-01. Keep.
- **"Overrides"** — retired in Phase 16. Verified by `scripts/verify-overrides-retired.sh`.
  Occurrences remaining are in frozen `.planning/phases/` artefacts
  (historical) and in `backend/app/models.py` / `magic_link_service.py` where
  they refer to different concepts (e.g. env overrides). No action.

### Live code — needs sweep

| File | Line | Current | Action |
|---|---|---|---|
| `IDEAS.md` | 142 | "Event Template System + LLM-Normalized CSV Import (yearly ops win + real AI surface)" | Rewrite to "quarterly ops win" — this is the headline claim, wrong per CLAUDE.md |
| `IDEAS.md` | 196 | "Who does the yearly upload" | Rewrite: "quarterly upload" |
| `IDEAS.md` | 218 | "CSV import UI for yearly event generation" | Rewrite: "quarterly event generation" |
| `IDEAS.md` | 266 | "yearly ops win + real AI surface" | Rewrite: "quarterly ops win + real AI surface" |
| `IDEAS.md` | 278 | "What does the current yearly event CSV look like?" | Rewrite: "quarterly event CSV" |
| `README.md` | entire file | Just "# uni-volunteer-scheduler" | Write a real v1.2-prod README: stack summary, how to boot the docker stack, how to run tests (link CLAUDE.md), link to `docs/smoke-checklist.md`, quick role tour (admin / organizer / participant URLs), link to .planning/ROADMAP.md |
| `CLAUDE.md` | lines 6–8 | Calls project "v1.2-prod milestone — production-ready by role" but keep the "phases 0–7 code-complete" language at bottom from pre-v1.2 | Update the closing "Planning harness" paragraph (lines 67–71) to say phases 0–20 complete post-Phase 20 merge |
| `.planning/PROJECT.md` | line 137 | "Autonomous run introduced student accounts" | Keep — this is historical record, a decisions-log entry. Intentional. |

### Archived artefacts — DO NOT sweep

Per `docs/ORG-AUDIT.md` line 97 and the CLAUDE.md teaching pattern, frozen
phase dirs (`.planning/phases/00-*` through `19-*`) are historical artefacts.
Even if they contain "yearly", "student account", "/organize", or "Overrides"
references, leave them alone. Future readers should treat them as
of-the-time-of-writing.

This decision applies to: all `.planning/phases/*/` files,
`.planning/research/*.md`, `.planning/REQUIREMENTS-v1.1-accountless.md`,
`.planning/REQUIREMENTS.md` (original v1.0 requirements).

### In-app copy sweep — manual visual check

Beyond grep, do one manual 5-minute pass of every route in the smoke
checklist looking for stale copy. Likely empty (the Phase 15 + 16 audits
already caught most of it) but cheap insurance.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Cross-role login helpers | A shared `loginAs()` module | Inline copy-paste of the 5-line admin-smoke pattern | `admin-a11y.spec.js` already flagged the extraction for a future phase; inlining keeps the PR diff scoped to "new specs only" |
| Seed setup per scenario | Custom per-spec fixtures | Reuse `seed_e2e.py` via globalSetup + `getSeed()` | Idempotent, well-tested, handles the UNIQUE constraint correctly |
| Cleanup between scenarios | Manual DB queries | The existing `/api/v1/test/seed-cleanup` + `/api/v1/test/event-signups-cleanup` endpoints | Already built and tested; ephemeral emails avoid most cleanup needs |
| Direct DB access from specs | psycopg in specs | `fetch()` to `http://localhost:8000` or backend routes via Playwright | DB isn't exposed to host (docker-network pattern); fetch is what `organizer-check-in.spec.js` already does |
| Parallel-worker slot contention | Per-worker events | Existing capacity-200 on seed event | v1.1 Phase 13 already solved this; just use ephemeral emails |

## Common Pitfalls

### Pitfall 1: Serial describe blocks breaking parallel runs
**What goes wrong:** `public-signup.spec.js` uses `test.describe.serial` because
tests share a `token` variable. A cross-role spec that follows the same
pattern but doesn't need serial execution will pay a worker-count penalty.
**How to avoid:** For Scenario 1 (which threads a single token through admin
→ participant → organizer → admin), use serial. For Scenarios 2–5 which are
independent, use default parallel. Match the scope to the need.

### Pitfall 2: Audit log search is async / eventually-consistent
**What goes wrong:** After a signup action, the audit log entry may take a
moment to appear (async Celery write on some actions? Check Phase 7 audit
wiring). A test that does "signup → immediately assert audit entry" can flake.
**How to avoid:** Use `page.waitForResponse` on the relevant API call, then
poll the audit log page with `expect(...).toBeVisible({ timeout: 10000 })`.
Inspect `backend/app/routers/admin.py` audit logic before writing Scenario 1
step 4 to confirm whether audit writes are synchronous.

### Pitfall 3: `confirm_token` absent when `EXPOSE_TOKENS_FOR_TESTING` unset
**What goes wrong:** Specs relying on `signupBody.confirm_token` will silently
skip or fail cryptically if the env var isn't set on the backend.
**How to avoid:** CI sets it explicitly in `ci.yml` line 202. For local runs,
check `backend/.env`. `public-signup.spec.js` line 119 already has a
defensive `expect(..., 'confirm_token missing — EXPOSE_TOKENS_FOR_TESTING=1 must be set').toBeTruthy()` —
copy that pattern.

### Pitfall 4: Rate limiter kicks in during parallel runs
**What goes wrong:** 4 Playwright workers hammering `/public/signups` from
the same localhost IP can blow the 10/min rate limit.
**How to avoid:** Already solved — rate limit is bypassed when
`EXPOSE_TOKENS_FOR_TESTING=1`. No action, just confirm env var is set.

### Pitfall 5: Organizer can reach `/admin/templates` — not a bug
**What goes wrong:** Scenario 5 (RBAC check) might fail for templates path
because templates is a shared admin+organizer surface (see `docs/ORG-AUDIT.md`
line 31 + `App.jsx` line 82 — `ProtectedRoute roles={["admin", "organizer"]}`).
**How to avoid:** Assert templates/imports/events pages load (positive),
assert users/audit-logs/exports redirect (negative). Don't invert the list.

### Pitfall 6: React-router legacy `/organize/` redirect breaks if new code adds absolute links
**What goes wrong:** Any code that hard-codes `/organize/events/:id/roster` (no
`r`) will hit the Phase 19-01 redirect — a 301-equivalent `<Navigate>` bounce.
**How to avoid:** Grep for `/organize` (no `r`) in any cross-role spec or
smoke doc before landing it. Only the intentional redirect catch-all should
match.

### Pitfall 7: Doc-sweep touches a PR-only file without Hung approval
**What goes wrong:** `README.md`, `CLAUDE.md`, `.github/workflows/ci.yml`,
`docker-compose.yml`, `.planning/ROADMAP.md`, `.planning/STATE.md` are all
PR-only per `docs/COLLABORATION.md`. Phase 20's doc sweep explicitly touches
some of these — landing without PR breaks the collaboration contract.
**How to avoid:** All doc-sweep changes go in one PR at the end of Phase 20,
explicitly reviewed by Hung. Do not push directly to `main`.

## Runtime State Inventory

Phase 20 is a test-authoring + doc-sweep phase. No renames or schema changes
anticipated.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no DB migrations expected | None |
| Live service config | None — no n8n / external services involved | None |
| OS-registered state | None — no OS-level registrations | None |
| Secrets/env vars | `EXPOSE_TOKENS_FOR_TESTING` is the only env var Phase 20 cares about; already set in CI and expected in `backend/.env` for local. No new vars. | None |
| Build artifacts | None — no package renames or builds | None |

**If INTEG-05 surfaces a bug that needs a schema change:** route via Andy
(single Alembic writer) per CLAUDE.md. Otherwise this section stays empty.

## Environment Availability

Phase 20 runs against the existing docker stack. All dependencies already
proven by the five-spec-file green CI run.

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Node 20 | Playwright | ✓ (CI + local assumed) | 20.x | — |
| Python 3.10 | seed_e2e.py globalSetup | ✓ | 3.10 | — |
| Docker Compose | backend/db/redis/mailpit stack | ✓ | — | — |
| Postgres 16 | backend tests | ✓ | 16 | — |
| Redis 7 | celery broker | ✓ | 7 | — |
| Mailpit | dev email capture (for smoke checklist step: "magic link email arrives") | ✓ | latest | — |
| `@playwright/test` | all specs | ✓ | per `package.json` | — |
| `@axe-core/playwright` | a11y specs (not new in this phase) | ✓ | per `package.json` | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Playwright `@playwright/test` (version per `package.json`) |
| Config file | `playwright.config.js` at repo root |
| Quick run command | `npx playwright test e2e/cross-role.spec.js --project=chromium` |
| Full suite command | `npx playwright test` (all specs × 6 projects) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| INTEG-01 | Cross-role loop: admin→organizer→participant→admin audit | e2e | `npx playwright test e2e/cross-role.spec.js -g "Scenario 1"` | ❌ Wave 0 — write in new `e2e/cross-role.spec.js` |
| INTEG-02 | ≥4 new scenarios, full suite green | e2e | `npx playwright test` | ❌ Wave 0 — write Scenarios 1–4 (5 optional) |
| INTEG-03 | CI green on every PR | ci | Existing `.github/workflows/ci.yml` e2e-tests job | ✓ (already runs all e2e specs by default) |
| INTEG-04 | Manual smoke pass | manual-only | `docs/smoke-checklist.md` | ❌ Wave 0 — write the checklist |
| INTEG-05 | Bugs fixed or deferred | per-bug | per-bug | N/A (runtime outcome) |
| INTEG-06 | Doc sweep | manual grep + review | `grep -rn "yearly" IDEAS.md README.md CLAUDE.md` and visual review | ❌ Wave 0 — edit files per Stale Reference Inventory |

### Sampling Rate
- **Per task commit:** `npx playwright test e2e/cross-role.spec.js --project=chromium`
  (fast — one file, one browser)
- **Per wave merge:** `npx playwright test e2e/cross-role.spec.js` (all 6 projects on
  new spec only)
- **Phase gate:** `npx playwright test` (FULL suite including v1.1 16 + new
  cross-role specs + a11y specs, all 6 projects) must be green before
  `/gsd-verify-work 20`.

### Wave 0 Gaps
- [ ] `e2e/cross-role.spec.js` (new) — covers INTEG-01, INTEG-02
- [ ] `docs/smoke-checklist.md` (new) — covers INTEG-04
- [ ] `README.md` rewrite — covers INTEG-06
- [ ] `IDEAS.md` yearly→quarterly sweep — covers INTEG-06
- [ ] `CLAUDE.md` phase-complete update — covers INTEG-06
- [ ] No framework install needed — `@playwright/test` + `@axe-core/playwright`
  already in `package.json`

## Security Domain

Phase 20 is test-authoring + doc sweep. Security posture changes: zero. The
existing security controls (magic-link auth for participants, JWT for
admin/organizer, rate limiting, CCPA export, audit logging) are all already
covered by existing tests and are not modified in this phase.

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | yes (validated, not modified) | Existing magic-link + bcrypt/JWT |
| V3 Session Management | yes (validated, not modified) | Existing JWT flow |
| V4 Access Control | yes (validated by Scenario 5) | Existing `ProtectedRoute roles=...` |
| V5 Input Validation | yes (validated, not modified) | Existing Pydantic schemas |
| V6 Cryptography | no new crypto | — |

**Threat patterns for cross-role flows:**

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Organizer escalates to admin surface | Elevation | `ProtectedRoute roles={...}` (Scenario 5 test) |
| Confirm-token leakage in audit logs | Information Disclosure | Tokens never logged; `EXPOSE_TOKENS_FOR_TESTING` is test-only flag |
| Cross-role CSRF via audit-log page | Tampering | Existing SameSite cookies + bearer tokens; not modified |

## Code Examples

### Cross-role spec skeleton (verified pattern from existing specs)

```javascript
// e2e/cross-role.spec.js
// Source: composes public-signup.spec.js + admin-smoke.spec.js + organizer-check-in.spec.js

import { test, expect } from '@playwright/test';
import { ADMIN, ORGANIZER, VOLUNTEER_IDENTITY, ephemeralEmail, getSeed } from './fixtures.js';

async function loginAs(page, who) {
  await page.goto('/login');
  await page.locator('#login-email').fill(who.email);
  await page.locator('#login-password').fill(who.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });
}

async function logout(page) {
  // TODO: inspect current logout UI — AdminLayout header? right-drawer?
  // If no UI button, clear storage: await page.context().clearCookies();
}

test.describe.serial('cross-role: admin → participant → organizer → admin audit', () => {
  const email = ephemeralEmail('xrole');
  let confirmToken;

  test('public participant signs up via seeded event', async ({ page }) => {
    const seed = getSeed();
    await page.goto(`/events/${seed.event_id}`);
    // ... reuse clickSlotByLabel + form fill from public-signup.spec.js ...
    const [resp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/public/signups') && r.request().method() === 'POST'),
      page.locator('form').getByRole('button', { name: /sign up/i }).last().click(),
    ]);
    const body = await resp.json();
    confirmToken = body.confirm_token;
    expect(confirmToken).toBeTruthy();
    await page.goto(`/signup/confirm?token=${confirmToken}`);
    await expect(page.getByText(/your signup is confirmed/i)).toBeVisible();
  });

  test('organizer checks them in from roster', async ({ page }) => {
    const seed = getSeed();
    await loginAs(page, ORGANIZER);
    await page.goto(`/organizer/events/${seed.event_id}/roster`);
    const row = page.locator('ul li button').filter({ hasText: new RegExp(email.split('@')[0], 'i') }).first();
    await expect(row).toBeVisible({ timeout: 10000 });
    await row.click();
    await expect(
      row.locator('span').filter({ hasText: /^checked in$/i })
    ).toBeVisible({ timeout: 8000 });
  });

  test('admin sees both entries in audit log', async ({ page }) => {
    await logout(page);
    await loginAs(page, ADMIN);
    await page.goto('/admin/audit-logs');
    await page.locator('#al-q').fill(email);  // reuse Keyword Search input from admin-smoke
    // TODO: submit filter, assert rows
    await expect(page.getByText(/signup.*created/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/checked.?in/i)).toBeVisible();
  });
});
```

### Direct-API participant signup (reused from `organizer-check-in.spec.js`)

```javascript
const apiBase = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
const email = ephemeralEmail('xrole-direct');
const signupResp = await fetch(`${apiBase}/api/v1/public/signups`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    first_name: 'CheckIn', last_name: 'Test', email, phone: '8055550150',
    slot_ids: [seed.period_slot_id],
  }),
});
const body = await signupResp.json();
// body.signup_ids[0], body.confirm_token
```

## State of the Art

Nothing to report. Playwright, axe-core, and the existing docker stack are
current and stable. The project's test infrastructure is well-ahead of a
typical v1.2 volunteer scheduler.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | The 16 existing Playwright scenarios in the ROADMAP refer to unique test names, not project-multiplied runs | Existing Playwright Inventory | Low — counts are descriptive only; actual gate is "full suite green" not a count |
| A2 | Audit log writes for `signup.created` and `signup.checked_in` are synchronous (or fast enough to catch with a 10s `toBeVisible` timeout) | Scenario 1 step 4, Pitfall 2 | Medium — if audit is async Celery, Scenario 1 may flake. Inspect `backend/app/routers/admin.py` audit logic before writing the spec. Fallback: use `expect.poll` with a longer window |
| A3 | `OrganizerRosterPage` 5s polling from Phase 3 still works post-Phase 19 rescope | Scenario 3 | Medium — if polling is broken, Scenario 3 downgrades to a page-reload assertion. Check `frontend/src/pages/OrganizerRosterPage.jsx` during planning |
| A4 | The admin event create UI exists and is reachable during Scenario 1 without a seed-created event | Scenario 1 step 1 | Low — seed already creates the event; "admin creates" is satisfied by the pre-condition. Explicit UI-level create is a bonus, not a blocker |
| A5 | Logout UI exists in the admin shell header | Code example `logout()` helper | Low — worst case, replace with `page.context().clearCookies()` + reload |
| A6 | `#al-q` is still the Keyword Search input ID on `/admin/audit-logs` post-Phase 16 | Code example step 3 | Low — verified by `admin-smoke.spec.js` line 40 at time of research |
| A7 | `signup.canceled` (single L, American spelling) is the audit `kind` value used for cancel events | Scenario 4 | Low — matches `public-signup.spec.js` toast copy; verify against audit service during planning |

## Expected Bug Surfaces (INTEG-05 anticipation)

When you run the cross-role suite for the first time against a fresh stack,
these are the areas most likely to surface bugs — none are guaranteed, they
are watch-for hints:

1. **Audit log timing** — if `signup.created` writes are async Celery tasks,
   Scenario 1 step 4 will flake. Fix: make the specific audit writes
   synchronous, OR use `expect.poll` in the spec.
2. **Organizer RBAC drift** — Phase 19 shipped RBAC hide of Users/Audit
   Logs/Exports. Phase 16 touched the admin shell extensively. Scenario 5
   specifically tests for drift.
3. **Magic-link email delivery in smoke checklist** — Mailpit must be
   running; if SES/SendGrid modes are on in `backend/.env`, magic links might
   go to a real inbox instead of Mailpit. Document the env switch in the
   checklist.
4. **Seeded `attended_volunteer_email` state leaking across scenarios** — if
   a cross-role scenario picks up the attended volunteer by accident, the
   orientation modal suppression fires and the test assumption breaks. Use
   `ephemeralEmail()` per scenario.
5. **Organizer dashboard tab state after navigation back** — Phase 19-02 is
   new, not deeply E2E-tested. Cross-role Scenario 3 navigates away and
   back; if tab state is lost or scroll resets unpleasantly, that's a UX bug.
6. **Audit log search input may not debounce** — `#al-q` accepts fill but
   filter might require a submit button click or Enter key. Inspect
   `AuditLogsPage.jsx` during planning.

File each as either a commit-fix in Phase 20 (for small bugs) or an explicit
out-of-scope follow-up issue per INTEG-05.

## Open Questions (RESOLVED)

1. **Does admin event-create UI need to be exercised literally in Scenario 1?**
   RESOLVED: Use the seeded event (per Plan 20-01 Assumption A4). Document
   rationale in the spec comment. Literal UI-level create adds complexity
   without adding cross-role coverage beyond what the seed already provides.

2. **Should Scenarios 1–5 live in one file or separate files?**
   RESOLVED: One file — `e2e/cross-role.spec.js` (per Plan 20-01 Task 1).
   Split only if it exceeds ~400 lines during execution.

3. **Is the organizer 5s roster poll still functional post-Phase 19 rescope?**
   RESOLVED: Inspect `frontend/src/pages/OrganizerRosterPage.jsx` at Plan
   20-01 Task 2 execution time. If polling is broken, fall back to
   `page.reload()` + assertion.

4. **Does the audit log page filter apply on `fill()` alone or require a
   submit button click?**
   RESOLVED: Inspect `AuditLogsPage.jsx` at Plan 20-01 Task 1 execution
   time; handle debounce-vs-submit per observation.

5. **Should `docs/smoke-checklist.md` also live in `.planning/` or strictly
   in `docs/`?**
   RESOLVED: Locked to `docs/smoke-checklist.md` per ROADMAP.

## Project Constraints (from CLAUDE.md)

- **Branch awareness:** Phase 20 is cross-role integration. The current branch
  `v1.2-final` is the integration-ready merge branch. Confirm with Andy
  whether to use `v1.2-final`, cut a new `feature/v1.2-integration`, or work
  directly on `main` via PR.
- **File-ownership:** `README.md` + `CLAUDE.md` + `.planning/STATE.md` +
  `.planning/ROADMAP.md` are PR-only; doc-sweep commits must go through PR.
- **Docker-network test pattern** for backend tests (not needed for Playwright
  directly but relevant if INTEG-05 fixes touch backend).
- **Alembic slug revision IDs** — unlikely to matter for Phase 20 unless
  INTEG-05 surfaces a schema bug.
- **CSV cadence is quarterly, not yearly** — directly drives the `IDEAS.md`
  sweep in INTEG-06.
- **Andy is the single Alembic writer** (from `docs/COLLABORATION.md`).
- **Teaching style** — one concept per turn; doesn't affect code but affects
  how planning output is framed.

## Sources

### Primary (HIGH confidence)
- `/Users/andysubramanian/uni-volunteer-scheduler/.planning/REQUIREMENTS-v1.2-prod.md` — INTEG-01..06 definitions
- `/Users/andysubramanian/uni-volunteer-scheduler/.planning/ROADMAP.md` — Phase 20 success criteria + touches list
- `/Users/andysubramanian/uni-volunteer-scheduler/.planning/STATE.md` — current milestone position
- `/Users/andysubramanian/uni-volunteer-scheduler/CLAUDE.md` — project constraints
- `/Users/andysubramanian/uni-volunteer-scheduler/docs/COLLABORATION.md` — PR-only file list, tie-breaker rule
- `/Users/andysubramanian/uni-volunteer-scheduler/docs/ORG-AUDIT.md` — Phase 19 close-out state
- `/Users/andysubramanian/uni-volunteer-scheduler/docs/ADMIN-AUDIT.md` — Phase 16 audit trail
- `/Users/andysubramanian/uni-volunteer-scheduler/playwright.config.js` — 6-project matrix
- `/Users/andysubramanian/uni-volunteer-scheduler/.github/workflows/ci.yml` — CI pipeline, env vars
- `/Users/andysubramanian/uni-volunteer-scheduler/e2e/*.spec.js` — 5 existing spec files
- `/Users/andysubramanian/uni-volunteer-scheduler/e2e/fixtures.js` + `e2e/global-setup.js` — seed infrastructure
- `/Users/andysubramanian/uni-volunteer-scheduler/backend/app/routers/test_helpers.py` — cleanup endpoints
- `/Users/andysubramanian/uni-volunteer-scheduler/backend/tests/fixtures/seed_e2e.py` — seed script contract

### Secondary (MEDIUM confidence)
- Grep sweep for stale references (`yearly`, `student account`, `/organize`,
  `Overrides`) across `frontend/src`, `backend/app`, `docs/`, repo root.
  Results cited in Stale Reference Inventory.

### Tertiary (LOW confidence)
- Assumption A2 (audit log sync vs async) — unverified; flagged as a
  planning-time inspection target.
- Assumption A3 (5s polling) — unverified; flagged as a planning-time
  inspection target.

## Metadata

**Confidence breakdown:**
- Existing test inventory: HIGH — every spec file read directly
- Proposed scenarios: HIGH — compose verified existing patterns
- Stale reference inventory: HIGH for live code (greps ran clean), MEDIUM for
  archived `.planning/` (explicitly excluded per ORG-AUDIT precedent)
- Smoke checklist structure: MEDIUM — drafted from requirements; exact
  checkbox count will settle during planning
- Pitfalls: HIGH — sourced from reading the specs + the v1.1 Phase 13
  research doc's own pitfall list

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days — this is test authoring against a stable
stack, low churn)
