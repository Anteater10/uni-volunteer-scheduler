# Phase 20 — Deferred Items

Out-of-scope discoveries surfaced during Plan 20-01 execution. These are NOT
caused by `e2e/cross-role.spec.js`; they are pre-existing failures on the
`v1.2-final` branch that were carried forward from the pillar merges
(Phases 15, 16, 17, 18, 19).

Per Plan 20-01 scope discipline ("anti-goal: do NOT refactor or 'tidy up' any
existing spec in this plan — scope is additive only"), these are logged for
triage under INTEG-05 in Plan 20-03.

## Pre-existing Playwright failures on `v1.2-final`

All verified by running the affected spec in isolation with the Plan 20-01
changes stashed (confirmed pre-existing, not caused by the new cross-role
spec).

### 1. `admin-smoke.spec.js` — "admin overview page loads"

**Assertion:** `getByRole('heading', { name: 'Admin' })`
**Actual DOM:** No top-level h1 with text "Admin". AdminLayout renders
breadcrumb "Admin > Overview" and the Overview page's first heading is
"Overview" (from `useAdminPageTitle("Overview")`).
**Root cause:** Phase 16 rewrote the admin shell heading model; the smoke
test was not updated.
**Fix scope:** One-line edit to `e2e/admin-smoke.spec.js` — change the
assertion to match "Overview" or a breadcrumb selector. Not in scope for
Plan 20-01.

### 2. `admin-smoke.spec.js` — "audit logs page loads"

**Assertion:** `page.locator('#al-q').first()` visible
**Actual DOM:** The Keyword Search input is `#al-search` (verified in
`frontend/src/pages/AuditLogsPage.jsx` line 209). There is also an
`#al-kind`, `#al-actor`, `#al-search` but no `#al-q`.
**Root cause:** Phase 16 Plan 04 refactored the audit-logs page and renamed
the input from `al-q` to `al-search`. The smoke test was not updated.
**Fix scope:** One-line change `#al-q` → `#al-search` in
`e2e/admin-smoke.spec.js`. Not in scope for Plan 20-01. Plan 20-01's new
`cross-role.spec.js` uses `#al-search` correctly.

## Green-on-chromium but no installed `firefox`/`webkit` binary

`npx playwright install firefox webkit` was required during Plan 20-01 —
this is a local-machine install step, not a spec change. CI already runs
`npx playwright install --with-deps` in `.github/workflows/ci.yml`, so no
code change is needed. Dev-machine onboarding doc may want to mention this
for new clones.

## Package gap: `@axe-core/playwright` not installed on this clone

Root `package.json` declares `@axe-core/playwright@^4.11.1` in
`devDependencies` but `node_modules/@axe-core/` was missing on this
machine. Fixed inline during Plan 20-01 via `npm install`.

## Scope note

Plan 20-01 ships `e2e/cross-role.spec.js` (7 tests × 6 projects = 42 green
runs). Full-suite green across all pre-existing specs is INTEG-03's ask but
requires fixing items 1 and 2 above. Recommended: a small "INTEG-05 triage"
plan (20-03) that lands those two one-line fixes in the same PR as the doc
sweep, with explicit pointer here.
