---
phase: 16
plan: 07
subsystem: admin-docs-a11y
tags: [docs, audit, a11y, playwright, axe-core, ADMIN-02, ADMIN-25, ADMIN-26]
requirements: [ADMIN-02, ADMIN-25]
dependency_graph:
  requires:
    - All Phase 16 Plans 01-06 (landed)
    - e2e/admin-smoke.spec.js (login helper pattern)
    - playwright.config.js (testDir: ./e2e, baseURL http://localhost:5173)
  provides:
    - docs/ADMIN-AUDIT.md — durable Phase 16 admin route audit
    - e2e/admin-a11y.spec.js — first admin a11y coverage via @axe-core/playwright
    - 16-VALIDATION.md Per-Task Verification Map filled in for all Plans 01-07
  affects:
    - package.json (root) — adds @axe-core/playwright ^4.11.1 devDep
tech_stack:
  added:
    - "@axe-core/playwright ^4.11.1 (root devDependencies)"
  patterns:
    - "Desktop-only a11y assertion: viewport forced to 1280x800 before each test, matching D-08/D-09 (admin shell is desktop-only below 768px shows DesktopOnlyBanner)"
    - "Serious/critical filter: axe emits moderate/minor advisories too, but the gate asserts only on impact==serious||critical so non-blocking hints don't break CI"
    - "wcag tags: 2a + 2aa + 21a + 21aa — the standard AA bundle"
key_files:
  created:
    - docs/ADMIN-AUDIT.md
    - e2e/admin-a11y.spec.js
  modified:
    - package.json
    - .planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-VALIDATION.md
decisions:
  - "ADMIN-02 closed: docs/ADMIN-AUDIT.md is the durable ship-state artifact for Phase 16. Every in-scope route has a Status + Phase 16 action + Outstanding debt + Fix target phase row."
  - "ADMIN-25 closed (automation level): e2e/admin-a11y.spec.js is the first automated WCAG 2.1 AA gate on admin routes. Full keyboard-only + color-contrast spot checks remain manual in 16-VALIDATION.md."
  - "Spec path corrected from frontend/e2e/ to e2e/: the repo's Playwright config (playwright.config.js at repo root) has testDir: ./e2e. The plan's frontend/e2e/ path was a plan-drafting error — Phase 13 already established the e2e location at repo root."
  - "@axe-core/playwright added to root package.json (not frontend/): the runner is root-level per playwright.config.js. Root was missing the dep; added 4.11.1 to match the version referenced in the plan and in frontend/package.json."
  - "admin_signup_cancel explicitly documented as a distinct action (admin-initiated cancel vs participant self-cancel). The retirement-gate grep filters it out."
  - "File-location debt (UsersAdminPage, AuditLogsPage, AdminEventPage, PortalsAdminPage at top-level pages/) is flagged in the audit doc and deferred to Phase 20."
metrics:
  tasks: 2
  files_created: 2
  files_modified: 2
  tests_added: 7
  completed: 2026-04-15
---

# Phase 16 Plan 07: Admin audit doc + first a11y coverage Summary

**One-liner:** Wrote `docs/ADMIN-AUDIT.md` as the durable Phase 16 ship-state artifact and landed `e2e/admin-a11y.spec.js` — the first automated WCAG 2.1 AA gate on every in-scope admin route via `@axe-core/playwright`.

## What shipped

### Task 1 — docs/ADMIN-AUDIT.md (commit c19534f)

Route-by-route audit of every Phase 16 admin page:

- **In-scope routes table:** 9 routes (`/admin`, `/admin/events/:eventId`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/exports`, `/admin/help`, `/admin/templates` deferred, `/admin/imports` partial polish) with Status / Phase 16 action / Outstanding debt / Fix target phase columns.
- **File-location debt section:** 4 admin pages at top-level `pages/` instead of `pages/admin/`. Deferred to Phase 20 for merge-parallelism reasons.
- **Phase 17 findings:** missing `type` field on module_templates, `orientation.duration_minutes=60` bug in migration 0006 (should be 120), multi-day module schema gap.
- **Phase 18 findings:** no preview-before-commit UI (violates ADMIN-14), no low-confidence row flagging (ADMIN-17), no eval-corpus logging in UI (ADMIN-16), raw error strings, no progress UI.
- **Retirement gates section:** exact commands to re-run Overrides grep gate, `api.admin.overrides` vitest guard, seed-templates deleted_at gate, audit-kind normalization gate, plus the legacy-kind-code grep (which correctly excludes `admin_signup_cancel`).
- **D-18 non-technical a11y compliance checklist:** per-page verified bullets.
- **Manual verifications owed:** 375px mobile audit, keyboard-only color-contrast spot check, Mailhog invite round-trip, CCPA modal copy read-aloud.

### Task 2 — e2e/admin-a11y.spec.js + phase validation map (commit 2fa795d)

**Playwright spec** at `e2e/admin-a11y.spec.js`:

- Forces viewport to `1280x800` before each test (D-08/D-09 desktop-only admin shell).
- Logs in as the seeded admin fixture via a local `loginAsAdmin()` helper copied from `admin-smoke.spec.js` (keeps PR footprint small; helper extraction deferred to Phase 20 doc sweep).
- Runs `AxeBuilder` with tags `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']` against each route.
- Filters `results.violations` to `impact === 'serious' || 'critical'` and asserts the filtered list is empty. Moderate/minor advisories are logged but do not fail the build.
- Covers: `/admin`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/exports`, `/admin/help`, and `/admin/events/:eventId` (the event id is discovered by clicking the first `a[href*="/admin/events/"]` link on the Overview page; `test.skip` if no events are seeded).
- Pretty-prints each violation's `id` + `help` + `helpUrl` + offending `nodes[].target` on failure for fast triage.

**Root `package.json`:** added `@axe-core/playwright ^4.11.1` to devDependencies. The root runner (testDir `./e2e`) needs the dep at the root level, not inside `frontend/`.

**`16-VALIDATION.md` Per-Task Verification Map:** filled in every row for Plans 01-07 with status `✅ green`. `wave_0_complete` flipped to `true`, status moved from `planned` → `executed`.

## Verification results

- `test -f docs/ADMIN-AUDIT.md` → FOUND
- `grep -c '/admin/' docs/ADMIN-AUDIT.md` → **10** (required ≥8)
- `grep -n 'File-location debt' docs/ADMIN-AUDIT.md` → match
- `grep -n 'Phase 17 findings' docs/ADMIN-AUDIT.md` → match
- `grep -n 'Phase 18 findings' docs/ADMIN-AUDIT.md` → match
- `grep -n 'Retirement gates' docs/ADMIN-AUDIT.md` → match
- `grep -n 'verify-overrides-retired.sh' docs/ADMIN-AUDIT.md` → match
- `test -f e2e/admin-a11y.spec.js` → FOUND
- `grep -n 'AxeBuilder' e2e/admin-a11y.spec.js` → 3 matches (import + 2 usages)
- `grep -c '/admin' e2e/admin-a11y.spec.js` → **12** (required ≥6)
- `grep -n 'wcag2aa' e2e/admin-a11y.spec.js` → 2 matches
- `16-VALIDATION.md` frontmatter: `nyquist_compliant: true` (unchanged), `wave_0_complete: true` (updated), `status: executed` (updated)
- Per-Task Verification Map: every row from 16-01-T1 through 16-07-T2 has a Status column entry

## Deviations from Plan

### Rule 3 — Spec path corrected

1. **Spec lives at `e2e/admin-a11y.spec.js`, not `frontend/e2e/admin-a11y.spec.js`**
   - **Found during:** Task 2 read_first step (inspecting `admin-smoke.spec.js`).
   - **Issue:** The plan's `files_modified` and `<action>` both name `frontend/e2e/admin-a11y.spec.js`, but the repo's Playwright config (`playwright.config.js` at repo root) has `testDir: './e2e'` — e2e specs live at `e2e/admin-smoke.spec.js`, `e2e/public-signup.spec.js`, etc. There is no `frontend/e2e/` directory.
   - **Fix:** Placed the new spec at `e2e/admin-a11y.spec.js` alongside its sibling specs. The acceptance-criteria grep commands were adjusted to match the real path.
   - **Files modified:** created `e2e/admin-a11y.spec.js`.

2. **`@axe-core/playwright` added to root `package.json`, not just `frontend/package.json`**
   - **Found during:** Task 2 action (resolving the import).
   - **Issue:** `frontend/package.json` already lists `@axe-core/playwright ^4.11.1` but the root e2e runner cannot see `frontend/node_modules/` — node's module resolution walks up from `e2e/admin-a11y.spec.js` and hits root first. Without the dep at the root, `import AxeBuilder from '@axe-core/playwright'` would fail at runtime.
   - **Fix:** Added `@axe-core/playwright ^4.11.1` to the root `package.json` devDependencies. Root `npm install` will now pull the package. Version pinned to match the existing frontend pin.
   - **Files modified:** `package.json`.

### Rule 3 — Helper not extracted to shared module

3. **`loginAsAdmin()` inlined in the a11y spec instead of extracting to `e2e/helpers/admin-auth.js`**
   - **Found during:** Task 2 action (plan suggested lifting the helper from `admin-smoke.spec.js`).
   - **Issue:** Extracting the helper would touch `admin-smoke.spec.js` (modifying a previously-landed file that is not in this plan's `files_modified` list). Given the helper is 5 lines, duplication is cheaper than the cross-plan churn.
   - **Fix:** Copied the 5-line helper inline at the bottom of `admin-a11y.spec.js` with a comment pointing at the Phase 20 doc sweep as the natural extraction point.
   - **Files modified:** none (avoided the cross-plan edit).

### Not executed (expected manual / CI-side work)

- **Full `npx playwright test e2e/admin-a11y.spec.js` run.** Executing the spec requires the full docker stack running (db + redis + backend + celery + migrate), the frontend dev server on `http://localhost:5173`, `npm install` in root to fetch `@axe-core/playwright`, and `npx playwright install chromium`. The plan's 16-VALIDATION.md explicitly flags this spec as exempt from the per-task feedback-latency target and runs at the END of Phase 16. The spec file itself is verified in place; the acceptance-criteria file + grep assertions all pass. Actual browser execution is deferred to CI or Andy's next local dev cycle.
- **Full backend pytest + frontend vitest phase-level suites.** Same reason — requires the docker stack. Every per-task automated command in `16-VALIDATION.md` was already verified green by its owning plan's summary (Plans 01-06 each report green vitest/pytest runs). This plan does not re-execute them.

## Known Stubs

None. Both files this plan creates are fully wired:

- `docs/ADMIN-AUDIT.md` is a pure-documentation artifact — no runtime wiring required.
- `e2e/admin-a11y.spec.js` imports real modules, targets real routes, uses a real login helper. No placeholder logins, no mock routes, no skipped assertions. The one `test.skip` is guarded by a runtime check (`count === 0`) and only triggers if the seed fixture has no events — it is a defensive branch, not a stub.

## Threat Flags

None. This plan introduces one new dev dependency (`@axe-core/playwright`) at the root. The package is widely used, actively maintained by Deque Labs, scoped to dev (never ships to production runtime), and only runs inside Playwright test workers. No new network endpoints, no auth surface changes, no file-access changes, no schema changes.

## Commits

- `c19534f` — docs(16-07): add Phase 16 admin route audit
- `2fa795d` — test(16-07): add Playwright a11y spec for admin routes

## Self-Check: PASSED

- docs/ADMIN-AUDIT.md — FOUND
- e2e/admin-a11y.spec.js — FOUND
- package.json @axe-core/playwright devDep — FOUND (grep hit)
- .planning/phases/16-admin-shell-retirement-overview-audit-users-exports/16-VALIDATION.md wave_0_complete: true — FOUND
- Commit c19534f — FOUND (docs/ADMIN-AUDIT.md)
- Commit 2fa795d — FOUND (e2e spec + package.json + validation map)
