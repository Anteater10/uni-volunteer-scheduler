---
phase: 23-recurring-event-duplication
plan: 01
requirements_addressed: [DUP-01, DUP-02, DUP-03, DUP-04, DUP-05, DUP-06, DUP-07]
objective: >
  One-click admin action to duplicate an event across multiple weeks with slot
  pattern preservation, form_schema cloning, conflict detection, atomic commit,
  and audit. No new migration — Event + Slot models already carry everything
  needed (Phase 22 shipped events.form_schema JSONB; Phase 08 shipped
  quarter/year/week_number/module_slug).
files_modified:
  # Backend — new
  - backend/app/services/event_duplication_service.py
  - backend/tests/test_event_duplication_service.py
  # Backend — edits
  - backend/app/routers/admin.py
  - backend/app/services/audit_log_humanize.py
  # Frontend — new
  - frontend/src/components/admin/DuplicateEventDrawer.jsx
  - frontend/src/components/admin/__tests__/DuplicateEventDrawer.test.jsx
  # Frontend — edits
  - frontend/src/lib/api.js
  - frontend/src/pages/AdminEventPage.jsx
must_haves:
  - event_duplication_service.duplicate_event(db, source_event_id, target_weeks,
    target_year, skip_conflicts, actor_user_id) copies event basics + all slots
    + events.form_schema verbatim; preserves per-slot time-of-day offsets
    relative to event.start_date; sets created_by (owner_id) to actor.
  - Conflict key: (quarter, year, week_number, module_slug). Quarter derived
    from source event (week-number-agnostic within same calendar-year quarter)
    or retained from source when target_year matches source year. If the source
    has no quarter, fall back to copying the source's quarter verbatim.
  - skip_conflicts=true: create non-conflicting targets, record skipped list.
  - skip_conflicts=false + any conflict: raise, commit nothing (atomic).
  - One audit row per call: action=event_duplicate, entity_type=Event,
    entity_id=source_event_id, extra={source_event_id, target_event_ids,
    skipped_weeks, target_year, skip_conflicts}.
  - POST /admin/events/{event_id}/duplicate endpoint returns
    {created: [event_ids], skipped_conflicts: [{week, existing_event_id}]}.
  - Humanize entry for event_duplicate.
  - DuplicateEventDrawer renders week chips 1..11 with conflict highlighting,
    optional next-year toggle, preview count, skip-conflicts toggle (default ON),
    submit CTA; success toast links to first created event.
  - "Duplicate…" button added to AdminEventPage action row.
  - api.admin.duplicateEvent wired in frontend/src/lib/api.js.
  - Backend unit tests in test_event_duplication_service.py cover happy path,
    skip-conflicts, atomic rollback, form_schema verbatim.
  - Frontend unit test covers DuplicateEventDrawer state + conflict-chip render.
---

# 23-PLAN — Recurring event duplication

## Task 1 — Backend service

`backend/app/services/event_duplication_service.py`:

- `DuplicateResult` dataclass/TypedDict: `{created: list[str], skipped_conflicts: list[{week: int, existing_event_id: str}]}`.
- `duplicate_event(db, source_event_id, target_weeks, target_year, skip_conflicts, actor)`:
  1. Load source event. 404 if missing.
  2. For each target week, compute target `(quarter, year, week, module_slug)` key. Quarter is copied from source event (source owns the quarter; admin picks target weeks within same quarter by default, but target_year lets cross into another calendar year). If source has no quarter, pass `None` so conflict check never matches and we still create.
  3. Query existing events with same key → build skipped list.
  4. If `skip_conflicts=false` and skipped non-empty → HTTP 409 (`skipped_conflicts` in detail) before any inserts.
  5. For each non-conflict target week, build a new Event copying: owner_id=actor.id, title, description, location, visibility, module_slug, school, form_schema (copy as list if set), venue_code, quarter (from source), year=target_year, week_number=target_week, max_signups_per_user. Shift start_date/end_date by (target_week - source_week) weeks.
  6. For each Slot on the source, build a new Slot with the same shift: start_time/end_time, capacity (preserve), slot_type, date=new start_time.date(), location. current_count=0.
  7. `db.flush()` to get new event IDs. Build result list.
  8. Write ONE audit log row via `log_action`.
  9. `db.commit()`.
  10. On any exception → `db.rollback()`, re-raise.

