# Shifts — design

**Date:** 2026-08-02
**Status:** approved (design review with Hung)
**Sequencing:** lands after `2026-08-02-read-only-volunteer-signups-design.md`,
which deletes the self-cancel/self-swap/auto-promotion machinery this
redesign would otherwise have to rewire.

## Problem

Today volunteers book individual *period slots* one at a time, and
"Period 1 / Period 2" labels are invented by the frontend (numbering
slots by time-of-day per date — `EventDetailPage.jsx`); slots have no
name, order, or grouping in the database. The professors want volunteers
to sign up for a **Shift** — an organizer-named bundle such as
"Shift 1 = periods 1 and 2 on Tuesday and Wednesday" — committing to all
of its sessions as a package, with organizer-controlled naming and
display order at both the shift and session level.

## Decisions

1. **A shift is an all-or-nothing package.** One signup covers every
   session in the shift. One capacity number and one waitlist per shift.
   Individual sessions are no longer separately bookable.
2. **Shifts are defined per event**, in the same place slots are managed
   today. No module-level shift templates (duplicate-event copies shifts).
3. **Shift-level signup rows** (option B of the design review): a
   `shift_signups` row carries the lifecycle; per-session attendance is
   recorded separately. No fan-out signup rows, no slot dual-identity.
4. **Orientation is untouched.** Orientation slots stay individually
   bookable; the orientation-credit gate now applies to shift signups.
5. **Legacy period slots are migrated** into single-session shifts so the
   app has exactly one model. No legacy code path.
6. **Vocabulary:** user-facing copy says *shift* and *session*. The DB
   keeps `slot_type = 'period'` for sessions (renaming the Postgres enum
   buys nothing and enum migrations carry a known downgrade bug).

## Data model

### New table `shifts`

| column | notes |
|---|---|
| `id` | UUID PK |
| `event_id` | FK → events, cascade |
| `name` | required, organizer-chosen ("Shift 1", "Morning crew") |
| `sort_order` | int; organizer-controlled display order within the event |
| `capacity` | int > 0 |
| `current_count` | int; same counter + `SELECT … FOR UPDATE` capacity pattern slots use today |

### `Slot` gains three columns

- `shift_id` — nullable FK → shifts. NULL ⇒ orientation slot (unchanged
  behavior). After migration every `period` slot has a shift.
- `name` — nullable; organizer-chosen session label ("Period 1").
- `sort_order` — int; session order within its shift.

Sessions keep real `date`/`start_time`/`end_time`/`location` — check-in
windows, ICS entries, and event auto-completion (last slot ends) depend
on them. Per-session `capacity`/`current_count` become inert for shift
members; capacity lives only on the shift.

### New table `shift_signups`

