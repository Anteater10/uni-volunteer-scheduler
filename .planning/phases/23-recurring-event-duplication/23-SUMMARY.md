---
phase: 23-recurring-event-duplication
plan: 01
status: complete
branch: v1.3
commits:
  - 4855ba7 — docs(23): add PLAN for recurring event duplication
  - 669a27d — feat(23): event_duplication_service + admin endpoint + tests
  - d7c8e89 — feat(23): DuplicateEventDrawer + AdminEventPage wiring
---

# Phase 23 — Recurring event duplication — SUMMARY

One-click admin duplication of an event across multiple target weeks.
Preserves slots (time-of-day offsets relative to event start), copies
`events.form_schema` JSONB verbatim (Phase 22 contract), detects conflicts
by `(quarter, year, week_number, module_slug)`, and guarantees atomicity —
with `skip_conflicts=false` any conflict aborts before any inserts. Writes
ONE audit row per duplication action with source + targets + skipped
weeks.

## What shipped (mapped to requirements)

- **DUP-01 — duplication service** —
  `backend/app/services/event_duplication_service.py::duplicate_event(db,
  source_event_id, target_weeks, target_year, skip_conflicts, actor)`.
  Returns `{created: [{id, week_number, start_date}], skipped_conflicts:
  [{week, existing_event_id}]}`. Copies title, description, location,
  visibility, branding_id, module_slug, school, venue_code, quarter,
  max_signups_per_user, reminder_1h_enabled, form_schema (as-is; NULL
  stays NULL so template default still wins). Shifts start_date /
  end_date / signup_open_at / signup_close_at by the week delta.
- **DUP-02 — admin UI** —
  `frontend/src/components/admin/DuplicateEventDrawer.jsx` with 11 week
  chips, year toggle (source year / source year + 1), conflict
  highlighting, preview copy, skip-conflicts toggle (default ON).
  `AdminEventPage.jsx` gains a "Duplicate…" button in the action row.
- **DUP-03 — slot-time pattern** — for each source Slot, a new Slot is
  built with `start_time/end_time` shifted by `(target_week -
  source_week) * 7 days`, `capacity` and `slot_type` preserved,
  `current_count=0`, `date` rederived from the shifted start time.
- **DUP-04 — conflict detection** — probe query keyed on
  `(quarter, year, week_number, module_slug)`. Source's own week is
  treated as an implicit conflict when `target_year == source.year` and
  it appears in the requested weeks. Frontend reuses the public
  per-week list endpoint to pre-highlight conflict chips without an
  extra round-trip.
- **DUP-05 — atomic commit** — whole batch runs inside a single
  `db.commit()`; any exception triggers `db.rollback()`. With
  `skip_conflicts=false`, the conflict probe raises `HTTPException(409,
  detail={error: "conflicts", skipped_conflicts: [...]})` BEFORE any
  inserts — the rollback test verifies 0 new events land.
- **DUP-06 — audit entry** — single `AuditLog` row per call with action
  `event_duplicate`, entity `Event:<source_id>`, `extra` payload
  `{source_event_id, target_event_ids, target_weeks, target_year,
  skip_conflicts, skipped_weeks}`. Humanize entry added to
  `audit_log_humanize.ACTION_LABELS` ("Duplicated an event"). Phase 22
  form_schema actions were also backfilled into the same map.
- **DUP-07 — Playwright** — deferred to Phase 29 (same pattern as
  Phases 21 / 22 — seed-e2e infra). Unit + component tests cover the
  same flows.

## Backend endpoint

`POST /admin/events/{event_id}/duplicate` (admin-only) — body
`{target_weeks: [5,6,7], target_year: 2026, skip_conflicts: true}`.
Lives at the end of the Phase 22 form-schema block in
`backend/app/routers/admin.py`.

## No migration

Phase 22 already shipped `events.form_schema` JSONB, and Phase 08
already shipped `quarter` / `year` / `week_number` / `module_slug` /
`school` / `venue_code`. Phase 23 therefore lands without a new
migration — the last migration on `v1.3` remains 0015.

## Deviations from PLAN / CONTEXT

- **Implicit source-week conflict** — CONTEXT didn't call this out, but
  we treat the source's own `(year, week_number)` as a conflict so an
  admin can't accidentally "duplicate into itself." It only fires when
  that week is in the requested list, so the common path stays clean.
- **Sibling prefetch strategy** — frontend uses the existing public
  per-week list endpoint (`GET /public/events?quarter=&year=&week_number=`)
  instead of a new admin endpoint. Eleven lightweight requests per
  drawer open; cached in TanStack Query. Keeps Phase 23 strictly
  read-only on the admin event surface.
- **Skipped-weeks audit payload** — includes both `target_weeks` (what
  the admin asked for) and `skipped_weeks` (which of those ended up
  being skipped) so the audit trail is self-describing without needing
  to diff against created events.

## Test results

- **Backend pytest:** 274 passed, 2 failed. All 5 new tests in
  `test_event_duplication_service.py` pass. The 2 failures
  (`test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence`,
  `test_commit_rollback_on_integrity_error`) are the same
  pre-existing v1.3 baseline failures documented in Phase 21 / 22
  SUMMARY files — unrelated to Phase 23.
- **Frontend vitest:** 169 passed, 6 failed. All 6 new tests in
  `DuplicateEventDrawer.test.jsx` pass. The 6 failures are the same
  pre-existing AdminTopBar / AdminLayout / ExportsSection /
  ImportsSection failures flagged in Phase 22 SUMMARY — unrelated to
  Phase 23.
- **Alembic:** no new migration this phase; head remains 0015.

## Files

### New
- `backend/app/services/event_duplication_service.py`
- `backend/tests/test_event_duplication_service.py`
- `frontend/src/components/admin/DuplicateEventDrawer.jsx`
- `frontend/src/components/admin/__tests__/DuplicateEventDrawer.test.jsx`
- `.planning/phases/23-recurring-event-duplication/23-PLAN.md`
- `.planning/phases/23-recurring-event-duplication/23-SUMMARY.md`

### Edited
- `backend/app/routers/admin.py` (new POST endpoint)
- `backend/app/services/audit_log_humanize.py` (new labels)
- `frontend/src/lib/api.js` (new `admin.duplicateEvent`)
- `frontend/src/pages/AdminEventPage.jsx` (button + drawer mount + sibling query + mutation)

## Next phase considerations

- **Phase 24 — reminder emails** — duplicated events inherit the
  source's reminder_1h_enabled flag; confirm the Beat schedule
  recomputes windows from each event's own start_date (it should, but
  we haven't exercised it with a real Beat run).
- **Phase 25 — waitlist** — irrelevant to duplication (signups are not
  copied), but if Phase 25 adds slot-level waitlist positions those
  also should NOT carry over.
- **Phase 29 — Playwright** — cross-feature spec for "admin duplicates
  4-week module → organizer adds a custom field → volunteer signs up"
  is the canonical home for the DUP-07 e2e.
