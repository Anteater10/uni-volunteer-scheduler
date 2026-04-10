---
phase: 03
plan: 02
name: Service Layer — transition rules, SELECT FOR UPDATE, audit logging
wave: 2
depends_on: [03-01]
files_modified:
  - backend/app/signup_service.py
  - backend/app/services/check_in_service.py
  - backend/tests/test_check_in_service.py
autonomous: true
requirements:
  - Transition whitelist enforcement
  - SELECT ... FOR UPDATE row lock
  - Idempotent first-write-wins on concurrent check-in
  - Audit log on every transition
---

# Plan 03-02: Service Layer — Transition Rules + Row Lock + Audit

<objective>
Centralize signup state transitions in a service layer that (a) enforces the
allowed-transition whitelist, (b) holds a `SELECT ... FOR UPDATE` row lock for
the duration of any check-in write, (c) is idempotent on repeat check-in calls,
and (d) writes an `AuditLog` row on every successful transition.
</objective>

<must_haves>
- New module `backend/app/services/check_in_service.py` exports:
  - `check_in_signup(db, signup_id, actor_id, via)` — row-locked, idempotent
  - `resolve_event(db, event_id, actor_id, attended_ids, no_show_ids)` — atomic batch
  - `self_check_in(db, event_id, signup_id, venue_code, now)` — venue + time gate
- Allowed transitions enforced; invalid transitions raise `InvalidTransitionError`
- Every successful transition writes `AuditLog(action="transition", meta={from, to, via})`
- Idempotent: repeat `check_in_signup` on already-checked-in row returns existing row without raising and WITHOUT writing a second audit log entry
- Time window constants `CHECK_IN_WINDOW_BEFORE = timedelta(minutes=15)`, `CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)` defined and exported
</must_haves>

<tasks>

<task id="03-02-01" parallel="false">
<action>
Create `backend/app/services/check_in_service.py`. Define:

```python
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.app.models import Signup, SignupStatus, Event, AuditLog

CHECK_IN_WINDOW_BEFORE = timedelta(minutes=15)
CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)

ALLOWED_TRANSITIONS: dict[SignupStatus, set[SignupStatus]] = {
    SignupStatus.pending:    {SignupStatus.confirmed, SignupStatus.cancelled},
    SignupStatus.confirmed:  {SignupStatus.checked_in, SignupStatus.no_show, SignupStatus.cancelled},
    SignupStatus.checked_in: {SignupStatus.attended, SignupStatus.no_show, SignupStatus.cancelled},
    SignupStatus.attended:   set(),
    SignupStatus.no_show:    set(),
    SignupStatus.waitlisted: {SignupStatus.pending, SignupStatus.cancelled},
    SignupStatus.cancelled:  set(),
}

class InvalidTransitionError(Exception):
    def __init__(self, from_status, to_status):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition {from_status} -> {to_status}")

class CheckInWindowError(Exception):
    pass

class VenueCodeError(Exception):
    pass
```

Then implement three public functions:

1. `_transition(db, signup, new_status, actor_id, via)` — internal helper:
   - If `new_status not in ALLOWED_TRANSITIONS[signup.status]` → raise `InvalidTransitionError`.
   - Record `old = signup.status`; set `signup.status = new_status`.
   - If transitioning INTO `checked_in`, set `signup.checked_in_at = datetime.now(timezone.utc)`.
   - Append an `AuditLog` row with `actor_id`, `entity="signup"`, `entity_id=signup.id`, `action="transition"`, `meta={"from": old.value, "to": new_status.value, "via": via}`.
   - `db.flush()`.

2. `check_in_signup(db, signup_id, actor_id, via="organizer")`:
   - `signup = db.execute(select(Signup).where(Signup.id == signup_id).with_for_update()).scalar_one_or_none()`
   - If `signup is None`: raise `LookupError`.
   - **Idempotency:** if `signup.status == SignupStatus.checked_in`: return `signup` as-is (no audit log, no error).
   - Otherwise call `_transition(db, signup, SignupStatus.checked_in, actor_id, via)`.
   - Return `signup`.

