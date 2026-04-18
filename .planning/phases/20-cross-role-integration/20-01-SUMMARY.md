---
phase: 20-cross-role-integration
plan: 01
subsystem: e2e-testing
tags: [playwright, cross-role, integration, e2e, rbac, audit]
requirements: [INTEG-01, INTEG-02, INTEG-03]
dependency-graph:
  requires:
    - e2e/fixtures.js (ADMIN, ORGANIZER, VOLUNTEER_IDENTITY, ephemeralEmail, getSeed)
    - e2e/global-setup.js (seed_e2e.py bootstrap → process.env.E2E_SEED)
    - backend test-helpers router (EXPOSE_TOKENS_FOR_TESTING=1 gate — confirm_token exposure + rate-limit bypass)
    - frontend routes /events, /signup/confirm, /signup/manage, /admin, /admin/audit-logs, /admin/templates, /admin/imports, /admin/users, /admin/exports, /organizer, /organizer/events/:id/roster
    - backend /api/v1/public/signups (POST + /confirm) and /api/v1/admin/audit-logs
  provides:
    - 5 cross-role Playwright scenarios (7 top-level tests; 42 total runs across 6 projects)
    - Canonical admin → participant → organizer → admin-audit loop (INTEG-01)
    - Regression guard for Phase 19 organizer RBAC (Scenario 5)
    - Regression guard for the 5s OrganizerRosterPage refetch interval (Scenario 3)
    - Regression guard for the public cancel → audit-log write path (Scenario 4)
  affects:
    - CI .github/workflows/ci.yml e2e-tests job (picks up new spec automatically; no workflow edits)
tech-stack:
  added: []
  patterns:
    - "Inline login + clickSlotByLabel copy-paste (no shared helper module per scope discipline — `admin-a11y.spec.js` already flagged extraction for future phase)"
    - "Per-test pageerror + console.error capture with a justified ALLOWED_CONSOLE_PATTERNS list"
    - "ensureAdminViewport(1280×800) before admin-shell tests so Mobile Chrome / Mobile Safari / iPhone SE 375 projects bypass the DesktopOnlyBanner"
    - "expect.poll for read-after-write on admin overview (Scenario 2) and audit-log list (Scenario 4)"
    - "Direct-API signup + confirm for scenarios that do not need to exercise the participant UI (Scenarios 2–4)"
key-files:
  created:
    - e2e/cross-role.spec.js (573 lines, 5 scenarios, 7 tests)
    - .planning/phases/20-cross-role-integration/20-01-SUMMARY.md
    - .planning/phases/20-cross-role-integration/deferred-items.md
  modified: []
decisions:
  - "Use `#al-search` (not `#al-q`) for the audit-logs keyword input — the plan inherited the stale selector from the pre-Phase-16 codebase"
  - "Call `page.context().clearCookies()` + localStorage.clear() as the logout primitive instead of driving the header dropdown menu — dropdown menus race with React state under parallel workers"
  - "Scenario 1C asserts the weaker property 'admin audit-log page is reachable after cross-role flow' rather than 'signup.created row appears' — only ADMIN-initiated actions + public cancel are audited; participant signup.created and organizer check-in are NOT in ACTION_LABELS"
  - "Allowlist the WebKit 'due to access control checks' pageerror — reproducible Safari artifact for in-flight fetch aborts during navigation, not a product CORS bug"
  - "Treat the 13 pre-existing `admin-smoke.spec.js` / `organizer-check-in.spec.js` failures as out-of-scope for Plan 20-01 (scope: additive only) and defer to Plan 20-03 via deferred-items.md"
metrics:
  duration: ~3 hours (spanning 4 incremental commits + verification runs)
  completed: 2026-04-17
---

# Phase 20 Plan 01: Cross-Role Playwright Integration Scenarios Summary

Shipped `e2e/cross-role.spec.js` — 5 cross-role Playwright scenarios (7 tests × 6 projects = 42 green runs) proving the v1.2-prod admin + organizer + participant pillars compose end-to-end against the docker stack.

## What Shipped

| Scenario | Kind | Covers | Status |
|---|---|---|---|
| 1 (serial describe, 3 tests: 1A, 1B, 1C) | Canonical loop | INTEG-01 — admin → participant → organizer → admin-audit-log reachability | Green on all 6 projects |
| 2 | Independent test | Admin overview Signups counter increments after a participant signup (ADMIN-04 wiring) | Green |
| 3 | Independent test | Organizer roster picks up a fresh signup within the 5s react-query refetchInterval (ORG-07 polling regression guard) | Green |
| 4 | Independent test | Public cancel via `/signup/manage?token=...` writes `signup_cancelled` to the admin audit log | Green |
| 5 | Independent test | Phase 19 RBAC — admin-only pages render Forbidden for organizer; shared pages (templates/imports/organizer) load | Green |

## Audit-write sync/async finding

Audit writes are **synchronous** — `backend/app/deps.py:log_action` runs inside the same database transaction as the mutating action. No Celery indirection. Scenarios that assert audit-log content (Scenario 4) do not need `expect.poll` for timing; a short poll is used only to absorb read-after-write lag on a cold admin list endpoint connection.

