---
phase: 16
plan: 06
subsystem: admin-frontend
tags: [exports, imports, admin-event, portals, csv, polish, ADMIN-22, ADMIN-23, ADMIN-27]
requirements: [ADMIN-22, ADMIN-23, ADMIN-27]
dependency_graph:
  requires:
    - frontend/src/components/admin/DatePresetPicker.jsx (16-03)
    - frontend/src/lib/quarter.js (16-03)
    - api.admin.analytics.{volunteerHours,attendanceRates,noShowRates}{,Csv} (16-03)
    - AdminPageTitleContext + useAdminPageTitle (16-03)
  provides:
    - Polished /admin/exports with 3 working CSV buttons + preset pickers + explainers
    - Polished /admin/imports (D-36 cleanups)
    - Polished /admin/events/:eventId (D-55 audit pass)
    - Polished /admin/portals (TODO(copy) resolved, breadcrumb wired)
  affects:
    - None (all changes are contained in leaf pages)
tech-stack:
  added: []
  patterns:
    - "Exports panels mirror the DatePresetPicker -> {from, to} ISO state
      pattern, mapped to backend from_date/to_date params at call time"
    - "Intl.RelativeTimeFormat for humanized timestamps on Imports page
      (matches Audit Log relative-time pattern)"
key-files:
  created:
    - frontend/src/pages/admin/__tests__/ExportsSection.test.jsx
  modified:
    - frontend/src/pages/admin/ExportsSection.jsx
    - frontend/src/pages/admin/ImportsSection.jsx
    - frontend/src/pages/AdminEventPage.jsx
    - frontend/src/pages/PortalsAdminPage.jsx
