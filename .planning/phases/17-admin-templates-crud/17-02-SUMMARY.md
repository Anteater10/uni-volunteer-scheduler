---
phase: 17-admin-templates-crud
plan: "02"
subsystem: frontend
tags: [react, side-drawer, crud, templates, vitest, admin-ux]
dependency_graph:
  requires: [17-01-templates-backend, 16-admin-shell-sidedrawer-components]
  provides: [templates-crud-ui, archive-restore-ui]
  affects:
    - frontend/src/pages/admin/TemplatesSection.jsx
    - frontend/src/pages/admin/__tests__/TemplatesSection.test.jsx
tech_stack:
  added: []
  patterns:
    - SideDrawer CRUD (create/edit in right-side panel)
    - soft-delete archive pattern (delete = archive, restore endpoint)
    - client-side filter + pagination (useMemo)
    - slug auto-generation from name on create
key_files:
  created:
    - frontend/src/pages/admin/__tests__/TemplatesSection.test.jsx
  modified:
    - frontend/src/pages/admin/TemplatesSection.jsx
decisions:
  - "Restore button only visible when Show archived toggle is on — avoids confusion with active templates"
  - "Slug field is read-only on edit because backend uses slug as primary identifier — changing it would break references"
  - "Type badge colors: seminar=blue, orientation=green, module=gray — consistent with D-19 humanized role colors"
  - "Client-side filtering chosen (not server-side search params) because template count is small (<100)"
metrics:
  duration_minutes: 45
  completed_date: "2026-04-16"
  tasks_completed: 1
  files_changed: 2
requirements: [ADMIN-08, ADMIN-09, ADMIN-10, ADMIN-11]
---

# Phase 17 Plan 02: TemplatesSection SideDrawer CRUD Summary

**One-liner:** TemplatesSection.jsx rewritten from InlineEditCell to SideDrawer CRUD with create/edit/archive/restore, type badges, slug auto-gen, 12 passing vitest tests.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite TemplatesSection with SideDrawer CRUD | 89c1750 | TemplatesSection.jsx, TemplatesSection.test.jsx |

## What Was Built

### TemplatesSection.jsx (626 lines)

Completely replaced the old `InlineEditCell` pattern with the Phase 16 SideDrawer CRUD pattern:

**Table:** Name, Type (colored badge), Duration (plain "90 min"), Sessions ("1 session" / "N sessions"), Capacity. Clickable rows open edit drawer.

**Create flow:** "New template" button opens SideDrawer with title "New template". Name field auto-generates URL slug (lowercase, hyphens). Admin can override slug before submitting.

**Edit flow:** Click any active row to open "Edit template" SideDrawer with all fields pre-filled. Slug is read-only on edit (backend primary key). Save calls PATCH.

**Archive flow:** "Archive" button in edit drawer opens Modal titled "Archive this template?" with plain-English body: "Archiving removes [Name] from the active list. You can restore it later." Confirm calls DELETE (soft-delete). D-18 compliant.

**Restore flow:** "Show archived" toggle re-queries with `include_archived: true`. Archived rows show an "Archived" badge and a "Restore" button that calls POST `/{slug}/restore`.

**Filtering:** Search by name, type dropdown (All / Module / Seminar / Orientation), "Show archived" toggle. All client-side with `useMemo`.

**Pagination:** Pagination component from Phase 16, PAGE_SIZE=10.

**States:** 4 Skeleton rows (loading), EmptyState "No templates yet" (empty), EmptyState with Retry (error).

**Breadcrumb:** `useAdminPageTitle("Templates")` wired — top bar shows "Admin / Templates".

### TemplatesSection.test.jsx (312 lines, 12 tests)

