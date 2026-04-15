---
phase: 03
plan: 01
name: Schema & Migration — enum extension, venue_code, MagicLinkToken.purpose
wave: 1
depends_on: []
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/
  - backend/tests/test_models_phase3.py
autonomous: true
requirements:
  - SignupStatus enum extension (checked_in, attended, no_show)
  - Event.venue_code column
  - MagicLinkToken.purpose enum column
---

# Plan 03-01: Schema & Migration

<objective>
Extend `SignupStatus` with `checked_in`, `attended`, `no_show`. Add `Event.venue_code`
(4-digit numeric, nullable). Add `MagicLinkToken.purpose` enum column
`{email_confirm, check_in}`. Ship an Alembic migration. Existing rows grandfathered.
</objective>

<must_haves>
- Final enum: `{pending, confirmed, checked_in, attended, no_show, waitlisted, cancelled}`
- `Event.venue_code` column exists (String(4), nullable)
- `MagicLinkToken.purpose` enum column exists (default `email_confirm` for backfill)
- Migration applies cleanly with no data loss
- Existing `confirmed` signups remain `confirmed`; existing magic link tokens backfill as `email_confirm`
- Migration round-trips (upgrade → downgrade → upgrade)
</must_haves>

<tasks>

<task id="03-01-01" parallel="false">
<action>
Edit `backend/app/models.py`. Locate the `SignupStatus` enum (currently has
`pending, confirmed, waitlisted, cancelled` after Phase 2). Add three new
members so the final enum reads:

```python
class SignupStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    checked_in = "checked_in"
    attended = "attended"
    no_show = "no_show"
    waitlisted = "waitlisted"
    cancelled = "cancelled"
```

In the same file:

1. Add `venue_code = Column(String(4), nullable=True)` to the `Event` model.
2. Define a new enum `MagicLinkPurpose`:
   ```python
   class MagicLinkPurpose(str, enum.Enum):
       email_confirm = "email_confirm"
       check_in = "check_in"
   ```
3. Add `purpose = Column(Enum(MagicLinkPurpose, name="magiclinkpurpose"), nullable=False, server_default="email_confirm")` to the `MagicLinkToken` model (added in phase 2).
4. Add `checked_in_at = Column(DateTime(timezone=True), nullable=True)` to the `Signup` model — used by roster UI.

Ensure `Enum` is imported from `sqlalchemy`.
</action>
<read_first>
- backend/app/models.py
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
- .planning/phases/03-check-in-state-machine-organizer-roster/03-CONTEXT.md
</read_first>
<acceptance_criteria>
- `grep -q 'checked_in = "checked_in"' backend/app/models.py`
- `grep -q 'attended = "attended"' backend/app/models.py`
- `grep -q 'no_show = "no_show"' backend/app/models.py`
- `grep -q 'venue_code' backend/app/models.py`
- `grep -q 'class MagicLinkPurpose' backend/app/models.py`
- `grep -q 'checked_in_at' backend/app/models.py`
- `python -c "from backend.app.models import SignupStatus, MagicLinkPurpose; assert SignupStatus.checked_in.value == 'checked_in'; assert MagicLinkPurpose.check_in.value == 'check_in'"` exits 0
</acceptance_criteria>
</task>

<task id="03-01-02" parallel="false">
<action>
Generate an Alembic migration via `alembic revision -m "phase3 check-in state machine schema"`.
Fill `upgrade()`:

1. Extend the `signupstatus` Postgres enum OUTSIDE a transaction:
   ```python
   with op.get_context().autocommit_block():
       op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'checked_in'")
       op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'attended'")
       op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'no_show'")
   ```
2. Add `venue_code VARCHAR(4) NULL` to `events`.
3. Add `checked_in_at TIMESTAMPTZ NULL` to `signups`.
4. Create `magiclinkpurpose` Postgres enum `{'email_confirm','check_in'}`.
5. Add `purpose` column to `magic_link_tokens` with server default `'email_confirm'` then ALTER to `NOT NULL`.

`downgrade()`:
1. Drop `purpose` column.
2. Drop `magiclinkpurpose` enum type.
3. Drop `signups.checked_in_at`.
4. Drop `events.venue_code`.
5. Document enum value removal as unsupported (no-op comment).

Migration docstring must include: `"Extends SignupStatus for Phase 3 check-in lifecycle. Existing rows stay confirmed; existing magic link tokens backfill as email_confirm."`
</action>
<read_first>
- backend/alembic/versions/ (find latest revision for down_revision)
- backend/alembic/env.py
- backend/app/models.py (after 03-01-01)
</read_first>
<acceptance_criteria>
- New file `backend/alembic/versions/*phase3_check_in_state_machine_schema.py` exists
- File contains `ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'checked_in'`
- File contains `ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'attended'`
- File contains `ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'no_show'`
- File contains `autocommit_block`
- File contains `venue_code`
- File contains `checked_in_at`
- File contains `magiclinkpurpose`
- `cd backend && alembic upgrade head` exits 0
- `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
</acceptance_criteria>
</task>

<task id="03-01-03" parallel="false">
<action>
Create `backend/tests/test_models_phase3.py` with tests that:

1. Assert every SignupStatus member exists: `pending, confirmed, checked_in, attended, no_show, waitlisted, cancelled`.
2. Create a Signup and transition through `confirmed → checked_in`, flush, assert persisted.
3. Set `signup.checked_in_at = datetime.now(timezone.utc)`, flush, assert stored.
4. Create an Event and set `venue_code = "4271"`, flush, assert stored.
5. Create a MagicLinkToken with `purpose=MagicLinkPurpose.check_in`, flush, assert stored.
6. Assert default `purpose` on a MagicLinkToken created without explicit purpose is `email_confirm`.

Reuse existing test DB fixture from `backend/tests/conftest.py`.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/models.py
- backend/tests/test_models_magic_link.py (for fixture patterns from Phase 2)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_models_phase3.py` exists
- Contains `SignupStatus.checked_in`
- Contains `SignupStatus.attended`
- Contains `SignupStatus.no_show`
- Contains `MagicLinkPurpose.check_in`
- Contains `venue_code`
- `cd backend && pytest tests/test_models_phase3.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Models import: `python -c "from backend.app.models import SignupStatus, MagicLinkPurpose, Event, Signup, MagicLinkToken"` exits 0
- Migration applies: `cd backend && alembic upgrade head` exits 0
- Migration round-trips: `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
- New tests pass: `cd backend && pytest tests/test_models_phase3.py -v` exits 0
- Existing tests still pass: `cd backend && pytest -q` exits 0
</verification>
