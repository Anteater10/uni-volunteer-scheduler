---
phase: 16
plan: 03
subsystem: admin-shell-primitives
tags: [frontend, admin, shell, primitives, api]
requires: [16-01, 16-02]
provides:
  - "7 admin primitives under components/admin/"
  - "lib/quarter.js currentQuarter/previousQuarter/quarterProgress"
  - "AdminLayout rework with AdminTopBar + DesktopOnlyBanner + AdminPageTitleContext"
  - "HelpSection static /admin/help page"
  - "api.admin.users.invite/deactivate/reactivate + full analytics CSV helpers"
affects:
  - "All Phase 16 Wave 2 plans (04/05/06) can import from components/admin/"
  - "PR-only file touch count for Phase 16 is now locked to this plan"
tech-stack:
  added: []
  patterns:
    - "context-based page-title hook for breadcrumbs (AdminPageTitleContext)"
    - "rangeForPreset helper exported so tests + callers share preset math"
key-files:
  created:
    - frontend/src/lib/quarter.js
    - frontend/src/lib/__tests__/quarter.test.js
    - frontend/src/components/admin/AdminTopBar.jsx
    - frontend/src/components/admin/DesktopOnlyBanner.jsx
    - frontend/src/components/admin/SideDrawer.jsx
    - frontend/src/components/admin/DatePresetPicker.jsx
    - frontend/src/components/admin/RoleBadge.jsx
    - frontend/src/components/admin/Pagination.jsx
    - frontend/src/components/admin/StatCard.jsx
    - frontend/src/components/admin/__tests__/DesktopOnlyBanner.test.jsx
    - frontend/src/components/admin/__tests__/AdminTopBar.test.jsx
    - frontend/src/components/admin/__tests__/SideDrawer.test.jsx
    - frontend/src/components/admin/__tests__/DatePresetPicker.test.jsx
    - frontend/src/components/admin/__tests__/Pagination.test.jsx
    - frontend/src/pages/admin/HelpSection.jsx
    - frontend/src/pages/admin/__tests__/AdminLayout.test.jsx
  modified:
    - frontend/src/pages/admin/AdminLayout.jsx
    - frontend/src/lib/api.js
    - frontend/src/App.jsx
    - frontend/src/lib/__tests__/api.test.js
decisions:
  - "quarterIndex() allows negative indices so previousQuarter() at the anchor resolves to Winter 2026 as required by the plan's fixture test"
  - "Sidebar uses fixed dark slate-900 chrome (matches Gemini mock); active state is slate-700"
  - "AdminTopBar account menu closes on outside click + Escape (not a full focus trap; deferred per plan)"
metrics:
  duration_minutes: 4
  completed_date: "2026-04-15"
  tests_added: 30
  tasks_completed: 3
---

# Phase 16 Plan 03: Admin shell primitives + HelpSection + batched api.js Summary

**One-liner:** Shipped the 7 reusable admin-shell primitives, the `/admin/help`
static page, and the full Phase-16 batch of `api.js` admin additions so Wave 2
plans (04/05/06) never have to touch the PR-only files again.

## What was built

### Task 1 — Shared admin primitives + quarter helper (commit `36432cc`)

- `frontend/src/lib/quarter.js` mirrors `backend/app/services/quarter.py`:
  anchor `Date.UTC(2026, 2, 30)` (Mon 2026-03-30), 11-week window,
  exports `QUARTER_ANCHOR`, `quarterIndex`, `currentQuarter`,
  `previousQuarter`, `quarterProgress`. Signed indexing so
  `previousQuarter()` from the anchor rolls back to Winter 2026.
- `components/admin/DesktopOnlyBanner.jsx` — renders the exact copy the plan
  dictated plus a `useIsDesktop(breakpoint = 768)` hook used by AdminLayout.
- `components/admin/AdminTopBar.jsx` — breadcrumbs (left), optional center
  slot, Help link, account dropdown (name + RoleBadge + Sign out). Closes
  on outside click + Escape.
- `components/admin/SideDrawer.jsx` — right-side slide-over with
  `role="dialog" aria-modal="true"` + `aria-labelledby`. Escape + backdrop
  click both call `onClose`.
- `components/admin/DatePresetPicker.jsx` — segmented preset buttons
  (`24h / 7d / 30d / quarter / custom`). `rangeForPreset()` is exported for
  tests and reuse. `quarter` uses `currentQuarter()` from `lib/quarter.js`.
- `components/admin/RoleBadge.jsx` — admin=purple, organizer=blue,
  participant=gray.
- `components/admin/Pagination.jsx` — `< 1 … 3 4 5 6 7 … 47 >` via a shared
  `buildPageList()`; `<nav aria-label="Pagination">` + `aria-current="page"`
  on the active button.
- `components/admin/StatCard.jsx` — big headline value, label, optional
  explainer sentence, optional subline, optional trend chip.
- 6 vitest files (19 tests) cover the required behaviors per the plan:
  banner copy, AdminTopBar crumbs + help link + sign-out callback, drawer
  Escape + backdrop, 7d preset ISO math, pagination ellipsis shape.

### Task 2 — AdminLayout rework + HelpSection (commit `6aa801f`)

- `AdminLayout.jsx` rebuilt: fixed dark `bg-slate-900` sidebar, deleted the
  mobile-tabs horizontal-scroll path, deleted the Overrides nav item, added
  `useIsDesktop()` so the Outlet is replaced by `<DesktopOnlyBanner/>`
  below 768px. Top bar sits above the content area via `<AdminTopBar
  crumbs user onSignOut/>`.