| Test | What it covers |
|------|---------------|
| renders loading skeletons | isPending state, no table visible |
| renders empty state | empty list → "No templates yet" text |
| renders table with columns | Name/Type/Duration/Sessions/Capacity headers |
| New template button opens drawer | SideDrawer dialog appears with h2 "New template" |
| Row click opens edit drawer | "Edit template" heading + pre-filled name value |
| Create form has all fields | All 8 labeled inputs present |
| Slug auto-generates from name | "Test Seminar" → "test-seminar" |
| Archive button triggers modal | "Archive this template?" dialog appears |
| Show archived toggle | include_archived:true passed to api.admin.templates.list |
| Archived row shows Restore | After toggle, ARCHIVED_TEMPLATE row has Restore button |
| Restore calls api.restore | fireEvent on Restore → api.admin.templates.restore("old-seminar") |
| useAdminPageTitle called | vi.fn mock called with "Templates" |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree missing Phase 16 admin components**
- **Found during:** Setup before Task 1
- **Issue:** The worktree's working tree was from a pre-Phase-16 state. SideDrawer, Pagination, AdminTopBar, etc. were absent. AdminLayout.jsx lacked `useAdminPageTitle`.
- **Fix:** Used `git checkout HEAD -- frontend/src/components/admin/ frontend/src/pages/admin/AdminLayout.jsx frontend/src/lib/api.js` to pull the correct file versions from the commit HEAD (6ca37ab, which had Phase 16 content).
- **Files modified:** frontend/src/components/admin/ (all), frontend/src/pages/admin/AdminLayout.jsx, frontend/src/lib/api.js
- **Not a code change** — this was a worktree filesystem state correction.

**2. [Rule 1 - Test fix] Test queries too broad, caused "multiple elements found" errors**
- **Found during:** RED phase test run
- **Issue:** `screen.getByText(/name/i)` matched both the "Template name" label and the "Name" th header. `screen.getByText("New template")` matched both button and h1. `/type/i` matched "Type" heading and "URL slug" label text.
- **Fix:** Tightened queries: `table.querySelectorAll("th")` for header checks, `getByRole("heading", { name: "New template" })` for dialog title, `document.getElementById("tf-type")` for type select.

**3. [Rule 1 - Test fix] Archived template tests needed showArchived toggle first**
- **Found during:** RED → GREEN test run
- **Issue:** Restore button only renders when `showArchived` is true (by design). Tests that passed `[ARCHIVED_TEMPLATE]` directly to mock but didn't toggle the checkbox never saw the Restore button.
- **Fix:** Tests now mock list to return active templates first, then archived templates after toggle, and simulate clicking the "Show archived" checkbox before asserting.

## Known Stubs

None — all data flows from real API calls (`api.admin.templates.*`). No hardcoded values passed to rendering.

## Threat Flags

None — this plan adds no new network endpoints. All mutations go through existing `api.admin.templates.*` methods which send JWT via api.js. The AdminLayout route guard remains unchanged (T-17-07 already mitigated).

## Self-Check: PASSED

- `frontend/src/pages/admin/TemplatesSection.jsx` — EXISTS (626 lines, > 200 required)
- `frontend/src/pages/admin/__tests__/TemplatesSection.test.jsx` — EXISTS (312 lines, > 100 required, 12 tests)
- TemplatesSection.jsx does NOT contain `InlineEditCell` — VERIFIED
- TemplatesSection.jsx contains `import SideDrawer` — VERIFIED
- TemplatesSection.jsx contains `useAdminPageTitle("Templates")` — VERIFIED
- TemplatesSection.jsx contains `api.admin.templates.list` — VERIFIED
- TemplatesSection.jsx contains `api.admin.templates.create` — VERIFIED
- TemplatesSection.jsx contains `api.admin.templates.restore` — VERIFIED
- TemplatesSection.jsx contains `include_archived` — VERIFIED
- TemplatesSection.jsx contains `session_count` — VERIFIED
- TemplatesSection.jsx contains `"Archive this template?"` — VERIFIED
- TemplatesSection.jsx contains `"New template"` — VERIFIED
- vitest: 12/12 tests pass — VERIFIED
- Commit 89c1750 — EXISTS
