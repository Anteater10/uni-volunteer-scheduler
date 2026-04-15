---
phase: 04
plan: 02
name: Prereq check service — _check_prereqs() helper + unit tests
wave: 2
depends_on: [04-01]
files_modified:
  - backend/app/services/prereqs.py
  - backend/tests/test_prereqs_service.py
autonomous: true
requirements:
  - _check_prereqs(db, user_id, module_slug) -> list[str]
  - Only attended signups satisfy
  - Active prereq_overrides satisfy
  - next_slot lookup helper
---

# Plan 04-02: Prereq Check Service

<objective>
Implement the pure-logic prereq checker as `backend/app/services/prereqs.py` so it can
be imported by both `signups.py` router and future admin endpoints without circular
imports. Include a helper to find the next orientation slot for deep-linking.
</objective>

<must_haves>
- `check_missing_prereqs(db, user_id, module_slug) -> list[str]` — returns the list of
  missing prereq slugs for `module_slug` for the given user.
- Only signups with `status == SignupStatus.attended` on an event whose
  `module_slug == <prereq_slug>` satisfy a prereq.
- An active `PrereqOverride` (where `revoked_at IS NULL`) for `(user_id, prereq_slug)`
  also satisfies that prereq.
- Transitive prereqs are handled: if `A` requires `B` and `B` requires `C`, and user
  lacks `C`, calling `check_missing_prereqs(user, A)` returns the direct missing
  prereqs of `A` (i.e. `['B']`) — the chain is resolved at the UI level per phase
  context (no visualization of the chain, but the check function must not crash on
  chains and must not infinite-loop on cycles).
- `find_next_orientation_slot(db) -> dict | None` — returns `{event_id, slot_id, starts_at}`
  for the soonest future slot of an event whose `module_slug == "orientation"`, or
  `None` if no such slot exists.
- Unit-tested in isolation with an in-memory/SQLite fixture.
</must_haves>

<tasks>

<task id="04-02-01" parallel="false">
<action>
Create `backend/app/services/prereqs.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from backend.app.models import (
    ModuleTemplate, PrereqOverride, Event, Signup, Slot, SignupStatus,
)

def check_missing_prereqs(db: Session, user_id: UUID, module_slug: str) -> list[str]:
    """Return missing direct prereq slugs for (user_id, module_slug).

    A prereq is satisfied iff EITHER:
      - the user has a Signup with status == attended on any past event whose
        module_slug matches the prereq slug, OR
      - there is an active PrereqOverride (revoked_at IS NULL) for the user on
        that prereq slug.
    """
    template = db.get(ModuleTemplate, module_slug)
    if template is None or not template.prereq_slugs:
        return []

    missing: list[str] = []
    for prereq in template.prereq_slugs:
        # Check override first (cheaper).
        override = db.execute(
            select(PrereqOverride).where(
                PrereqOverride.user_id == user_id,
                PrereqOverride.module_slug == prereq,
                PrereqOverride.revoked_at.is_(None),
            ).limit(1)
        ).scalar_one_or_none()
        if override is not None:
            continue
        # Check attended signup on any event with matching module_slug.
        attended = db.execute(
            select(Signup.id)
            .join(Event, Event.id == Signup.event_id)
            .where(
                Signup.user_id == user_id,
                Signup.status == SignupStatus.attended,
                Event.module_slug == prereq,
            ).limit(1)
        ).scalar_one_or_none()
        if attended is None:
            missing.append(prereq)
    return missing


def find_next_orientation_slot(db: Session) -> Optional[dict]:
    """Return {event_id, slot_id, starts_at} for the soonest future orientation slot."""
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(Slot.id, Slot.event_id, Slot.starts_at)
        .join(Event, Event.id == Slot.event_id)
        .where(Event.module_slug == "orientation", Slot.starts_at > now)
        .order_by(Slot.starts_at.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"slot_id": str(row.id), "event_id": str(row.event_id), "starts_at": row.starts_at.isoformat()}
```

If `Slot` is not the correct model name in this codebase, read `backend/app/models.py`
and adjust — the schema has a slots table per phase 0.
</action>
<read_first>
- backend/app/models.py
- backend/app/routers/signups.py
- .planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md
</read_first>
<acceptance_criteria>
- File `backend/app/services/prereqs.py` exists
- Contains `def check_missing_prereqs`
- Contains `def find_next_orientation_slot`
- Contains `SignupStatus.attended`
- Contains `revoked_at.is_(None)`
- `python -c "from backend.app.services.prereqs import check_missing_prereqs, find_next_orientation_slot"` exits 0
</acceptance_criteria>
</task>

<task id="04-02-02" parallel="false">
<action>
Create `backend/tests/test_prereqs_service.py` with tests:

1. **No prereqs** — module with empty `prereq_slugs` returns `[]`.
2. **Missing single prereq** — user has no attended signup on `orientation`; calling
   `check_missing_prereqs(user, "intro-bio")` returns `["orientation"]`.
3. **Satisfied via attended** — user has a past Signup with `status=attended` on an
   Event with `module_slug="orientation"`. Returns `[]`.
4. **NOT satisfied via checked_in** — user has only `checked_in` (not `attended`).
   Returns `["orientation"]`.
5. **Satisfied via override** — create a `PrereqOverride(user, "orientation", ...)`.
   Returns `[]`.
6. **Revoked override does not satisfy** — set `revoked_at=now()`. Returns `["orientation"]`.
7. **Unknown module_slug** — returns `[]` (no crash).
8. **find_next_orientation_slot** — creates one future and one past orientation slot;
   asserts the future one is returned.
9. **find_next_orientation_slot — none** — returns `None` when no future orientation.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/services/prereqs.py (after 04-02-01)
- backend/app/models.py
</read_first>
<acceptance_criteria>
- File `backend/tests/test_prereqs_service.py` exists
- Contains `check_missing_prereqs`
- Contains `find_next_orientation_slot`
- Contains `SignupStatus.attended`
- Contains `SignupStatus.checked_in`
- Contains `revoked_at`
- `cd backend && pytest tests/test_prereqs_service.py -v` exits 0 with at least 9 passing tests
</acceptance_criteria>
</task>

</tasks>

<verification>
- Service importable: `python -c "from backend.app.services.prereqs import check_missing_prereqs, find_next_orientation_slot"` exits 0
- Unit tests pass: `cd backend && pytest tests/test_prereqs_service.py -v` exits 0
- Full backend suite still green: `cd backend && pytest -q` exits 0
</verification>