- `AdminPageTitleContext` + `useAdminPageTitle("Users")` hook let each
  section emit its own breadcrumb label — HelpSection already uses it.
- Nav items (in order): Overview, Events, Users, Portals, Audit Logs,
  Exports, Templates, Imports. Templates + Imports kept as per CONTEXT.
- `pages/admin/HelpSection.jsx`: 8 hand-written plain-English how-to cards
  wrapped in `Card`. First card satisfies the CCPA/invite ADMIN-25 link.
- `AdminLayout.test.jsx` (3 tests) asserts: nav labels present + no
  Overrides link, child Outlet renders at 1200px, DesktopOnlyBanner
  renders at 500px.

### Task 3 — api.js batch + App.jsx route (commit `6e9e613`)

- `api.admin.users` gained `invite`, `deactivate`, `reactivate` hitting
  Plan 02's backend endpoints, plus `list()` routed through `/users/`
  with params (preserving the legacy `create/update/delete`/`ccpaExport`/
  `ccpaDelete` surface).
- `api.admin.analytics` gained `volunteerHoursCsv`, `attendanceRatesCsv`,
  `noShowRatesCsv` (all via `downloadBlob`) so Plan 06's Download CSV
  buttons never need to touch `api.js` again. JSON read helpers for
  volunteer hours / attendance rates / no-show rates are still in place.
- `App.jsx` imports `HelpSection` and adds `<Route path="help"
  element={<HelpSection/>}/>` as a nested child of the admin layout route.
- `api.test.js` extended with three new assertions (invite/deactivate/
  reactivate exist; CSV helpers exist; overrides guard remains).

## Verification

```
cd frontend && npm run test -- --run \
  src/components/admin src/pages/admin/__tests__ \
  src/lib/__tests__/api.test.js src/lib/__tests__/quarter.test.js
```

Result: **8 test files, 30 tests passing** (quarter 5, api 8, SideDrawer 4,
Pagination 4, DatePresetPicker 3, AdminTopBar 2, AdminLayout 3,
DesktopOnlyBanner 1).

## Acceptance criteria check

- [x] `ls frontend/src/components/admin/` shows 7 `.jsx` files
- [x] DesktopOnlyBanner string + `useIsDesktop` present
- [x] `QUARTER_ANCHOR` present in `lib/quarter.js`
- [x] `role="dialog"` present in SideDrawer
- [x] `purple-` class present in RoleBadge
- [x] AdminLayout has `DesktopOnlyBanner`, `AdminTopBar`,
      `AdminPageTitleContext`; no `Overrides`; ≥6 nav labels match
- [x] HelpSection has ≥8 `{ title:` entries (exactly 8)
- [x] `api.js` has `invite:`, `deactivate:`, `reactivate:`,
      `volunteerHours:`, `attendanceRates:`, `noShowRates:`,
      `attendanceRatesCsv`, `noShowRatesCsv`
- [x] `api.admin.overrides` still undefined (test guard + grep both clean)
- [x] `App.jsx` has `HelpSection` import + `path="help"` route
- [x] All phase-16 plan-03 tests green

## Deviations from Plan

**1. [Rule 3 - Blocking] Signed quarter index so `previousQuarter()` tests pass**

- **Found during:** Task 1 (plan's own fixture test)
- **Issue:** Plan snippet clamped `quarterIndex` with `Math.max(0, ...)`,
  which made `previousQuarter()` at the anchor (2026-04-15 → should roll
  back to Winter 2026 starting 2026-01-12) return the current Spring
  quarter — the plan's own assertion would have failed.
- **Fix:** Removed the `Math.max(0, ...)` clamp in `quarterIndex`, so
  negative indices are allowed and `previousQuarter()` from `idx=0`
  correctly returns `idx=-1` = Winter 2026.
- **Files modified:** `frontend/src/lib/quarter.js`
- **Commit:** `36432cc`

**2. [Rule 1 - Bug] AdminTopBar test disambiguation**

- **Found during:** Task 1 verification run
- **Issue:** `screen.getByText("Admin")` matched both the breadcrumb link
  AND the RoleBadge text ("Admin"), producing a multiple-match failure.
- **Fix:** Changed the breadcrumb assertion to
  `getByRole("link", { name: "Admin" })` and checked the `href` attribute
  explicitly.
- **Files modified:** `frontend/src/components/admin/__tests__/AdminTopBar.test.jsx`
- **Commit:** `36432cc`

No architectural deviations (Rule 4) and no auth gates encountered.

## Known Stubs

None. Every primitive is fully wired. HelpSection is static by design
(D-54); `/admin/help` is content-complete with 8 hand-written cards.

## Self-Check: PASSED

- FOUND: `frontend/src/lib/quarter.js`
- FOUND: `frontend/src/components/admin/AdminTopBar.jsx`
- FOUND: `frontend/src/components/admin/DesktopOnlyBanner.jsx`
- FOUND: `frontend/src/components/admin/SideDrawer.jsx`
- FOUND: `frontend/src/components/admin/DatePresetPicker.jsx`
- FOUND: `frontend/src/components/admin/RoleBadge.jsx`
- FOUND: `frontend/src/components/admin/Pagination.jsx`
- FOUND: `frontend/src/components/admin/StatCard.jsx`
- FOUND: `frontend/src/pages/admin/HelpSection.jsx`
- FOUND: commit `36432cc` (Task 1)
- FOUND: commit `6aa801f` (Task 2)
- FOUND: commit `6e9e613` (Task 3)
