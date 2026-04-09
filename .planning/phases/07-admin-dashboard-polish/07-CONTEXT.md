---
name: Phase 7 Context
description: Admin dashboard polish — decisions locked autonomously
type: phase-context
---

# Phase 7: Admin Dashboard Polish — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary
Surface all admin operations behind a usable UI: eligibility overrides (phase 4), template CRUD (phase 5), CSV import trigger (phase 5), audit log viewer with filters, attendance CSV export, analytics views, CCPA access/deletion endpoint. No new backend capabilities — this phase wires UIs to endpoints that already exist (or thin admin wrappers around them).

Success criteria (ROADMAP.md):
1. Audit log filterable by user/action/date.
2. CSV import pipeline usable end-to-end from UI.
3. Manual override with reason visible on timeline.
4. Bulk module-template CRUD in one table view.
5. CSV export of volunteer hours + attendance rates.
6. CCPA data-access and deletion fulfillable via UI.
</domain>

<decisions>
## Implementation Decisions (locked)

### Admin dashboard layout
- Single-page `/admin` with a left-nav (desktop) / top-tab (mobile) for sections:
  - **Overview** — quick stats, recent activity
  - **Audit log** — filterable table
  - **Templates** — from phase 5 CRUD
  - **Imports** — CSV import (phase 5)
  - **Overrides** — prereq overrides (phase 4)
  - **Users** — search + CCPA actions
  - **Exports** — CSV downloads
- Reuses phase 1 primitives. Mobile-first but table-heavy sections get a secondary "open on desktop for full view" hint.

### Audit log viewer
- `GET /admin/audit-logs?user_id=&kind=&from=&to=&page=&page_size=` — new endpoint (or extend existing).
- Default page size 50, max 500.
- Filters: user picker (typeahead), action kind multi-select, date range picker.
- Search-by-keyword across `meta` JSONB — Postgres `jsonb @> '{"key":"value"}'` or `ts_vector` index (planner decides; default: simple ILIKE on `action` + JSON text cast).
- CSV export of current filter.

### Analytics views
- `GET /admin/analytics/volunteer-hours?from=&to=` → `[{user_id, name, hours, events}]`
- `GET /admin/analytics/attendance-rates?from=&to=` → `[{event_id, name, confirmed, attended, no_show, rate}]`
- `GET /admin/analytics/no-show-rates?from=&to=` → `[{user_id, rate, count}]`
- Frontend renders each as a sortable table + "Export CSV" button.
- No charting library — tables only this phase. Chart.js etc. deferred.

### Attendance CSV export
- `GET /admin/events/{id}/attendance.csv` → `user_name,email,status,checked_in_at,attended_at`.
- `GET /admin/analytics/volunteer-hours.csv` — same data as JSON endpoint, CSV format.

### CCPA endpoints
- `GET /admin/users/{id}/ccpa-export` → zip or JSON with all user data (signups, audit logs about them, notifications).
- `POST /admin/users/{id}/ccpa-delete` → soft delete user, anonymize PII (name→`[deleted]`, email→`deleted-{uuid}@example.invalid`), keep historical signups for stats integrity.
- Both are admin-only. Every call writes an `AuditLog(action='ccpa_export'|'ccpa_delete', reason=required)`.
- UI: user detail page has two clearly-labeled buttons, each with a confirm modal.
- **Retention policy:** documented in a new `docs/ccpa-policy.md` (TODO(copy) — Hung refines legal language).

### Eligibility override UI
- Table at `/admin/overrides` — list, filter by user, create, revoke.
- Create modal: user picker, module picker, required reason textarea (min 10 chars).
- Revoke action: confirm modal, logs audit event.

### Bulk module template CRUD
- Table at `/admin/templates` (from phase 5 foundation).
- Inline edit for name/capacity/duration/prereqs.
- Bulk delete with selection checkboxes + confirm modal.
- "Add template" opens a modal with the full form.

### CSV import UI surface
- `/admin/imports` — built in phase 5 but polished here:
  - History list of past imports with status chips.
  - Re-run a failed import (re-uses stored raw CSV).

### Permissions
- All endpoints require `role='admin'` — enforced at router layer.
- Organizers see a reduced set (imports + roster, no overrides, no CCPA).

### Claude's Discretion
- Exact layout of the overview cards.
- Date picker library (planner picks; prefer hand-rolled or react-day-picker).
- Whether analytics endpoints pre-aggregate or query on each request (planner: query on request, add index hints if slow).
</decisions>

<code_context>
- `backend/app/routers/admin.py` — existing admin router (from phase 0); extend.
- Phase 4 gives us `prereq_overrides`.
- Phase 5 gives us `module_templates` CRUD + imports.
- `AuditLog` model — the log viewer's data source.
- `frontend/src/pages/admin/` — new directory.
</code_context>

<specifics>
- CCPA delete is soft-delete + PII anonymize, not row deletion (preserves analytics).
- Audit log default page 50, max 500.
- Volunteer hours = sum of `slot_duration_minutes` across `status='attended'` signups.
- All admin actions must write to AuditLog.
</specifics>

<deferred>
- Charts/graphs (Chart.js etc.) — tables only this phase.
- Email templates editor — out of scope.
- Role-based granular permissions beyond admin/organizer/student — out of scope.
- Real-time dashboard via websockets — out of scope.
</deferred>

<canonical_refs>
- `.planning/ROADMAP.md` — Phase 7 success criteria
- `.planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md`
- `.planning/phases/05-event-template-system-llm-normalized-csv-import/05-CONTEXT.md`
- `backend/app/routers/admin.py`
- California CCPA: https://oag.ca.gov/privacy/ccpa
</canonical_refs>