However, the audit surface is narrower than the research doc assumed:
- Only ADMIN-initiated actions + public cancel are audited (`backend/app/services/audit_log_humanize.py` ACTION_LABELS).
- `signup.created` (public) and organizer check-in are NOT audited.
- Scenario 1C therefore asserts the weaker property: the admin audit-log page is **reachable** after the cross-role loop, not that the create/check-in rows exist.

This is logged as an INTEG-05 candidate in deferred-items.md — Andy may want to add check-in audit writes in a follow-up.

## Logout approach used

`page.context().clearCookies()` + `localStorage.clear()` + `sessionStorage.clear()`. The admin shell renders logout in a dropdown menu (`frontend/src/components/Layout.jsx`) behind an `aria-haspopup` trigger that races with React state under the 4-worker parallel run. Direct cookie/storage clearing is deterministic.

## RBAC behaviour observed in App.jsx

`frontend/src/routes/ProtectedRoute.jsx` lines 12-19: when a logged-in user hits a route whose `roles={[...]}` does not include their role, the route renders a `<Forbidden />` component (heading text "Forbidden"), NOT a redirect.

Admin-only routes (`roles=["admin"]`): `/admin/users`, `/admin/audit-logs`, `/admin/exports`.
Shared routes (`roles=["admin", "organizer"]`): `/admin` (overview), `/admin/templates`, `/admin/imports`, `/admin/events/:id`.
Organizer pillar: `/organizer`, `/organizer/events/:id/roster`.

Pitfall 5 from 20-RESEARCH.md reaffirmed: templates/imports MUST load for organizers — Scenario 5's positive checks catch any future inversion of the allow/deny lists.

## Key Decisions

1. **Seeded event, not admin-UI event create.** Scenario 1 uses the `globalSetup`-created event (via `seed_e2e.py`). Literal UI-level admin-event-create adds spec complexity without adding cross-role coverage (research Open Question Q1 RESOLVED).
2. **One file, not split.** All 5 scenarios live in `e2e/cross-role.spec.js` (573 lines). Split only if it grows past ~800 lines.
3. **No shared helpers extracted.** `loginAs`, `logout`, `clickSlotByLabel`, `apiSignupAndConfirm`, `readSignupsTotal`, `ensureAdminViewport` are all inline in the spec. Matches the "Don't Hand-Roll" table in 20-RESEARCH.md.
4. **Last-name tag (not email-local) for roster row matching.** The roster UI renders `{first_name} {last_name} ... {chip}`; email is not in the visible row text. A unique last-name suffix is the reliable locator.
5. **Allowlist three specific console/pageerror patterns** with inline justification comments (parallel-worker Response serialization, organizer-403 on shared pages, WebKit in-flight fetch-abort pageerror).

## Deviations from Plan

### Auto-fixed (Rule 1/3 — inline repairs to make the plan work)

**1. [Rule 3 - Missing dependency] `@axe-core/playwright` not installed on local clone**
- **Found during:** Task 3 full-matrix run (affects `admin-a11y.spec.js`)
- **Issue:** Root `package.json` declares `@axe-core/playwright@^4.11.1` in devDependencies but `node_modules/@axe-core/` was missing on this machine.
- **Fix:** `npm install` at repo root during Task 3.
- **Scope:** Local install only; no code change committed.

**2. [Rule 3 - Missing binary] Playwright firefox + webkit browsers not downloaded**
- **Found during:** Task 3 full-matrix run.
- **Issue:** Fresh playwright install on this clone had only chromium.
- **Fix:** `npx playwright install firefox webkit`.
- **Scope:** Local install only.

**3. [Rule 1 - Stale contract] `#al-q` selector is now `#al-search`**
- **Found during:** Task 1 inspection of `AuditLogsPage.jsx`.
- **Issue:** Plan interfaces section cited `#al-q` (from `admin-smoke.spec.js` line 40). Phase 16 Plan 04 renamed it to `#al-search` with 300ms debounce (no submit button).
- **Fix in new spec:** Used `#al-search` and relied on debounce + `waitForLoadState('networkidle')` — no submit required.
- **Pre-existing spec NOT touched:** `admin-smoke.spec.js` still references `#al-q`. Logged in deferred-items.md for Plan 20-03 (scope-discipline anti-goal: do NOT edit existing specs).

**4. [Rule 3 - Viewport gate] AdminLayout's DesktopOnlyBanner blocks tests on mobile-sized projects**
- **Found during:** Task 3 full-matrix run (Mobile Chrome, Mobile Safari, iPhone SE 375 projects).
- **Issue:** AdminLayout renders a "Please switch to a larger screen" banner below 768px instead of the actual admin shell. All admin-shell cross-role scenarios would fail on the 3 mobile projects.
- **Fix:** Added `ensureAdminViewport(page)` helper (`page.setViewportSize({ width: 1280, height: 800 })`) and called it in every scenario that authenticates as admin. Mirrors the pattern already established in `admin-a11y.spec.js`.

