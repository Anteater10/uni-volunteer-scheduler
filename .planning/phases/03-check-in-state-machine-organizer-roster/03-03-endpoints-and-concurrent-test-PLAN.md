---
phase: 03
plan: 03
name: Endpoints — roster, check-in, self-check-in, resolve + concurrent merge-gate test
wave: 3
depends_on: [03-02]
files_modified:
  - backend/app/routers/roster.py
  - backend/app/routers/check_in.py
  - backend/app/schemas.py
  - backend/app/main.py
  - backend/tests/test_roster_endpoints.py
  - backend/tests/test_check_in_endpoints.py
  - backend/tests/test_concurrent_check_in.py
autonomous: true
requirements:
  - GET /events/{event_id}/roster
  - POST /signups/{id}/check-in
  - POST /events/{event_id}/self-check-in
  - POST /events/{event_id}/resolve
  - MERGE GATE — concurrent check-in integration test
---

# Plan 03-03: HTTP Endpoints + Concurrent Check-In Merge-Gate Test

<objective>
Expose the phase 3 service layer via FastAPI endpoints. Ship the merge-gate
concurrent check-in integration test that proves `SELECT ... FOR UPDATE`
plus the idempotency branch results in exactly ONE audit log row when two
clients race.
</objective>

<must_haves>
- `GET /events/{event_id}/roster` — organizer-only
- `POST /signups/{id}/check-in` — organizer-only, idempotent
- `POST /events/{event_id}/self-check-in` — body `{signup_id, venue_code}`
- `POST /events/{event_id}/resolve` — organizer-only, body `{attended: [...], no_show: [...]}`, atomic
- Invalid transitions return 409 `{code: "INVALID_TRANSITION", from, to}`
- Wrong venue code returns 403 `{code: "WRONG_VENUE_CODE"}`
- Outside check-in window returns 403 `{code: "OUTSIDE_WINDOW"}`
- **MERGE GATE: concurrent check-in integration test is present and passes**
</must_haves>

<tasks>

<task id="03-03-01" parallel="false">
<action>
Create Pydantic schemas in `backend/app/schemas.py` (append):

```python
class RosterRow(BaseModel):
    signup_id: UUID
    student_name: str
    status: SignupStatus
    slot_time: datetime
    checked_in_at: datetime | None

class RosterResponse(BaseModel):
    event_id: UUID
    event_name: str
    venue_code: str | None
    total: int
    checked_in_count: int
    rows: list[RosterRow]

class SelfCheckInRequest(BaseModel):
    signup_id: UUID
    venue_code: str

class ResolveEventRequest(BaseModel):
    attended: list[UUID] = Field(default_factory=list)
    no_show: list[UUID] = Field(default_factory=list)
```
</action>
<read_first>
- backend/app/schemas.py
- backend/app/models.py
</read_first>
<acceptance_criteria>
- `grep -q 'class RosterRow' backend/app/schemas.py`
- `grep -q 'class SelfCheckInRequest' backend/app/schemas.py`
- `grep -q 'class ResolveEventRequest' backend/app/schemas.py`
- `python -c "from backend.app.schemas import RosterResponse, SelfCheckInRequest, ResolveEventRequest"` exits 0
</acceptance_criteria>
</task>

<task id="03-03-02" parallel="false">
<action>
Create `backend/app/routers/roster.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

router = APIRouter(prefix="", tags=["roster"])

@router.get("/events/{event_id}/roster", response_model=RosterResponse)
def get_roster(event_id: UUID, db: Session = Depends(get_db), user = Depends(require_organizer)):
    event = db.get(Event, event_id)
    if not event: raise HTTPException(404)
    signups = db.execute(select(Signup).where(Signup.event_id == event_id).order_by(Signup.slot_id)).scalars().all()
    rows = [RosterRow(signup_id=s.id, student_name=s.student.name, status=s.status, slot_time=s.slot.starts_at, checked_in_at=s.checked_in_at) for s in signups]
    checked = sum(1 for s in signups if s.status in (SignupStatus.checked_in, SignupStatus.attended))
    return RosterResponse(event_id=event.id, event_name=event.name, venue_code=event.venue_code, total=len(rows), checked_in_count=checked, rows=rows)
```

Adapt field names (`student.name`, `slot.starts_at`, `require_organizer`) to actual model/auth dependencies — inspect models.py and existing routers.

If `event.venue_code` is None, generate one: `f"{secrets.randbelow(10000):04d}"`, persist, commit before returning.

Register router in `backend/app/main.py`.
</action>
<read_first>
- backend/app/main.py (find auth dependency pattern)
- backend/app/routers/ (existing router for organizer-only pattern)
- backend/app/models.py
- backend/app/services/check_in_service.py
</read_first>
<acceptance_criteria>
- File `backend/app/routers/roster.py` exists
- Contains `@router.get("/events/{event_id}/roster"`
- Registered in main.py
- `curl` smoke (via TestClient) hitting `/events/{id}/roster` as organizer returns 200 with `rows` array
- Non-organizer caller gets 403
</acceptance_criteria>
</task>

<task id="03-03-03" parallel="false">
<action>
Create `backend/app/routers/check_in.py` with three endpoints:

1. `POST /signups/{signup_id}/check-in` — organizer-only. Opens a DB transaction, calls `check_in_signup(db, signup_id, actor_id=user.id, via="organizer")`, commits, returns the updated signup as a `SignupResponse`. Maps exceptions:
   - `InvalidTransitionError` → `HTTPException(409, {"code": "INVALID_TRANSITION", "from": e.from_status.value, "to": e.to_status.value})`
   - `LookupError` → 404

