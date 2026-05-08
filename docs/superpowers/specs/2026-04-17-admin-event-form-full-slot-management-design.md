# Admin Event Form — Full Slot Management

**Date:** 2026-04-17
**Status:** Approved
**Milestone:** v1.2 final (Milestone1.2Final branch)

## Problem

Admins can create events through the `/admin/events` page, but the current
`EventForm` only collects metadata (title, description, location, start/end,
visibility, max signups). It has no slot fields and no way to specify school.

Result: admin-created events are empty — participants see them as "full" because
there are no slots to sign up for. The only paths that produce usable events
today are the quarterly CSV import and the E2E seed script.

Production parity with tools like SignUpGenius requires a single form flow
where an admin can create **and edit** an event with its slots in place.

## Scope

**In scope:**
- Extend `EventForm` with a repeatable slots section (1..N slots) and a
  `school` field.
- Create flow: single `POST /events/` includes `slots[]` in the payload.
- Edit flow: metadata `PUT /events/{id}` plus a client-side diff that issues
  `POST /slots`, `PATCH /slots/{id}`, `DELETE /slots/{id}` for added, changed
  and removed slots.
- Client-side validation matching backend rules.
- Vitest coverage for the form and the edit-diff path.

**Out of scope (v1.3 parking lot):**
- Custom question editor (separate `/events/{id}/questions` endpoint exists).
- Recurring / bulk slot generation UI wrapper for `/events/{id}/generate_slots`.
- Module template binding (`module_slug`) — belongs with the templates work.

## Form fields

Ordered as they will appear:

1. Title *(required)*
2. Description
3. Location
4. Visibility (`public` | `private`)
5. Start date *(required)*
6. End date *(required)*
7. Max signups per user (blank = unlimited)
8. School (optional)
9. **Slots section** — at least one required on create
   - slot_type dropdown: `orientation` | `period`
   - date (defaults to event start date)
   - start_time, end_time (HTML `time` inputs, combined with the date)
   - capacity (positive integer)
   - location (defaults to event location)
   - remove button; disabled if slot's `current_count > 0` — shows
     "Has N signups, can't remove" inline
   - `+ Add slot` button appends a new empty row

## Data flow

### Create

```
POST /api/v1/events/
{
  title, description, location, visibility,
  start_date, end_date, max_signups_per_user,
  school,
  slots: [
    { slot_type, date, start_time, end_time, capacity, location },
    ...
  ]
}
```

Backend already supports this payload. `quarter/year/week_number` are
auto-derived from `start_date` (fix shipped earlier this session).

### Edit

Client diffs the edited slot list against the original loaded slots:

| Condition | Action |
|-----------|--------|
| `initial.slots` contains `id` not in `draft.slots` | `DELETE /slots/{id}` |
| `draft.slots` row has no `id` | `POST /slots` with `{event_id, ...}` |
| Row `id` matches and any field differs | `PATCH /slots/{id}` with changed fields |

Sequence inside the edit mutation:

1. `PUT /events/{id}` with metadata.
2. On success, run the slot `POST` / `PATCH` / `DELETE` calls in parallel via
   `Promise.allSettled`.
3. Collect per-slot results. If any rejected, surface a toast listing the
   failing slot indexes and keep the drawer open so the operator can retry.
4. On full success, invalidate the events query and close.

## Validation

Client-side, mirroring backend constraints so the form fails fast:

- `title` non-empty.
- `end_date > start_date`.
- Each slot: `end_time > start_time`, `capacity > 0`.
- Each slot's combined `date + start_time` and `date + end_time` must fall
  within `[event.start_date, event.end_date]`.
- `school` free-text, capped at 100 chars (matches backend column).

Errors render inline next to the offending input and block submission.

## Files touched

1. `frontend/src/pages/admin/EventsSection.jsx`
   - Extend `EMPTY_FORM`, `EventForm` render, and `handleSubmit` payload.
   - Extend `updateMutation` to perform the slot diff after metadata `PUT`.
2. `frontend/src/lib/api.js`
   - Ensure `api.slots.create / update / delete` exist. Add missing ones.
3. `frontend/src/pages/admin/__tests__/EventsSection.test.jsx`
   - New file (or new suite) with tests listed below.

## Tests (vitest + @testing-library/react)

- `renders empty slot row on open` — create mode seeds one blank slot.
- `add / remove slot rows` — clicking `+ Add slot` and `Remove` updates state.
- `rejects end_time ≤ start_time` — inline error, submit blocked.
- `rejects capacity ≤ 0` — inline error.
- `rejects slot outside event range` — inline error.
- `create submit posts correct payload shape` — spies on `api.events.create`
  and asserts slots array present.
- `edit mode diff — POST for new rows, PATCH for changed, DELETE for removed`
  — spies on all three `api.slots.*` mutations and asserts each is called
  with expected args.
- `edit mode disables remove on slot with current_count > 0` — DOM assertion
  and inline warning text.

Backend tests: no new coverage needed. `POST /events/` with slots is already
covered; `derive_quarter_week` was added earlier with verification.

## Risks / unknowns

- The existing `PATCH /slots/{id}` accepts partial bodies — confirm before
  writing the diff (if it doesn't, switch to a full-slot `PUT` pattern).
- Reducing a slot's capacity below `current_count` should be rejected server
  side today; the form surfaces that as a submission error, it doesn't attempt
  any client-side blocking beyond the `current_count` removal guard.
- Timezone handling: HTML `time` input gives `HH:MM` wall-clock. We combine
  with `date` and send as an ISO string with the browser's local offset. The
  backend already normalizes to UTC.

## Success criteria

1. From the admin UI, create a new event with at least one slot in one
   submission. The participant view (`/events`) shows the event with correct
   capacity and filled count.
2. Edit an existing event: add a new slot, modify an existing slot's capacity,
   delete an unused slot. All three changes persist and are reflected in
   both admin and participant views.
3. Vitest suite passes. The existing Playwright `cross-role.spec.js` still
   passes (slot-based flow unchanged at the API level).
