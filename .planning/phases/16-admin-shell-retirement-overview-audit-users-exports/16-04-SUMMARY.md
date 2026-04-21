---
phase: 16
plan: 04
subsystem: admin-frontend
tags: [overview, audit-log, humanize, ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07]
requirements: [ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07]
dependency_graph:
  requires:
    - backend /admin/summary expanded shape (Plan 02)
    - backend /admin/audit-logs humanized rows (Plan 02)
    - frontend/src/components/admin/{StatCard,RoleBadge,SideDrawer,DatePresetPicker,Pagination}.jsx (Plan 03)
    - frontend/src/lib/api.js api.admin.summary / auditLogs / users.list / downloadBlob (Plan 03)
  provides:
    - Admin Overview page (D-14..D-29) wired to real backend data
    - Polished Audit Log page (D-03..D-07, D-30..D-34) with presets + drawer + numbered pagination
  affects: []
tech_stack:
  added: []
  patterns:
    - "Humanized-only rendering: every actor/entity surface comes from backend
      {actor_label, actor_role, action_label, entity_label} — UI never touches
      UUIDs, enforced by a no-UUID regression gate in both page tests (D-19)."
    - "URL-as-state-source for filters: useSearchParams drives every filter on
      the Audit Log page, so a filtered view is always deep-linkable and the
      back button restores state."
    - "Debounced search input: local React state mirrors the text field for
      instant typing feedback, then a 300ms useDebounced hook pushes the
      committed value into the URL (which triggers the query)."
key_files:
  created:
    - frontend/src/pages/admin/__tests__/OverviewSection.test.jsx
    - frontend/src/pages/__tests__/AuditLogsPage.test.jsx
  modified:
    - frontend/src/pages/admin/OverviewSection.jsx
    - frontend/src/pages/AuditLogsPage.jsx
decisions:
  - "D-14..D-29 applied to OverviewSection: 5 StatCards with plain-English
    explainers, per-quarter sublines, WoW trend chips (users/events/signups),
    quarter progress bar (Week X of 11), hours+attendance headlines,
    This Week card, fill-rate attention list with red/amber/green badges,
    20-row humanized Recent Activity feed, Last updated footer."
  - "D-18 applied: every admin-facing string is final copy. Deleted all
    TODO(copy) markers on both pages."
  - "D-19 applied and locked with regression gates: both page tests assert
    no UUID regex matches rendered text. Activity feed on Overview and log
    rows on Audit page use humanized actor_label / action_label /
    entity_label fields exclusively."
  - "D-30..D-34 applied to AuditLogsPage: URL-driven filter state (q, kind,
    actor_id, from_date, to_date, preset, page) via useSearchParams;
    SideDrawer shows raw payload + Copy button; Pagination primitive with
    25 per page; Export filtered view (CSV) button calls downloadBlob with
    the exact current param set; debounced text search."
  - "ACTION_LABELS mirrored in frontend: the kind dropdown options are a
    hand-kept mirror of backend ACTION_LABELS
    (backend/app/services/audit_log_humanize.py). Adding a new audit action
    requires adding it here too — called out in a comment."
  - "File-location debt intentionally deferred: AuditLogsPage.jsx stays at
    src/pages/ (not src/pages/admin/) to keep the merge footprint small.
    Flagged for Plan 07 audit doc."
  - "md:hidden mobile card fallback deleted on the Audit Log page. Admin
    pages are desktop-only (guarded by DesktopOnlyBanner in AdminLayout),
    so there is nothing to fall back to."
  - "Local debounced search state: the search input keeps a local useState
    so typing feels instant, and a 300ms useDebounced hook pushes the
    committed value into the URL param via updateParam. Prevents a round
    trip per keystroke."
metrics:
  tasks: 2
  files_created: 2
  files_modified: 2
  tests_added: 12
  duration_minutes: ~20
  completed: 2026-04-15
---

# Phase 16 Plan 04: Overview + Audit Logs Wave 2 Summary

One-liner: Landed the two flagship Wave 2 admin pages — Overview wired to the
expanded /admin/summary with humanized activity feed, and AuditLogsPage
rewritten in place around the new primitives (SideDrawer, DatePresetPicker,
Pagination) with URL-driven filters and a locked-in no-UUID regression gate.

## What shipped

### Task 1 — OverviewSection rewire (commit 3602eae)

