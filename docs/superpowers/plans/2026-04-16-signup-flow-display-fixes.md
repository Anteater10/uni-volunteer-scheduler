# Signup-flow display fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the 7-hour timezone drift on slot times displayed in `/signup/manage` and `EventDetailPage`, and add a "Signups for {first} {last}" greeting on the manage/confirm page so users on shared devices know whose signup they're viewing.

**Architecture:** Backend-first. The `Z` suffix is being added by Pydantic when serializing the naive `time → datetime` combination on `PublicSlotRead.start_time` / `end_time`. Override the field serializer to emit naive ISO. For the greeting, project two volunteer-name fields onto `TokenedManageRead` and render them in the React `PageHeader`.

**Tech Stack:** FastAPI + Pydantic v2 (`@field_serializer`), pytest (backend), React + vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-04-16-signup-flow-display-fixes-design.md`

---

## File Structure

**Backend (modify):**
- `backend/app/schemas.py:526-536` — `PublicSlotRead`: add `@field_serializer` for `start_time`, `end_time` that drops the `Z`
- `backend/app/schemas.py:571-575` — `TokenedManageRead`: add `volunteer_first_name: str`, `volunteer_last_name: str`
- `backend/app/routers/public/signups.py:130-134` — populate the two new name fields from the `Volunteer` row

**Backend (create):**
- `backend/tests/test_slot_serializer_naive_time.py` — new test file, asserts `start_time`/`end_time` serialized without `Z`
- (Extend existing) `backend/tests/test_public_signups.py` — add test asserting manage response includes volunteer name fields

**Frontend (modify):**
- `frontend/src/pages/public/ManageSignupsPage.jsx:188-190` — render `Signups for {first} {last}` in `PageHeader`

**Frontend (modify tests):**
- `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` — update fixtures to include `volunteer_first_name`/`volunteer_last_name`; add a greeting-renders test

---

## Task 1: Backend test for naive-ISO slot serializer

**Files:**
- Create: `backend/tests/test_slot_serializer_naive_time.py`

- [ ] **Step 1: Write the failing test**

```python
"""Verify PublicSlotRead serializes time fields as naive ISO (no Z suffix).

Bug: SlotRead emitted "2026-04-16T09:00:00Z" — the Z lied about UTC.
Frontend then converted UTC → local, dropping 7 hours in PDT.

Fix: serializer emits "2026-04-16T09:00:00" — browsers parse as local
wall-clock time, no offset shift.
"""
from datetime import date, time
from uuid import uuid4

from app.schemas import PublicSlotRead
from app.models import SlotType