| column | notes |
|---|---|
| `id` | UUID PK |
| `shift_id` | FK → shifts, cascade |
| `volunteer_id` | FK → volunteers |
| `status` | `SignupStatus`, lifecycle values only: pending / confirmed / waitlisted / cancelled |
| `timestamp` | signup time; waitlist position = `timestamp ASC, id ASC` per shift (today's rule, one level up) |

Unique on `(volunteer_id, shift_id)`.

### New table `session_attendance`

| column | notes |
|---|---|
| `id` | UUID PK |
| `shift_signup_id` | FK → shift_signups, cascade |
| `slot_id` | FK → slots (the session) |
| `checked_in_at` | nullable timestamp |
| `status` | checked_in / attended / no_show |

Unique on `(shift_signup_id, slot_id)`. Rows are created only when
check-in or close-out actually happens — commitment lives in
`shift_signups`, "did they show up Tuesday period 1" lives here.
Orientation signups keep using `Signup` end to end.

## Flows

- **Public signup** (`public_signup_service.py`): request schema gains
  `shift_ids` alongside `slot_ids`; `slot_ids` are valid only for
  orientation slots — a bare period-slot id is rejected. Same
  one-event-per-batch rule. Full shift ⇒ `waitlisted`, else `pending` +
  `current_count += 1` under the shift row lock.
- **Orientation gate**: a batch containing shifts and no orientation slot
  requires existing family credit — same logic, retargeted from period
  slots to shifts.
- **Confirm**: batch semantics unchanged — one email, one magic link;
  consuming it confirms all the batch's pending bookings, `Signup` and
  `shift_signups` alike. `magic_link_tokens.signup_id` becomes nullable
  and the table gains a nullable `shift_signup_id` FK with a CHECK that
  exactly one anchor is set (a shift-only batch has no `Signup` row to
  anchor to); consume keeps resolving the rest of the batch by
  email + event as today.
- **Staff moves**: the staff swap/move tooling retargets to the new
  bookable units — staff move a volunteer between shifts (or between
  orientation slots) rather than between period slots. Same guards
  (target full ⇒ refuse, no waitlist fallback), now against shift
  capacity.
- **Manage page** (read-only per the companion spec): lists orientation
  signups and shift signups (shift name + its sessions + waitlist
  position).
- **Waitlist**: admin/organizer promotes a waitlisted shift signup →
  `pending` + 3-day confirm email (companion spec flow). Raising shift
  capacity opens seats but promotes nobody.
- **Check-in**: volunteer checks in at the venue as today; the resolver
  finds the in-window *session* whose shift they hold a confirmed
  shift signup for and writes `session_attendance` (`checked_in`).
  Orientation check-in unchanged.
- **Close-out**: organizer ends a *session* and marks attended/no-show
  per volunteer into `session_attendance`. Ending an orientation slot
  still grants orientation credits exactly as now.
- **Rosters/hours**: a session roster = confirmed members of the owning
  shift annotated with that session's attendance; volunteer hours count
  attended sessions.

## Admin / organizer UI

- **Event editor** (`EventsSection.jsx` modal): the flat slot list splits
  into **Orientation slots** (today's row unchanged) and **Shifts**. A
  shift row = name + capacity with up/down reorder; expanded, it lists
  its sessions (name, date, start, end, location) with their own up/down
  order. Removing a shift is blocked once it has active signups (same
  rule slots have today). Duplicate-event copies shifts + sessions.
- **Roster view** (`AdminEventPage.jsx`): sessions grouped under shift
  headers; waitlist panel per shift with promote (over-capacity confirm
  stays) and manual reorder (the per-slot reorder endpoint moves to
  shifts); attendance marked per session at close-out.
- **Broadcasts** (`BroadcastModal.jsx`): recipient picker offers shifts
  and orientation slots instead of raw slots.

## Volunteer UI

`EventDetailPage.jsx` replaces the derived per-date period table (the
`_periodLabel` logic dies) with ordered **shift cards**: shift name,
seats left / waitlist state, sessions inside in organizer order with
name, date, time, location. Volunteers toggle whole shifts plus
orientation slots. `SignupSuccessCard`, emails, and calendar invites
render the shift name with one ICS entry per session.

## Migration (one Alembic revision, descriptive-slug id)

1. Create `shifts`, `shift_signups`, `session_attendance`; add the three
   `Slot` columns.
2. Backfill per event: each existing period slot → a single-session shift
   (name from the slot's weekday + time, e.g. "Tue 9:00–10:30";
   capacity = slot capacity; `sort_order` by date/time), with the slot as
   its only session.
3. Convert that slot's signups: lifecycle statuses map 1:1 to
   `shift_signups` (same status + timestamp); attendance outcomes
   (checked_in / attended / no_show) become a **confirmed** shift signup
   plus a `session_attendance` row carrying the outcome and
   `checked_in_at`. Converted period `Signup` rows are then deleted.
   Orientation signups untouched.
4. **Accepted casualty (say it in the migration docstring):** outstanding
   magic-link tokens anchored to a converted period signup die with it
   (FK cascade). Pre-production this costs nothing real; a re-send covers
   any dev/demo case. Tokens anchored to orientation signups survive.
5. Downgrade reverses the mapping best-effort; no new Postgres enums are
   created, so the known enum downgrade bug is not extended.

## Tests

- **Backend:** shift CRUD + ordering; signup service — shift capacity,
  waitlist entry, unique constraint, one-event batch, orientation gate on
  shifts, rejection of bare period-slot ids; batch confirm covering shift
  signups; check-in resolver per session; close-out attendance; promote
  flow (pending + confirm); migration test seeding old-shape data and
  asserting the conversion (pattern:
  `test_orientation_backfill_migration`-style seeded migration test).
- **Frontend:** shift builder (add/rename/reorder shifts and sessions),
  EventDetailPage shift selection, read-only manage rendering of shift
  signups, DuplicateEventModal copies shifts.
- **e2e:** cross-role signup scenario picks a shift;
  `docs/smoke-checklist.md` updated.
- **Docs/KB:** `05-events.md`, `06-slots.md` (major rewrite),
  `07-modules.md`, `02-glossary.md`, task guides — shift/session
  vocabulary; corpus re-ingest.

## Out of scope

- Module-level shift templates (revisit if per-event definition proves
  repetitive).
- Per-session capacity for shift members.
- Any automatic waitlist promotion (removed by the companion spec).
- `Event.max_signups_per_user` enforcement (still decorative; unchanged).