## Task 2 — Router endpoint

`backend/app/routers/admin.py` gets:

```python
@router.post("/events/{event_id}/duplicate")
def duplicate_event_endpoint(event_id: UUID, body: DuplicateEventRequest,
                             db, admin_user):
    return event_duplication_service.duplicate_event(
        db, event_id, body.target_weeks, body.target_year,
        body.skip_conflicts, actor=admin_user,
    )
```

Body is a plain dict (mirrors form_schema handler pattern) — we don't need to
add a Pydantic schema class for one endpoint. Admin role required.

## Task 3 — Humanize entry

Add `"event_duplicate": "Duplicated an event"` to `ACTION_LABELS` in
`audit_log_humanize.py`. Entity already humanizes via `event`.

## Task 4 — Frontend API client

`frontend/src/lib/api.js` — add under `admin:`:

```js
duplicateEvent: (eventId, { target_weeks, target_year, skip_conflicts }) =>
  request(`/admin/events/${eventId}/duplicate`, {
    method: "POST",
    body: { target_weeks, target_year, skip_conflicts },
  }),
```

Also add `admin.events.listByQuarter(quarter, year)` shortcut if needed for
conflict prefetch — actually reuse `api.admin.events({ quarter, year })` if
that exists; otherwise fall back to fetching per-week via the duplicate
endpoint's 409 response.

## Task 5 — DuplicateEventDrawer component

`frontend/src/components/admin/DuplicateEventDrawer.jsx` — props:
- `sourceEvent` (must carry quarter/year/week_number/module_slug/title).
- `existingEvents` — array of `{week_number, id}` for conflict highlighting.
- `isOpen`, `onClose`, `onSuccess(result)`.

State:
- `selectedWeeks: number[]`
- `targetYear: number` (default = sourceEvent.year)
- `skipConflicts: boolean` (default true)

UI:
- Week chips 1..11 (`WEEKS_PER_QUARTER`). Conflict weeks get red ring + label "conflict". Clicking selects/deselects.
- Year toggle: radio ("same year", "next year").
- Preview: "Creating N events (weeks X, Y, Z). M conflicts — will be skipped."
- Skip-conflicts toggle.
- Submit button → mutation calls API → on success toast + onSuccess.

## Task 6 — AdminEventPage wiring

- Add `[duplicateOpen, setDuplicateOpen]` state.
- Add "Duplicate…" button next to "Download roster CSV" in the action row.
- Mount `<DuplicateEventDrawer>` at the bottom like `FormFieldsDrawer`.
- On success, toast with count + link to admin events list (or first new event detail).

## Task 7 — Tests

### Backend (`backend/tests/test_event_duplication_service.py`)
- `test_duplicate_happy_path` — one source with 2 slots, duplicate to weeks [5, 6, 7] → 3 new events, 6 new slots total, correct week shifts, form_schema copied.
- `test_duplicate_skip_conflicts` — pre-create a conflicting event at week 7; duplicate to [5, 6, 7] with skip=true → 2 created, 1 skipped.
- `test_duplicate_atomic_rollback` — pre-create conflict at week 7; duplicate to [5, 6, 7] with skip=false → raises HTTPException, 0 created.
- `test_duplicate_copies_form_schema_verbatim` — source has form_schema override → new events have identical schema.

### Frontend (`__tests__/DuplicateEventDrawer.test.jsx`)
- Renders week chips with conflict highlight.
- Toggles selection + preview text.
- Calls `onSave` (mutation) with correct payload.

## Task 8 — Verification

- `docker run --rm --network uni-volunteer-scheduler_default ... pytest -q` — new tests pass; no regressions vs Phase 22 baseline (same pre-existing failures OK).
- `cd frontend && npm run test -- --run` — new DuplicateEventDrawer tests pass; no regressions.
- No migration to run.

## Task 9 — Atomic commits with `(23)` scope

## Task 10 — SUMMARY

Write `23-SUMMARY.md` following standard shape (status: complete, commits list, what-shipped per requirement, test results).