def test_public_slot_read_serializes_times_without_z():
    slot = PublicSlotRead(
        id=uuid4(),
        slot_type=SlotType.orientation,
        date=date(2026, 4, 16),
        start_time=time(9, 0),
        end_time=time(10, 0),
        location="E2E Hall Room A",
        capacity=200,
        filled=12,
        signups=[],
    )
    payload = slot.model_dump(mode="json")
    assert payload["start_time"] == "2026-04-16T09:00:00"
    assert payload["end_time"] == "2026-04-16T10:00:00"
    assert "Z" not in payload["start_time"]
    assert "Z" not in payload["end_time"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/test_slot_serializer_naive_time.py -v"
```
Expected: FAIL — payload value will be `"2026-04-16T09:00:00Z"` or similar with offset.

- [ ] **Step 3: Implement the field serializer**

Edit `backend/app/schemas.py`. At the top of the file ensure `field_serializer` is imported:

```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator
```

(Most likely already imported; only add if missing.)

Update `PublicSlotRead` (around line 526) to add a serializer:

```python
class PublicSlotRead(BaseModel):
    id: UUID
    slot_type: SlotType
    date: DateType
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    capacity: int
    filled: int  # = slot.current_count
    signups: List[SlotSignupRead] = []
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("start_time", "end_time")
    def _serialize_naive(self, value: datetime) -> str:
        # Slot times are wall-clock at the venue, not UTC. Drop any tzinfo
        # so the JSON value is "YYYY-MM-DDTHH:MM:SS" with no Z / no offset.
        # Browsers then parse as local time and skip the offset math.
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value.isoformat(timespec="seconds")
```

- [ ] **Step 4: Run test to verify it passes**

Run the same docker pytest command as Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_slot_serializer_naive_time.py
git commit -m "fix(15): serialize slot times as naive ISO (drop Z) to fix TZ drift"
```

---

## Task 2: Backend test + impl for volunteer-name in manage response

**Files:**
- Modify: `backend/app/schemas.py` (`TokenedManageRead`)
- Modify: `backend/app/routers/public/signups.py` (`manage_signups`)
- Modify: `backend/tests/test_public_signups.py`

- [ ] **Step 1: Locate an existing manage-endpoint test for patterns**

Run:
```bash
grep -n "signups/manage\|TokenedManageRead\|manage_signups" backend/tests/test_public_signups.py | head
```

Open the first matching test in that file. Note: how the test seeds a volunteer + signup + token, calls the endpoint, and asserts response shape. Reuse the same fixture pattern.

- [ ] **Step 2: Write the failing test (append to test_public_signups.py)**

Add at the end of `backend/tests/test_public_signups.py`:

```python
def test_manage_response_includes_volunteer_name(client, db_session):
    """Manage endpoint must return volunteer first/last name so the
    UI can render 'Signups for {first} {last}' on shared-device flows."""
    # Seed: create a public signup that issues a magic-link token.
    payload = {
        "event_id": _seed_event_with_slot(db_session),
        "first_name": "Hung",
        "last_name": "Khuu",
        "email": "hung@example.com",
        "phone": "+15555550100",
        "slot_ids": [_seed_slot_id(db_session)],
    }
    r = client.post("/api/v1/public/signups", json=payload)
    assert r.status_code == 201, r.text
    token = r.json()["confirm_token"]  # EXPOSE_TOKENS_FOR_TESTING=1

    r = client.get(f"/api/v1/public/signups/manage?token={token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["volunteer_first_name"] == "Hung"
    assert body["volunteer_last_name"] == "Khuu"
```

If `_seed_event_with_slot` / `_seed_slot_id` helpers don't already exist
in this file, copy the equivalent fixture-building code from the nearest
existing test in the same file (do not duplicate by extracting a helper —
inline the few lines so the test is self-contained).

- [ ] **Step 3: Run test to verify it fails**

```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/test_public_signups.py::test_manage_response_includes_volunteer_name -v"
```
Expected: FAIL — `KeyError: 'volunteer_first_name'`.

- [ ] **Step 4: Add fields to `TokenedManageRead`**

Edit `backend/app/schemas.py` around line 571:

```python
class TokenedManageRead(BaseModel):
    volunteer_id: UUID
    volunteer_first_name: str
    volunteer_last_name: str
    event_id: UUID
    signups: List[TokenedSignupRead]
```

- [ ] **Step 5: Populate the fields in the router**

Edit `backend/app/routers/public/signups.py`. After the line that
loads the `anchor` Signup (around line 90) and before the existing
`return schemas.TokenedManageRead(...)`, fetch the Volunteer:

```python
    from ...models import Volunteer  # local import keeps top tidy
    volunteer = db.get(Volunteer, token_row.volunteer_id)
    if volunteer is None:
        raise HTTPException(status_code=400, detail="token references missing volunteer")
```

Then update the `return` (around line 130) to include the new fields:

```python
    return schemas.TokenedManageRead(
        volunteer_id=token_row.volunteer_id,
        volunteer_first_name=volunteer.first_name,
        volunteer_last_name=volunteer.last_name,
        event_id=event_id,
        signups=signup_reads,
    )
```

- [ ] **Step 6: Run test to verify it passes**

Same docker pytest command as Step 3.
Expected: PASS.

- [ ] **Step 7: Run the full public_signups test file to catch regressions**

```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/test_public_signups.py -v"
```
Expected: ALL PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/public/signups.py backend/tests/test_public_signups.py
git commit -m "feat(15): include volunteer name in /signups/manage response"
```

---

## Task 3: Frontend test + impl for greeting

**Files:**
- Modify: `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` (fixtures + new test)
- Modify: `frontend/src/pages/public/ManageSignupsPage.jsx:188-190` (PageHeader title)

- [ ] **Step 1: Update fixtures to include volunteer name**

Edit `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`. Find the
`getManageSignups.mockResolvedValue({...})` calls and update the response
shape so each one returns:

```js
{
  volunteer_id: "vol-001",
  volunteer_first_name: "Hung",
  volunteer_last_name: "Khuu",
  event_id: "evt-001",
  signups: [SIGNUP_1, SIGNUP_2],
}
```

(Where the existing test already mocked the response, just add the two
new keys. Do not invent a new mock pattern.)

- [ ] **Step 2: Add the failing greeting test**

Add at the end of the existing `describe(...)` block in
`ManageSignupsPage.test.jsx`:

```js
it("renders 'Signups for {first} {last}' in the page header", async () => {
  api.public.getManageSignups.mockResolvedValue({
    volunteer_id: "vol-001",
    volunteer_first_name: "Hung",
    volunteer_last_name: "Khuu",
    event_id: "evt-001",
    signups: [SIGNUP_1],
  });

  renderWithToken("tok-abc");

  await waitFor(() => {
    expect(screen.getByText("Signups for Hung Khuu")).toBeInTheDocument();
  });
});
```

(`renderWithToken` is the helper used by other tests in the file —
reuse whatever pattern already exists. If tests use a different mount
helper, mirror that.)

- [ ] **Step 3: Run frontend tests to verify the new one fails**

```bash
cd frontend && npm run test -- --run ManageSignupsPage
```
Expected: FAIL on the new test (`Unable to find element with text 'Signups for Hung Khuu'`).

- [ ] **Step 4: Update the PageHeader to render the greeting**

Edit `frontend/src/pages/public/ManageSignupsPage.jsx`. The current
header (around line 190) is:

```jsx
<PageHeader title="Your signups" />
```

Change to interpolate the names from the query data:

```jsx
<PageHeader
  title={
    data?.volunteer_first_name
      ? `Signups for ${data.volunteer_first_name} ${data.volunteer_last_name}`
      : "Your signups"
  }
/>
```

(Fallback to "Your signups" preserves behavior if the API ever returns
without name fields — defensive against in-flight or older cached
responses.)

- [ ] **Step 5: Run frontend tests to verify all pass**

```bash
cd frontend && npm run test -- --run ManageSignupsPage
```
Expected: ALL PASS (greeting test + the existing 7 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/__tests__/ManageSignupsPage.test.jsx frontend/src/pages/public/ManageSignupsPage.jsx
git commit -m "feat(15): greet user by name on signup manage/confirm page"
```

---

## Task 4: Manual smoke test in browser + Mailpit

- [ ] **Step 1: Recreate backend so new code loads**

```bash
docker compose up -d --force-recreate backend celery_worker celery_beat
```

(Code is bind-mounted? Confirm by re-running the smoke test below. If
the container still shows old behavior, rebuild: `docker compose build
backend celery_worker celery_beat && docker compose up -d
--force-recreate backend celery_worker celery_beat`.)

- [ ] **Step 2: Sign up via UI and check email**

Open the frontend (`http://localhost:5173`), browse to an event in the
current week, sign up with first name `Hung`, last name `Khuu`, email
`hung@example.com`. Open Mailpit (`http://localhost:8025`).

Expected:
- Email arrives within 1s.
- Email body shows wall-clock times matching the slot definition (e.g.
  `09:00 AM` if the slot is at 9 AM). [unchanged from baseline]

- [ ] **Step 3: Click magic link, verify confirm + manage page**

In the email, click "Confirm my signup". Land on
`/signup/confirm?token=...`.

Expected:
- Page heading reads `Signups for Hung Khuu` (NOT `Your signups`).
- Slot row shows the SAME wall-clock times as the email (e.g. `9:00 AM
  – 10:00 AM`, NOT `2:00 AM – 3:00 AM`).

- [ ] **Step 4: Verify EventDetailPage time is consistent**

In a new tab, navigate to the same event's detail page from the public
events list (no token needed). Find the same slot.

Expected: same wall-clock time as the email and the manage page.

- [ ] **Step 5: No commit needed — manual verification only**

If anything in steps 2-4 fails, file a follow-up. Do not push the
branch until all three views agree on the time and the greeting renders.

---

## Self-review

**Spec coverage:**
- Spec Fix 1 (time bug) → Tasks 1 + 4
- Spec Fix 2 (greeting) → Tasks 2 + 3 + 4
- Deferred items → not in plan (correct)

**Placeholder scan:** none. Every step has the actual code or command.

**Type consistency:** `volunteer_first_name` / `volunteer_last_name`
identical across schema, router, frontend test fixtures, and
`ManageSignupsPage` JSX. `start_time`/`end_time` types unchanged
(`datetime`); only the JSON projection changes via `@field_serializer`.

**Frequent commits:** 3 commits planned (one per task, smoke test no
commit).