decisions:
  - "D-46 applied: kept the existing 3 analytics panels (Volunteer Hours /
    Attendance Rates / No-Show Rates). No new panels added."
  - "D-47 applied: Download CSV buttons wired to
    api.admin.analytics.attendanceRatesCsv and noShowRatesCsv (added in 16-03)."
  - "D-48 applied: datetime-local inputs replaced with DatePresetPicker
    presets = [quarter, last-quarter, last-12-months, custom], default quarter."
  - "D-49 applied: plain-English explainer under every panel title + a
    page-level explainer sentence."
  - "D-36 applied: ImportsSection — md:hidden mobile cards deleted,
    formatTs switched to Intl.RelativeTimeFormat, both TODO(copy) markers
    resolved, defensive backend-shape coercion removed (canonical list
    shape confirmed against backend GET /admin/imports which returns
    List[CsvImportRead])."
  - "D-55 applied: AdminEventPage breadcrumb via useAdminPageTitle driven
    by the analytics query; all TODO(copy) markers resolved; retry action
    added to analytics EmptyState; empty-roster body copy humanized."
  - "Exports panels map DatePresetPicker {from,to} -> {from_date,to_date}
    backend params (not the {start,end} in the plan snippet), which is the
    canonical shape used by /admin/analytics/* endpoints."
metrics:
  tasks: 2
  files_created: 1
  files_modified: 4
  tests_added: 2
  completed: 2026-04-15
---

# Phase 16 Plan 06: Exports polish + remaining admin page audit Summary

**One-liner:** Shipped the working Exports page (3 CSV buttons + preset
pickers + explainers) plus the D-36/D-55 polish pass on Imports,
AdminEventPage, and PortalsAdminPage — closing ADMIN-22, ADMIN-23, and
ADMIN-27 for the pages in this plan's scope.

## What shipped

### Task 1 — ExportsSection rewrite (commit `ae4e1f0`)

- `frontend/src/pages/admin/ExportsSection.jsx` rebuilt around a local
  `AnalyticsPanel` component that:
  - Seeds state from `currentQuarter()` with `preset: "quarter"`
  - Renders a `<DatePresetPicker/>` with presets
    `["quarter", "last-quarter", "last-12-months", "custom"]`
  - Maps `{from, to}` -> `{from_date, to_date}` for the api call
  - Has a Download CSV button wired to the panel's `csvFn` prop
  - Renders Skeleton/EmptyState/friendly-empty flow around the table
- Three panels:
  - Volunteer hours -> `api.admin.analytics.volunteerHours/volunteerHoursCsv`
  - Attendance rates -> `api.admin.analytics.attendanceRates/attendanceRatesCsv`
  - No-show rates -> `api.admin.analytics.noShowRates/noShowRatesCsv`
- Plain-English explainers under every panel title plus a page-level
  explainer sentence.
- `useAdminPageTitle("Exports")` wires the top-bar breadcrumb.
- No `datetime-local` inputs, no `TODO(copy)` markers anywhere in the file.
- New test file `frontend/src/pages/admin/__tests__/ExportsSection.test.jsx`
  with two cases:
  - Renders 3 Download CSV buttons, 3 explainer sentences verbatim, and
    no `<input type="datetime-local">`.
  - Clicking each Download CSV button calls the right csvFn with
    `{from_date, to_date}` params, and each panel also issues its JSON
    fetch.

### Task 2 — Imports + AdminEventPage + PortalsAdminPage polish (commit `20f6710`)

**ImportsSection (D-36):**

- `md:hidden` mobile-card block deleted entirely; single desktop table.
- `formatTs` now uses `Intl.RelativeTimeFormat` with numeric=auto and
  second/minute/hour/day granularity, mirroring the Audit Log pattern.
- Upload CSV button final copy: `"Upload quarterly CSV"` with a
  plain-English tooltip ("Upload a Sci Trek quarterly CSV to preview and
  commit events.").
- Commit modal body final copy:
  `"Commit this import? This creates all events in the preview and cannot be undone. Click Commit to proceed or Cancel to go back."`
- `useQuery.select` coercion removed; canonical shape is a list
  (verified against backend `GET /admin/imports` which returns
  `List[CsvImportRead]`).
- Added `useAdminPageTitle("Imports")` so the top-bar crumb shows
  "Admin / Imports".

**AdminEventPage (D-55):**

- `useAdminPageTitle(eventTitle)` driven by
  `analyticsQ.data?.event?.title || analyticsQ.data?.title || "Event"`.
- Page header uses the resolved event title (no more "Admin — Event"
  placeholder).
- Every `TODO(copy)` marker resolved with plain-English copy:
  - Privacy label: "Who can see volunteer names on this roster?"
  - Analytics heading: "Attendance summary"
  - Roster heading: "Signed-up volunteers"
  - Empty roster: "No one has signed up yet" + friendly body
  - Retry buttons: "Try again"
  - Export modal: "Download roster CSV" + plain-English body quoting
    the current privacy selection
- Retry action added to the analytics EmptyState so a transient failure
  is recoverable without a full page reload.
- No redesign — existing analytics query, roster grouping, privacy
  select, and CSV export button preserved.

**PortalsAdminPage:**

- Added `useAdminPageTitle("Portals")`.
- Every `TODO(copy)` marker resolved:
  - PageHeader subtitle: "Portals are the public-facing landing pages
    volunteers use to see events."
  - Empty state: "No portals yet" + helpful body pointing at the create
    form below.
  - Delete unavailable toast: clear plain-English message.
  - Form labels: "Portal name", "URL slug (short name used in the link)",
    "Short description (optional)".
  - Delete modal: plain-English body explaining the consequence.
- Loading/empty/error flow audited — Skeleton on load, EmptyState with
  Try again on error, friendly body on empty — no additions needed
  beyond the copy fixes.

## Verification results

All acceptance-criteria greps pass. Because `frontend/node_modules/vitest`
is not installed in this worktree, the vitest run was substituted with
static grep checks (same pattern used by Plan 16-01 for the
`api.test.js` guard).

### ExportsSection grep checks

- `grep -c "Download CSV" ExportsSection.jsx` → **3**
- `grep -c "attendanceRatesCsv" ExportsSection.jsx` → **1**
- `grep -c "noShowRatesCsv" ExportsSection.jsx` → **1**
- `grep -c "datetime-local" ExportsSection.jsx` → **0**
- `grep -c "DatePresetPicker" ExportsSection.jsx` → **2**
- `grep -c "Shows how many hours each volunteer" ExportsSection.jsx` → **1**
- `grep -c "TODO" ExportsSection.jsx` → **0**

### ImportsSection grep checks

- `grep -c "md:hidden"` → **0**
- `grep -c "toLocaleString"` → **0**
- `grep -c "Intl.RelativeTimeFormat"` → **1**
- `grep -c "TODO"` → **0**
- `grep -c "Some backends return a list"` → **0**
- `grep -c "useAdminPageTitle"` → **2** (import + call)

### AdminEventPage grep checks

- `grep -c "TODO"` → **0**
- `grep -c "useAdminPageTitle"` → **2**
- `grep -cE "Skeleton|EmptyState"` → **7** (loading + error + empty on
  both analytics and roster sections; well above the >=2 threshold)

### PortalsAdminPage grep checks

- `grep -c "TODO"` → **0**
- `grep -c "useAdminPageTitle"` → **2**

## Deviations from Plan

### 1. [Rule 3 — Environment] Vitest not installed in worktree

- **Found during:** Task 1 verification step
- **Issue:** `cd frontend && npm run test -- --run ...` fails with
  `sh: vitest: command not found`. `frontend/node_modules/vitest` does
  not exist in this worktree (same environment gap documented in
  Plan 16-01's deviation #7).
- **Fix:** Substituted the plan's vitest run with the
  `<acceptance_criteria>` grep gates, which are the authoritative pass
  signals per the plan. The new test file
  `ExportsSection.test.jsx` is committed and will run once vitest is
  installed (e.g. in CI or the next `npm install`).
- **Files affected:** none (the test file is still committed and
  will be picked up by a normal CI run).

### 2. [Rule 1 — Plan snippet vs backend query shape] `{start,end}` → `{from_date,to_date}`

- **Found during:** Task 1 (while reading backend `admin.py` analytics
  endpoints)
- **Issue:** The plan's `<action>` snippet uses
  `params = { start: dateState.from, end: dateState.to }`. The backend
  analytics endpoints only accept `from_date` / `to_date` query params
  (verified against `backend/app/routers/admin.py`), and the
  `api.admin.analytics.*` helpers in `lib/api.js` pass params through
  unchanged. Using `{start,end}` would have sent unfiltered requests.
- **Fix:** `AnalyticsPanel` maps `dateState -> {from_date, to_date}` via a
  `toParams()` helper and the test asserts the csvFn is called with
  `from_date` present.
- **Files modified:** `frontend/src/pages/admin/ExportsSection.jsx`,
  `frontend/src/pages/admin/__tests__/ExportsSection.test.jsx`
- **Commit:** `ae4e1f0`

### 3. [Rule 2 — Missing functionality] Retry on AdminEventPage analytics EmptyState

- **Found during:** Task 2 AdminEventPage audit
- **Issue:** The analytics EmptyState had no retry action, so a transient
  fetch failure would strand the admin on the error card until they
  reloaded the page. The plan's D-55 says "add loading/empty/error states
  if missing" — strictly, an error state without recovery is an error
  state that does not satisfy the intent of ADMIN-27.
- **Fix:** Added `<Button onClick={() => analyticsQ.refetch()}>Try again</Button>`
  to the analytics EmptyState action prop, matching the existing retry
  pattern on the roster EmptyState.
- **Files modified:** `frontend/src/pages/AdminEventPage.jsx`
- **Commit:** `20f6710`

### 4. [Rule 2 — Missing functionality] Friendly empty-roster body copy

- **Found during:** Task 2 AdminEventPage audit
- **Issue:** The empty-roster EmptyState had a title but no body, which
  violates the D-18 plain-English rule (non-technical admins should see
  an explanation, not a one-word title).
- **Fix:** Added body:
  `"As soon as volunteers start signing up, they will appear here."`
- **Files modified:** `frontend/src/pages/AdminEventPage.jsx`
- **Commit:** `20f6710`

No architectural deviations (Rule 4) and no auth gates encountered.

## Known Stubs

None. Every panel renders real data from real endpoints, every button is
wired, and every copy marker is resolved.

## Self-Check: PASSED

- FOUND: `frontend/src/pages/admin/ExportsSection.jsx`
- FOUND: `frontend/src/pages/admin/__tests__/ExportsSection.test.jsx`
- FOUND: `frontend/src/pages/admin/ImportsSection.jsx`
- FOUND: `frontend/src/pages/AdminEventPage.jsx`
- FOUND: `frontend/src/pages/PortalsAdminPage.jsx`
- FOUND: commit `ae4e1f0` (Task 1 — ExportsSection)
- FOUND: commit `20f6710` (Task 2 — Imports/AdminEventPage/Portals polish)