2. `POST /events/{event_id}/self-check-in` — NO role requirement, body `SelfCheckInRequest`. Calls `self_check_in(db, event_id, body.signup_id, body.venue_code, actor_id=body.signup_id)`. Maps:
   - `VenueCodeError` → 403 `{"code": "WRONG_VENUE_CODE"}`
   - `CheckInWindowError` → 403 `{"code": "OUTSIDE_WINDOW"}`
   - `InvalidTransitionError` → 409 as above

3. `POST /events/{event_id}/resolve` — organizer-only, body `ResolveEventRequest`. Opens transaction, calls `resolve_event(...)`, commits or rolls back on any error, returns the roster (reuse the roster builder from 03-03-02, extract as a helper).

Register router in `main.py`.
</action>
<read_first>
- backend/app/routers/roster.py (03-03-02)
- backend/app/services/check_in_service.py
- backend/app/main.py
</read_first>
<acceptance_criteria>
- File `backend/app/routers/check_in.py` exists
- Contains all three endpoint path strings
- Registered in `main.py`
- 409 responses contain `INVALID_TRANSITION`
- 403 responses contain `WRONG_VENUE_CODE` and `OUTSIDE_WINDOW`
</acceptance_criteria>
</task>

<task id="03-03-04" parallel="false">
<action>
Create `backend/tests/test_roster_endpoints.py` and `backend/tests/test_check_in_endpoints.py` using FastAPI TestClient:

`test_roster_endpoints.py`:
- Organizer fetches roster → 200, rows count matches, `checked_in_count` correct.
- Non-organizer → 403.
- Venue code auto-generated on first fetch (4 digits).
- Venue code is stable across repeated fetches.

`test_check_in_endpoints.py`:
- Organizer check-in happy path → 200, status `checked_in`.
- Repeat check-in → 200 (idempotent), still one audit row.
- Check-in of non-existent signup → 404.
- Check-in of already-cancelled signup → 409 with `INVALID_TRANSITION`.
- Self-check-in wrong venue code → 403 `WRONG_VENUE_CODE`.
- Self-check-in outside window → 403 `OUTSIDE_WINDOW` (monkeypatch `datetime.now` in service via a `now` injector OR freezegun).
- Self-check-in happy path → 200.
- Resolve endpoint: mix of confirmed + checked_in, partition into attended/no_show → 200, returns roster with final statuses.
- Resolve with invalid partition (already attended row in `no_show`) → 409, DB unchanged.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/routers/roster.py
- backend/app/routers/check_in.py
</read_first>
<acceptance_criteria>
- Both test files exist
- `cd backend && pytest tests/test_roster_endpoints.py tests/test_check_in_endpoints.py -v` exits 0
</acceptance_criteria>
</task>

<task id="03-03-05" parallel="false">
<action>
**MERGE-GATE TEST — concurrent check-in.**

Create `backend/tests/test_concurrent_check_in.py`. Requirements:

1. Uses a REAL Postgres database (not SQLite) so `SELECT ... FOR UPDATE` actually takes a row lock. If the default test fixture is SQLite, skip the test with a clear message AND add a new fixture `pg_db` that connects to a local Postgres (read `conftest.py` and the phase 0 `test_concurrent_*` files if any exist — reuse the pattern). The pytest fixture name is `pg_session`.
2. Creates one event with `venue_code="1234"`, one slot, one confirmed signup.
3. Spawns two threads via `concurrent.futures.ThreadPoolExecutor(max_workers=2)`. Thread A calls `POST /signups/{id}/check-in` (organizer path with a valid organizer token). Thread B calls `POST /events/{id}/self-check-in` with the correct venue code. Both threads use SEPARATE DB sessions (separate engine connections) so the row lock is meaningful.
4. Use a `threading.Barrier(2)` so both threads hit the endpoint at the same instant.
5. Assertions:
   - Both HTTP responses are 200.
   - Final `signup.status == "checked_in"`.
   - **EXACTLY ONE** AuditLog row exists for this signup with `action="transition"` and `meta.to == "checked_in"`.
   - `signup.checked_in_at` is set exactly once.
6. Parametrize the test to run twice in opposite arrival orders (A first, B first) and repeat each order 5 times to stress the race.

Add a marker `@pytest.mark.merge_gate` and document in the test docstring: "Merge-gate requirement per Phase 3 CONTEXT.md — concurrency open-question gate."
</action>
<read_first>
- backend/tests/conftest.py
- .planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md (Concurrency model section)
- backend/app/services/check_in_service.py
- backend/app/routers/check_in.py
</read_first>
<acceptance_criteria>
- File `backend/tests/test_concurrent_check_in.py` exists
- Contains `ThreadPoolExecutor` and `Barrier`
- Contains `@pytest.mark.merge_gate`
- Contains assertion that exactly one AuditLog row exists
- Contains docstring text `merge-gate` or `Merge-gate`
- Test runs against Postgres: `cd backend && pytest tests/test_concurrent_check_in.py -v -m merge_gate` exits 0
- Test file uses separate DB sessions per thread (grep for `sessionmaker` or `Session(bind=...)` inside the test)
</acceptance_criteria>
</task>

</tasks>

<verification>
- All new endpoint tests pass: `cd backend && pytest tests/test_roster_endpoints.py tests/test_check_in_endpoints.py tests/test_concurrent_check_in.py -v` exits 0
- Full backend suite passes: `cd backend && pytest -q` exits 0
- OpenAPI schema regenerates cleanly with the new routes
- **MERGE GATE:** concurrent check-in test passes 10 times in a row (5 per arrival order)
</verification>