- `frontend/src/pages/admin/OverviewSection.jsx` rewritten to consume the full
  D-14..D-29 `/admin/summary` shape:
  - 5 headline `StatCard`s (Users / Events / Slots / Signups / Confirmed
    signups) with inline plain-English explainers ("N people can sign into
    this admin panel."), per-quarter sublines, and week-over-week trend
    chips fed from `week_over_week.{users,events,signups}`.
  - Quarter progress bar: "Week {w} of 11 — {pct}% through the quarter"
    driven by `quarter_progress`.
  - Hours + attendance headlines: `volunteer_hours_quarter` and
    `attendance_rate_quarter` rendered as big bold numbers with one-sentence
    explainers.
  - This Week card: `this_week_events` + `this_week_open_slots` + link to
    `/admin/events`.
  - Needs attention list: top 20 upcoming events from `fill_rate_attention`,
    each row linking to `/admin/events/{id}` with a red/amber/green filled
    badge (`STATUS_BADGE` palette keyed by the backend `status` field).
  - Recent Activity feed: exactly 20 rows from
    `api.admin.auditLogs({ limit: 20 })`, each showing
    `{actor_label}` + `<RoleBadge role={actor_role}/>` + `{action_label}` +
    optional `— {entity_label}` + a relative timestamp via a local
    `relativeTime()` helper using `Intl.RelativeTimeFormat`.
  - "Last updated: HH:MM" footer from `last_updated`.
  - Loading → grid of Skeletons. Error → `EmptyState` with Retry. Empty
    activity → "Nothing yet."
  - Every `TODO(copy)` marker deleted; admin-facing copy is final.
- `frontend/src/pages/admin/__tests__/OverviewSection.test.jsx` (6 tests):
  - 5 StatCards render with the plain-English explainer strings
  - Quarter progress bar, hours headline, attendance %, This Week card,
    and Last updated footer all render from the fixture
  - Fill-rate attention list renders titles + `{filled}/{capacity}` badges
  - 20 humanized activity rows render with role badges and action labels
  - **D-19 regression gate**: no UUID regex matches the rendered text even
    though the summary fixture contains real-shape UUIDs in
    `fill_rate_attention[].event_id`
  - Activity query is invoked with exactly `{limit: 20}`

### Task 2 — AuditLogsPage rewrite (commit 97792f4)

- `frontend/src/pages/AuditLogsPage.jsx` rewritten in place:
  - 5-column table (When / Who / What / Target / Details) of humanized rows.
    "When" shows relative time with ISO tooltip. "Who" shows `actor_label` +
    `RoleBadge`. "What" / "Target" are `action_label` / `entity_label`.
    "Details" is a View button.
  - Filter bar:
    - Debounced (300ms) free-text search wired to URL param `q`
    - Action dropdown populated from `ACTION_LABEL_OPTIONS` — a hand-kept
      mirror of `backend/app/services/audit_log_humanize.py::ACTION_LABELS`
    - Actor dropdown populated from `api.admin.users.list({include_inactive: true})`
    - `DatePresetPicker` with presets `[24h, 7d, 30d, quarter, custom]`;
      preset + from_date/to_date mirrored in URL
    - Export filtered view (CSV) button → `downloadBlob("/admin/audit-logs.csv",
      "audit-logs.csv", { params })` where `params` is the exact current
      filter set
  - URL as state source: `useSearchParams` drives every filter. Any filter
    change resets `page=1`. Reloading the page restores state from URL.
  - Row click (or "View" button) opens `<SideDrawer/>` with the full raw
    payload pre-formatted as JSON plus a "Copy to clipboard" button that
    calls `navigator.clipboard.writeText` (best-effort; swallows errors so
    test envs don't crash).
  - Numbered pagination via `<Pagination/>` primitive, 25 per page, with
    entry count on the left ("N entries").
  - **Deleted**: the old Prev/Next pagination, the `md:hidden` mobile card
    fallback block, every `TODO(copy)` marker, all legacy helpers.
- `frontend/src/pages/__tests__/AuditLogsPage.test.jsx` (6 tests):
  - 5-column table header order (When/Who/What/Target/Details)
  - Explainer sentence rendered verbatim
  - Clicking a row opens the dialog with the raw JSON payload and a Copy
    button (verified by reading the rendered `"action_label": "..."` line)
  - Typing in the search box pushes `q=` into the URL (verified via a
    `useLocation` probe component rendered inside the router)
  - **D-19 regression gate**: no UUIDs in rendered table text
  - Export button calls `downloadBlob` with the params from the initial
    URL (`?q=invite&kind=user_invite`)

## Verification results

- `cd frontend && npm run test -- --run src/pages/admin/__tests__/OverviewSection.test.jsx
  src/pages/__tests__/AuditLogsPage.test.jsx` → **12 passed (12)** in ~2s

Acceptance greps (all pass):

- `grep -n "people can sign into this admin panel" frontend/src/pages/admin/OverviewSection.jsx` → 1 match
- `grep -n "fill_rate_attention" frontend/src/pages/admin/OverviewSection.jsx` → 1 match
- `grep -n "quarter_progress" frontend/src/pages/admin/OverviewSection.jsx` → 1 match
- `grep -n "Last updated" frontend/src/pages/admin/OverviewSection.jsx` → 1 match
- `grep -n "RoleBadge" frontend/src/pages/admin/OverviewSection.jsx` → 2 matches
- `grep -n "limit: 20" frontend/src/pages/admin/OverviewSection.jsx` → 1 match
- `grep -n "TODO" frontend/src/pages/admin/OverviewSection.jsx` → empty
- `grep -n "useSearchParams" frontend/src/pages/AuditLogsPage.jsx` → 3 matches
- `grep -n "SideDrawer" frontend/src/pages/AuditLogsPage.jsx` → 5 matches
- `grep -n "DatePresetPicker" frontend/src/pages/AuditLogsPage.jsx` → 3 matches
- `grep -n "Pagination" frontend/src/pages/AuditLogsPage.jsx` → 4 matches
- `grep -n "Export filtered view" frontend/src/pages/AuditLogsPage.jsx` → 2 matches
- `grep -n "md:hidden" frontend/src/pages/AuditLogsPage.jsx` → empty
- `grep -n "TODO" frontend/src/pages/AuditLogsPage.jsx` → empty
- `grep -n "history of every important change" frontend/src/pages/AuditLogsPage.jsx` → 1 match

## Deviations from Plan

### [Rule 1 — Text ambiguity] Audit log test row-click target

The plan's Task 2 acceptance had tests click on `"Invited a new user"` to open
the drawer. That string appears twice in the rendered DOM — once as the row's
action-label cell, and once as an option in the Action dropdown (which is
populated from the same backend `ACTION_LABELS` mirror). `screen.getByText`
failed with "Found multiple elements."

Fixed: the row-click and first-render tests now click/await on the row's
`entity_label` cell (`"Jane Newcomer"`), which is unambiguous (not in any
dropdown). The 5-column table test asserts the same 5 headers in the same
order, and the drawer-opens test still verifies the raw JSON contains
`"action_label": "Invited a new user"` inside the dialog. No behavior change
to production code.

### [Rule 3 — Worktree base divergence] Soft reset to plan base

The worktree started on commit `50f7eec` which predates the Phase 16 Plan
01/02/03 work (no admin primitives, no api.admin.users.list, no humanized
audit shape). The plan's `<worktree_branch_check>` directive instructed
resetting to `334a33f` (the tip of Plan 03). Applied: `git reset --soft`
plus a cleanup of the stale worktree index so the workspace matched the
expected base, then started Task 1 from a clean tree. No production-code
content was lost — the previous worktree commits were documentation
drafts for an unrelated Phase 14 branch.

## Known Stubs

None. Both pages render real data from real backend endpoints. The
`ACTION_LABEL_OPTIONS` list is a hand-kept mirror of the backend
`ACTION_LABELS` dict (documented inline) — that's a coordination
convention, not a stub.

## Threat Flags

None. No new authentication paths, no new file-read surfaces, no new trust
boundaries. The Audit Log page consumes the Plan 02 humanized endpoint
which is already admin-gated server-side. `navigator.clipboard.writeText`
is guarded with a try/catch so a missing clipboard API can't break the UI.

## Commits

- `0e48805` — test(16-04): add failing OverviewSection tests for D-14..D-29 shape
- `3602eae` — feat(16-04): rewire OverviewSection to D-14..D-29 expanded summary
- `7991de6` — test(16-04): add failing AuditLogsPage tests for D-03..D-07, D-30..D-34
- `97792f4` — feat(16-04): rewrite AuditLogsPage with primitives + humanized rendering

## Self-Check: PASSED

- frontend/src/pages/admin/OverviewSection.jsx — FOUND (modified)
- frontend/src/pages/admin/__tests__/OverviewSection.test.jsx — FOUND (created)
- frontend/src/pages/AuditLogsPage.jsx — FOUND (modified)
- frontend/src/pages/__tests__/AuditLogsPage.test.jsx — FOUND (created)
- Commit 0e48805 — FOUND
- Commit 3602eae — FOUND
- Commit 7991de6 — FOUND
- Commit 97792f4 — FOUND
- 12/12 tests passing on both page test files