3. `self_check_in(db, event_id, signup_id, venue_code, actor_id, now=None)`:
   - `now = now or datetime.now(timezone.utc)`
   - Fetch event; if `event.venue_code != venue_code`: raise `VenueCodeError`.
   - Fetch signup with `with_for_update()`; assert `signup.event_id == event_id`.
   - Compute `slot_start` from signup's slot relationship (read CONTEXT.md code_context for how slot time lives on the signup — planner: inspect `Signup` model for slot FK, then use `signup.slot.starts_at` or equivalent field).
   - If `now < slot_start - CHECK_IN_WINDOW_BEFORE` or `now > slot_start + CHECK_IN_WINDOW_AFTER`: raise `CheckInWindowError`.
   - Idempotency check as above; else `_transition(..., via="self")`.
   - Return signup.

4. `resolve_event(db, event_id, actor_id, attended_ids, no_show_ids)`:
   - Begin by fetching all signups for the event with `with_for_update()`.
   - For each id in `attended_ids`: `_transition(..., SignupStatus.attended, via="resolve_event")`.
   - For each id in `no_show_ids`: `_transition(..., SignupStatus.no_show, via="resolve_event")`.
   - All-or-nothing: the caller opens the transaction, any `InvalidTransitionError` propagates and rolls back.
   - Return list of updated signups.
</action>
<read_first>
- backend/app/models.py (after 03-01 — confirm Signup → Slot relationship field name, AuditLog field names)
- backend/app/signup_service.py (existing transition code to avoid duplication)
- .planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md
</read_first>
<acceptance_criteria>
- File `backend/app/services/check_in_service.py` exists
- Contains `with_for_update()`
- Contains `ALLOWED_TRANSITIONS`
- Contains `CHECK_IN_WINDOW_BEFORE = timedelta(minutes=15)`
- Contains `CHECK_IN_WINDOW_AFTER = timedelta(minutes=30)`
- Contains `InvalidTransitionError`, `CheckInWindowError`, `VenueCodeError`
- Contains idempotency branch: `if signup.status == SignupStatus.checked_in: return signup`
- `python -c "from backend.app.services.check_in_service import check_in_signup, self_check_in, resolve_event, ALLOWED_TRANSITIONS"` exits 0
</acceptance_criteria>
</task>

<task id="03-02-02" parallel="false">
<action>
Create `backend/tests/test_check_in_service.py` with unit tests:

1. **Happy path organizer check-in**: create confirmed signup, call `check_in_signup`, assert status=`checked_in`, `checked_in_at` set, 1 AuditLog row with `meta.via == "organizer"`.
2. **Idempotent repeat**: call `check_in_signup` twice on same signup; assert status unchanged, assert only 1 AuditLog row exists (NO second audit row).
3. **Invalid transition**: attempt `_transition` from `attended` → `checked_in`; assert `InvalidTransitionError` raised.
4. **Self check-in inside window**: set `now` to `slot_start`, correct venue code, assert success and audit `via == "self"`.
5. **Self check-in before window**: `now = slot_start - 20min` → `CheckInWindowError`.
6. **Self check-in after window**: `now = slot_start + 45min` → `CheckInWindowError`.
7. **Wrong venue code**: → `VenueCodeError`.
8. **resolve_event batch**: 3 confirmed signups; mark 2 attended, 1 no_show; assert 3 audit rows with `via == "resolve_event"` and correct final statuses.
9. **resolve_event rollback**: include one signup already in `attended` (invalid transition attended→attended is NOT in ALLOWED — assert it raises AND none of the other signups were updated because the caller's transaction rolls back).
</action>
<read_first>
- backend/app/services/check_in_service.py (after 03-02-01)
- backend/tests/conftest.py
- backend/app/models.py
</read_first>
<acceptance_criteria>
- File `backend/tests/test_check_in_service.py` exists
- Contains test for idempotent repeat check-in
- Contains `CheckInWindowError`
- Contains `VenueCodeError`
- Contains `InvalidTransitionError`
- `cd backend && pytest tests/test_check_in_service.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Service imports cleanly
- `cd backend && pytest tests/test_check_in_service.py -v` exits 0
- `cd backend && pytest -q` exits 0
</verification>