**5. [Rule 2 - Allowlist justification] WebKit `access control checks` pageerror**
- **Found during:** Task 3 full-matrix run (webkit, Mobile Safari, iPhone SE 375 projects).
- **Issue:** WebKit raises a `pageerror` with message `"<url> due to access control checks."` when navigation aborts in-flight fetches initiated by the previous page. Chromium/Firefox stay silent. Not a product CORS bug (verified — see upstream https://bugs.webkit.org/show_bug.cgi?id=245629).
- **Fix:** Added `/due to access control checks\.?$/i` to `ALLOWED_CONSOLE_PATTERNS` with a full justification comment.

## Known Stubs

None — the spec file contains no placeholder data, no mocked components, no TODOs that flow to UI.

## Deferred Issues

The full Playwright suite has 13 failures, all in pre-existing specs (not in the new `cross-role.spec.js`). These are out-of-scope for Plan 20-01 per the plan's explicit anti-goal ("do NOT refactor or 'tidy up' any existing spec in this plan — scope is additive only").

Documented in detail in `.planning/phases/20-cross-role-integration/deferred-items.md`:
- `admin-smoke.spec.js` "admin overview page loads" — asserts `getByRole('heading', { name: 'Admin' })` but Phase 16 renamed the heading to "Overview". 6 projects × 1 test = 6 failures.
- `admin-smoke.spec.js` "audit logs page loads" — asserts `#al-q` but Phase 16 renamed to `#al-search`. 6 projects × 1 test = 6 failures.
- `organizer-check-in.spec.js` — 1 remaining failure (chromium only); already partially fixed with the `/organize/` → `/organizer/` URL update that is on the working tree.

**Recommended Plan 20-03 triage:** land the two one-line fixes to `admin-smoke.spec.js` in the same PR as the INTEG-06 doc sweep. CI will then satisfy INTEG-03 (full suite green). Estimated effort: 5 minutes.

## Commits (all on `v1.2-final`)

| Task | Commit | Message |
|---|---|---|
| 1 | 585e895 | test(20-01): add cross-role Scenario 1 (canonical admin -> participant -> organizer -> admin loop) |
| 2 | 99786c5 | test(20-01): add cross-role Scenarios 2, 3, 4 + robustness fixes |
| 3 | 015fa20 | test(20-01): add cross-role Scenario 5 (organizer RBAC) |
| 3 (allowlist follow-up) | 10fa27d | fix(20-01): allowlist WebKit 'access control checks' pageerror in cross-role spec |
| SUMMARY (this commit) | (pending) | docs(20-01): complete cross-role integration plan |

## Verification Results

- `EXPOSE_TOKENS_FOR_TESTING=1 npx playwright test e2e/cross-role.spec.js --project=chromium` → **7 passed (10.6s)**
- `EXPOSE_TOKENS_FOR_TESTING=1 npx playwright test e2e/cross-role.spec.js` (all 6 projects) → **42 passed (1.5m)**
- `EXPOSE_TOKENS_FOR_TESTING=1 npx playwright test` (full suite, all 6 projects) → **188 passed, 13 failed, 51 skipped (5.6m)**
  - All 13 failures are in pre-existing `admin-smoke.spec.js` / `organizer-check-in.spec.js` — see deferred-items.md.
  - 0 failures in the new `e2e/cross-role.spec.js`.
- `grep -c "^test\|^test\.describe" e2e/cross-role.spec.js` → **5** (meets ≥5 threshold from plan verification).

## Anomalies and INTEG-05 Follow-ups

Candidates for Plan 20-03 triage (`deferred-items.md` has the precise list):

1. **Audit-log coverage gap (product decision, not bug).** `signup.created` (public) and organizer `signup.checked_in` are NOT audited. Only cancel + admin-initiated actions are in `ACTION_LABELS`. If Andy wants a full cross-role audit trail, add those two action kinds. Otherwise document the scope in `docs/ADMIN-AUDIT.md`.
2. **Admin-smoke selector staleness** — 2 one-line fixes (`#al-q` → `#al-search`, `name: 'Admin'` → `name: 'Overview'`).
3. **Organizer-check-in spec working-tree drift** — `e2e/organizer-check-in.spec.js` has uncommitted local edits normalizing `/organize/` → `/organizer/`. Plan 20-03 PR should include these or revert.
4. **WebKit upstream watch** — the `"access control checks"` pageerror allowlist is a workaround for https://bugs.webkit.org/show_bug.cgi?id=245629. Revisit when the bug lands.
5. **DesktopOnlyBanner UX on narrow admin viewports** — AdminLayout shows a static banner below 768px with no graceful narrow mode. If v1.3 wants admin mobile, it's a real design question, not a test hack.

## Self-Check: PASSED

- [x] `e2e/cross-role.spec.js` exists (573 lines)
- [x] Commit 585e895 on v1.2-final
- [x] Commit 99786c5 on v1.2-final
- [x] Commit 015fa20 on v1.2-final
- [x] Commit 10fa27d on v1.2-final
- [x] Full Playwright cross-role suite green: 42/42 across 6 projects
- [x] ≥5 `^test|^test.describe` matches in spec
- [x] No existing specs modified by Plan 20-01 commits (diff verified against commit ranges 585e895..10fa27d)
