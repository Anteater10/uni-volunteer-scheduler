# Phase 23: Recurring event duplication — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

One-click "Duplicate this event to weeks N…M" from the admin. Preserves slots (pattern), form schema, title. Atomic commit. Warns on conflicts. Audits every run.

</domain>

<decisions>
## Implementation Decisions

### What gets copied
- Event basics: title, module_slug, venue, description, start/end time-of-day, day-of-week pattern, capacity.
- ALL slots attached to source event (same slot_type, time-of-day offset from event start, capacity).
- `events.form_schema` (Phase 22 added this — must copy as-is, NOT fall back to template default because the source event may have customized it).
- Quarter + year derived from current event + target week number. Week numbers input by admin.

### What does NOT get copied
- Signups (obviously).
- Audit log entries (they belong to the source).
- `signup_opens_at`/`signup_closes_at` windows (Phase 29) — if those land before 23, copy them too; else skip.
- Created-by user is the admin running duplicate, not the source's creator.

### Conflict detection
- For each target week, check if an event already exists with same `(quarter, year, week_number, module_slug)`. If yes → add to conflict list.
- Admin sees conflict warning: "Week 7 already has a CRISPR event — skip or cancel?" Default is skip-existing (i.e., don't overwrite), not cancel-everything.

### Atomicity
- Use a single DB transaction for the whole batch. Either all target events + slots land, or none do.

### API
- `POST /admin/events/{id}/duplicate` with body `{target_weeks: [5,6,7], target_year: 2026, skip_conflicts: true}` → returns `{created: [event_ids], skipped_conflicts: [{week, reason}]}`.

### Frontend
- `AdminEventPage.jsx` — add "Duplicate…" button in the action row.
- New component `frontend/src/components/admin/DuplicateEventDrawer.jsx`:
  - Week multiselect chips (show current quarter's remaining weeks + option to cross into next quarter via a year toggle).
  - Preview: "Creating N events (weeks 5, 6, 7). 1 conflict: week 7 already exists — will be skipped."
  - Confirm/cancel buttons.
- Success toast shows link to each new event.

### Audit
- Single audit log row per duplication action: `action=event_duplicate`, payload `{source_event_id, target_event_ids, skipped_weeks, actor}`.
- Add humanize entry in `audit_log_humanize.py`.

### Tests
- `backend/tests/test_event_duplication_service.py`:
  - Happy path: 1 source + 3 targets → 3 events + correct slot counts.
  - Conflict path: 1 conflicts, 2 succeed, skip_conflicts=true → 2 created, 1 skipped.
  - Conflict path: skip_conflicts=false + any conflict → 0 created (atomic rollback).
  - form_schema copied verbatim.
- Playwright: admin duplicates 4-week module from event detail page.

</decisions>

<code_context>
## Existing Code Insights

- `backend/app/models.py` — Event model has `quarter`, `year`, `week_number`, `module_slug`, plus slot relationship.
- `backend/app/services/template_service.py` (Phase 17) — event-creation pattern.
- `backend/app/services/import_service.py` (Phase 18) — atomic commit pattern used by LLM CSV import; mirror this transaction shape.
- `frontend/src/components/SideDrawer.jsx` pattern — reuse.
- `frontend/src/pages/AdminEventPage.jsx` — has the action row today.

</code_context>

<specifics>
## Specific Ideas

- Week multiselect UX: chips for weeks 1..11 (SciTrek quarter length). Disabled chips for weeks with existing events; check-on-click otherwise. Selected chips highlighted.

</specifics>

<deferred>
## Deferred Ideas

- Duplicating events across multiple modules in one batch.
- Templated recurring rules ("every Wednesday for 4 weeks starting week 5").

</deferred>

---

*Phase: 23-recurring-event-duplication*
*Context gathered: 2026-04-17*
