# Phase 08: Schema Realignment Migration - Research

**Researched:** 2026-04-09
**Domain:** Alembic migrations, SQLAlchemy models, Postgres enum lifecycle, FK surgery
**Confidence:** HIGH (all findings sourced directly from codebase inspection)

---

## Summary

Phase 08 is a pure database and ORM layer migration. No new API endpoints, no frontend
changes. The goal is to land a new alembic revision (slug `0009_phase8_schema_realignment`)
that reshapes the schema from the v1.0 account-based model to the v1.1 email-keyed
volunteer model, and to retrofit clean `DROP TYPE` calls into every prior migration that
leaks a postgres enum on downgrade.

The codebase was inspected end-to-end. All findings below are sourced from the actual
migration files and model code — no guesswork.

**Primary recommendation:** Write one migration file (`0009_phase8_schema_realignment`)
that does all schema surgery in a single upgrade/downgrade pair, grouped into clearly
labelled sections. The enum-downgrade fixes go into the existing prior migrations
(in-place edits), not a new migration, because they fix the downgrade path of already-
shipped code. See the Enum Downgrade Checklist below for the exact files and operations.

---

## User Constraints (from ROADMAP.md and REQUIREMENTS-v1.1-accountless.md)

### Locked Decisions
- Volunteers identified by email — first signup creates `Volunteer` row, later signups attach
- One `Signup` row per slot (not per form submission)
- `Event` gets structured columns: `quarter`, `year`, `week_number` (start week), `module_slug`, `school`
- Each `Slot` has a single `capacity`; no role column on `Signup`
- Dev data in current User/Signup tables is throwaway — no backfill, safe to drop rows

### Claude's Discretion
- Migration split strategy: one file vs. small series (research recommends one file — see below)
- Exact CHECK constraint on `phone_e164`, if any (column exists; validation is Phase 09)
- ON DELETE semantics for new FKs

### Deferred Ideas (OUT OF SCOPE for Phase 08)
- Public signup API, magic-link token issuance for signup_confirm/signup_manage (Phase 09)
- Browse page, signup form, orientation modal (Phase 10)
- Manage-my-signup token-gated page (Phase 11)
- Retirement of Phase 4 prereq router and Phase 7 override UI (Phase 12)
- Playwright seed script (Phase 13)

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R08-01 | New `volunteers` table: id UUID PK, email UNIQUE NOT NULL, first_name, last_name, phone_e164, created_at, updated_at | Confirmed no existing `volunteers` table; `id` pattern is UUID(as_uuid=True) matching all other tables |
| R08-02 | `events`: add quarter enum, year int, week_number int, module_slug string (plain column, no longer FK), school string | Event model verified; existing `module_slug` column is a FK to `module_templates.slug` — must be dropped and re-added as plain String |
| R08-03 | `slots`: add `slot_type` enum (orientation\|period) | Slot model has no slot_type; existing columns: event_id, start_time, end_time, capacity, current_count |
| R08-04 | `signups`: drop FK to users, add FK to volunteers; drop unique constraint uq_signups_user_id_slot_id, add uq_signups_volunteer_id_slot_id | Unique constraint confirmed in migration b8f0c2e41a9d |
| R08-05 | `magic_link_tokens`: current schema uses signup_id FK (not user_id); add volunteer_id FK; add signup_confirm\|signup_manage values to magiclinkpurpose enum | Current MagicLinkToken has signup_id FK and email column — see Model Inventory below for exact shape |
| R08-06 | Drop `prereq_overrides` table and `module_templates.prereq_slugs` column | Both confirmed in models.py and migration 0005 |
| R08-07 | Fix enum-downgrade latent bug in all prior migrations | Audit complete — see Enum Downgrade Checklist |
| R08-08 | Update SQLAlchemy models + Pydantic schemas to match new shape | models.py is a single flat file; schemas.py is a single flat file |
| R08-09 | alembic downgrade base + upgrade head round-trips with no DuplicateObject | Verification command documented below |

---

## Standard Stack

No new libraries needed for the migration itself. One new library needed as a future
dependency that Phase 08 should add to requirements.txt even though the validation logic
lands in Phase 09:

| Library | Status | Purpose | Note |
|---------|--------|---------|------|
| alembic 1.17.2 | Already installed | Migration runner | Use existing patterns |
| sqlalchemy 2.0.44 | Already installed | ORM models | Use existing patterns |
| psycopg2-binary 2.9.11 | Already installed | Postgres driver | Use existing patterns |
| **phonenumbers** | **NOT in requirements.txt** | E.164 phone normalization | **Must add for Phase 09 prep; recommend adding in Phase 08** |

**phonenumbers is absent from requirements.txt.** [VERIFIED: grep of requirements.txt]
The `phone_e164` column lands in Phase 08 migration; the normalization logic lands in Phase
09. The planner should add `phonenumbers` to requirements.txt in Phase 08 so Phase 09 does
not have a hidden dependency gap. Pinned version recommendation: `phonenumbers>=8.13,<9`
(stable semver range). [ASSUMED — version range; verify with `pip index versions phonenumbers`
before pinning]

---

## Enum Downgrade Checklist

This is the core deliverable of the "fix latent bug" requirement. Every migration that
`CREATE TYPE`s a postgres enum in `upgrade()` must `DROP TYPE` in `downgrade()`.

Enum types created in each migration, and whether the downgrade handles them:

| Migration File | Enum Name | Created In upgrade()? | Dropped In downgrade()? | Status |
|---|---|---|---|---|
| `2465a60b9dbc_initial_schema.py` | `privacymode` | YES — via `sa.Enum(...)` in `create_table('site_settings')` | NO — `drop_table('site_settings')` drops the column but NOT the type | **LEAKS** |
| `2465a60b9dbc_initial_schema.py` | `userrole` | YES — via `sa.Enum(...)` in `create_table('users')` | NO — `drop_table('users')` drops the column but NOT the type | **LEAKS** |
| `2465a60b9dbc_initial_schema.py` | `signupstatus` | YES — via `sa.Enum(...)` in `create_table('signups')` | NO — `drop_table('signups')` drops the column but NOT the type | **LEAKS** |
| `2465a60b9dbc_initial_schema.py` | `notificationtype` | YES — via `sa.Enum(...)` in `create_table('notifications')` | NO — `drop_table('notifications')` drops the column but NOT the type | **LEAKS** |
| `0003_add_pending_status_and_magic_link_tokens.py` | `signupstatus` | ALTER TYPE ADD VALUE only — type already exists | N/A | OK (postgres cannot remove enum values anyway) |
| `0004_phase3_check_in_state_machine_schema.py` | `magiclinkpurpose` | YES — `magiclinkpurpose.create(op.get_bind(), checkfirst=True)` | YES — `sa.Enum(name="magiclinkpurpose").drop(op.get_bind(), checkfirst=True)` | **CLEAN** (this is the reference pattern to follow) |
| `0006_phase5_module_templates_csv_imports.py` | `csvimportstatus` | YES — `csvimportstatus.create(op.get_bind(), checkfirst=True)` | YES — `sa.Enum(name="csvimportstatus").drop(op.get_bind(), checkfirst=True)` | **CLEAN** |
| New `0009_phase8_schema_realignment.py` | `quarter` | YES — must add explicit create/drop | Must add | TBD |
| New `0009_phase8_schema_realignment.py` | `slottype` | YES — must add explicit create/drop | Must add | TBD |

**Summary of leaks to fix:**
- `privacymode` — confirmed leaking (Stage 0 round-trip test finding)
- `userrole` — leaks (same mechanism as privacymode)
- `signupstatus` — leaks (same mechanism)
- `notificationtype` — leaks (same mechanism)

**Fix pattern** (from 0004/0006 — the correct reference):
```python
# In downgrade() of 2465a60b9dbc_initial_schema.py — add these 4 lines BEFORE drop_table calls:
sa.Enum(name="signupstatus").drop(op.get_bind(), checkfirst=True)
sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
sa.Enum(name="notificationtype").drop(op.get_bind(), checkfirst=True)
sa.Enum(name="privacymode").drop(op.get_bind(), checkfirst=True)
```
[VERIFIED: inspected all migration files; pattern sourced from 0004 and 0006 which are correct]

**Important ordering:** `DROP TYPE` must come AFTER `DROP TABLE` for the tables using those
types. The initial schema downgrade already drops tables in the correct order; append the
`Enum.drop()` calls at the very end of the `downgrade()` function.

---

## Model Inventory (Current State vs. Required State)

### `models.py` — Current shape of affected models

**User model** (kept as-is, organizer/admin accounts survive):
- `id` UUID PK, `name`, `email`, `hashed_password`, `role` (userrole enum)
- `university_id`, `notify_email`, `created_at`, `deleted_at`
- Relationships: events, signups, notifications, refresh_tokens, audit_logs

**Event model** (needs new columns):
- CURRENT: id, owner_id (FK users.id), title, description, location, visibility,
  branding_id, start_date, end_date, max_signups_per_user, signup_open_at, signup_close_at,
  venue_code, **module_slug (FK → module_templates.slug)**, reminder_1h_enabled, created_at
- REQUIRED ADDS: quarter (enum), year (int), week_number (int), school (string)
- REQUIRED CHANGE: module_slug — drop FK constraint to module_templates, keep as plain String
- KEEP: all other columns

**Slot model** (needs slot_type column):
- CURRENT: id, event_id (FK events.id), start_time, end_time, capacity, current_count
- REQUIRED ADD: slot_type (enum: orientation|period)
- NOTE: The spec adds date, start_time, end_time, location per REQUIREMENTS-v1.1, but
  start_time and end_time already exist. The migration only needs to add `slot_type`.
  [ASSUMED: spec's "date" column is already satisfied by start_time/end_time as DateTime;
  confirm whether a separate DATE column is wanted — decision to flag in plan]

**Signup model** (needs FK surgery):
- CURRENT: id, **user_id (FK users.id NOT NULL)**, slot_id (FK slots.id), status
  (signupstatus enum), timestamp, reminder_sent, reminder_24h_sent_at, reminder_1h_sent_at,
  checked_in_at
- REQUIRED: drop user_id + its FK constraint; add volunteer_id (FK volunteers.id NOT NULL);
  drop unique constraint `uq_signups_user_id_slot_id`; add `uq_signups_volunteer_id_slot_id`
- KEEP: all other columns and the status enum with all existing values

**MagicLinkToken model** (current shape is different from what spec describes):
- CURRENT: id, token_hash, **signup_id (FK signups.id ON DELETE CASCADE)**, email,
  **purpose** (magiclinkpurpose enum: email_confirm|check_in), created_at, expires_at, consumed_at
- The spec says "drop FK to users, add FK to volunteers" — but the current model ALREADY
  has no FK to users; it has FK to signups.id. This is a mis-read in the phase scope.
- ACTUAL REQUIRED CHANGES:
  1. Add `volunteer_id` FK to volunteers table (so tokens can be looked up by volunteer)
  2. Add new values `signup_confirm` and `signup_manage` to the `magiclinkpurpose` enum
  3. The existing `signup_id` FK stays — it is still needed for the consume path
- NOTE: `email_confirm` and `check_in` enum values cannot be removed from Postgres;
  they stay in the type definition. The Phase 09 code simply won't issue new tokens of
  those old purposes.

**ModuleTemplate model** (needs column drop):
- CURRENT: slug PK, name, **prereq_slugs** (ARRAY String), default_capacity, duration_minutes,
  materials, description, metadata_, deleted_at, created_at, updated_at
- REQUIRED: drop `prereq_slugs` column

**PrereqOverride model** (entire table drops):
- CURRENT: id, user_id (FK users.id), module_slug (FK module_templates.slug), reason,
  created_by (FK users.id), created_at, revoked_at
- REQUIRED: drop entire table

---

## FK Surgery Pattern (signups.user_id → signups.volunteer_id)

[VERIFIED: Postgres documentation and Alembic op patterns confirmed via codebase inspection
of existing migrations using the same techniques]

Dropping a FK and adding a new one requires:
1. Drop the unique constraint that references the old column first (order matters)
2. Drop the old FK column
3. Create the new referenced table first (volunteers must exist before the FK)
4. Add the new FK column

In Alembic:
```python
# Step 1: Drop the unique constraint on the old column pair
op.drop_constraint("uq_signups_user_id_slot_id", "signups", type_="unique")

# Step 2: Drop the old FK column (Postgres implicitly drops the FK constraint when column drops)
op.drop_column("signups", "user_id")

# Step 3 (done earlier in same migration): create volunteers table

# Step 4: Add the new volunteer_id column with FK
op.add_column(
    "signups",
    sa.Column(
        "volunteer_id",
        postgresql.UUID(as_uuid=True),
        nullable=True,  # nullable first, then populate, then set NOT NULL
    ),
)
# Since data is throwaway: immediately set NOT NULL without a backfill step
op.alter_column("signups", "volunteer_id", nullable=False)

# Step 5: Add FK constraint explicitly
op.create_foreign_key(
    "fk_signups_volunteer_id",
    "signups", "volunteers",
    ["volunteer_id"], ["id"],
    ondelete="CASCADE",  # or RESTRICT — decision point; see note below
)

# Step 6: Add new unique constraint
op.create_unique_constraint(
    "uq_signups_volunteer_id_slot_id",
    "signups",
    ["volunteer_id", "slot_id"],
)
```

**ON DELETE semantics decision:** If a Volunteer row is deleted, what happens to their
Signups? Options:
- `CASCADE` — deletes all their signups (clean, but loses history)
- `RESTRICT` — blocks volunteer deletion if they have signups
- `SET NULL` — would require nullable volunteer_id (defeats the purpose)

Recommendation: `CASCADE` because dev data is throwaway and the app has no volunteer
deletion flow planned. [ASSUMED — confirm with Andy before locking]

**Data strategy for the drop:** Because dev data is throwaway (per locked decision),
the migration can `DELETE FROM signups` (and cascade to downstream tables) before dropping
user_id. The migration should do this explicitly and comment it.

---

## Postgres Enum Lifecycle Pattern for New Enums

Follow the pattern established in `0004_phase3_check_in_state_machine_schema.py` and
`0006_phase5_module_templates_csv_imports.py`:

```python
from sqlalchemy.dialects import postgresql

# In upgrade():
quarter_enum = postgresql.ENUM(
    "winter", "spring", "summer", "fall",
    name="quarter",
    create_type=False,
)
quarter_enum.create(op.get_bind(), checkfirst=True)

op.add_column(
    "events",
    sa.Column(
        "quarter",
        postgresql.ENUM("winter", "spring", "summer", "fall", name="quarter", create_type=False),
        nullable=True,  # nullable initially; already-existing rows would fail NOT NULL
    ),
)

# In downgrade():
op.drop_column("events", "quarter")
sa.Enum(name="quarter").drop(op.get_bind(), checkfirst=True)
```

This pattern is the correct approach — confirmed in two existing migrations.
[VERIFIED: sourced from backend/alembic/versions/0004 and 0006]

**For `magiclinkpurpose` extension** (adding signup_confirm and signup_manage):
```python
# upgrade() — must be outside transaction block
with op.get_context().autocommit_block():
    op.execute("ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_confirm'")
    op.execute("ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_manage'")

# downgrade() — cannot remove enum values in Postgres; intentionally no-op (document this)
```
[VERIFIED: existing pattern in 0003 and 0004 for signupstatus extension]

---

## prereq_overrides / prereq_slugs Blast Radius

Everything that breaks when these are dropped. The planner does NOT need to fix these in
Phase 08 — just needs to know the scope so model and schema edits are complete.

**Backend routers:**
- `backend/app/routers/admin.py` lines 1172–1255: three endpoints `GET /prereq-overrides`,
  `POST /users/{user_id}/prereq-overrides`, `DELETE /prereq-overrides/{override_id}` —
  all reference `models.PrereqOverride` and `schemas.PrereqOverrideRead/Create`
- `backend/app/routers/signups.py` lines 47, 88, 179, 185: `acknowledge_prereq_override`
  query param and `prereq_override_self` audit log action
- `backend/app/routers/users.py` lines 186–187, 221–224: reads `template.prereq_slugs`
  and queries `models.PrereqOverride`

**Backend services:**
- `backend/app/services/prereqs.py`: entire file uses `PrereqOverride` and `template.prereq_slugs`

**Backend schemas:**
- `backend/app/schemas.py` lines 408–421: `PrereqOverrideCreate`, `PrereqOverrideRead`
- `backend/app/schemas.py` lines 439, 453, 464: `prereq_slugs` fields on three Module schemas

**Backend tests (will fail after model changes):**
- `backend/tests/test_admin_prereq_overrides.py` — entire file
- `backend/tests/test_prereqs_service.py` — entire file
- `backend/tests/test_signups_prereq.py` — entire file
- `backend/tests/test_models_phase4.py` — `TestPrereqOverride` class and `prereq_slugs` tests
- `backend/tests/test_models_phase5.py` — references `prereq_slugs`
- `backend/tests/test_templates_crud.py` — references `prereq_slugs`
- `backend/tests/test_module_timeline.py` — references `prereq_slugs` and `PrereqOverride`

**Frontend:**
- `frontend/src/pages/admin/TemplatesSection.jsx` lines 70, 95, 135, 150, 243, 244, 273,
  275, 333, 334 — reads/writes `prereq_slugs`
- `frontend/src/pages/EventDetailPage.jsx` line 100 — passes `acknowledgePrereqOverride`
- `frontend/src/pages/AdminTemplatesPage.jsx` lines 14, 36 — displays `prereq_slugs`
- `frontend/src/lib/api.js` lines 281–284 — `acknowledgePrereqOverride` flag in createSignup

**Phase 08 must handle in models.py and schemas.py:**
- Remove `PrereqOverride` class from models.py
- Remove `prereq_slugs` column from `ModuleTemplate` class
- Remove `PrereqOverrideCreate`, `PrereqOverrideRead` from schemas.py
- Remove `prereq_slugs` fields from `ModuleTemplateBase`, `ModuleTemplateUpdate`, `ModuleTemplateRead`
- Phase 08 does NOT need to fix the routers, services, or frontend — those are Phase 12 scope

**Tests that will fail in Phase 08 and need to be deleted or skipped:**
The above test files reference models that no longer exist. They will fail at import time.
Phase 08 must either delete them or mark them `pytest.mark.skip` with a "retired in Phase 12"
note. Recommendation: delete them outright — they test functionality being retired.

---

## Code also referencing signup.user (relationship — breaks when user_id drops)

Beyond `user_id` column references, the `signup.user` relationship access is used in:
- `backend/app/magic_link_service.py` line 100: `signup.user.email if signup.user else None`
- `backend/app/emails.py` lines 56, 79, 102, 126, 151: `user = signup.user`
- `backend/app/celery_app.py` line 141: `user = signup.user`
- `backend/app/routers/admin.py` lines 205, 283, 369, 451, 539, 587, 652, 654, 959:
  `user = signup.user` (roster endpoints, analytics, CCPA)
- `backend/tests/test_magic_link_service.py` lines 32, 42, 50, 59, 77: `signup.user.email`

**Phase 08 scope:** Remove the `user = relationship("User", back_populates="signups")`
from the `Signup` model and add `volunteer = relationship("Volunteer", ...)`.
The code call-sites in emails.py, magic_link_service.py, celery_app.py, and admin.py
will break after this model change — this is expected and acceptable for Phase 08,
because those paths are Phase 09/12 scope. Tests that touch `signup.user` need to be
updated or deleted in Phase 08 so the test suite passes.

---

## Migration Design: One File vs. Series

**Recommendation: one migration file** (`0009_phase8_schema_realignment`).

Rationale:
- All changes are interdependent (signups.volunteer_id requires volunteers table first)
- A series would require careful ordering anyway — no simpler than one file
- The round-trip test `alembic downgrade base && alembic upgrade head` exercises the
  whole chain; one new file means only one new downgrade() to verify
- Phase 09 tests can start from a clean head without worrying about intermediate states

If the file becomes unwieldy, split into two max:
- `0009a_phase8_new_tables_and_fks` — volunteers table, events/slots columns, signups surgery
- `0009b_phase8_retire_prereqs` — drop prereq_overrides, drop module_templates.prereq_slugs

---

## Alembic Round-Trip Verification Command

The alembic commands run inside the docker network (db is not exposed to host). The
verification pattern from Stage 0 and Phase 05/06 plans is:

```bash
# Run alembic upgrade + full downgrade base + re-upgrade inside a one-off container
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" \
  uni-volunteer-scheduler-backend \
  sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head"
```

**The critical flag:** `downgrade base` (not `downgrade -1`). This exercises the ENTIRE
chain from current head all the way to the initial revision, which is the only way to
catch enum-leak bugs in the initial migration. `-1` only tests one step.

**After running:** Check stderr for any `DuplicateObject` or `already exists` errors.
A clean round-trip produces no such errors.

---

## What the Migration Must NOT Do

- Do NOT remove the `alembic/env.py` VARCHAR(128) widening for `alembic_version.version_num`.
  [VERIFIED: CLAUDE.md explicitly prohibits regression of this]
- Do NOT use short hex revision IDs. Use slug form: `0009_phase8_schema_realignment`.
  [VERIFIED: CLAUDE.md convention]
- Do NOT write `sa.Enum("val1", "val2", name="foo")` in `create_table()` without also
  calling `enum.create()` separately — that pattern causes the type to leak in downgrade.
  Use the `create_type=False` + explicit `.create()` pattern.
- Do NOT try to remove enum values from existing enums (e.g., pending from signupstatus)
  — Postgres does not support `ALTER TYPE DROP VALUE`. Leave old values in place.

---

## Common Pitfalls

### Pitfall 1: Dropping a column that has a FK constraint
**What goes wrong:** `op.drop_column("signups", "user_id")` fails if the FK constraint
still exists.
**Why:** Postgres won't drop a column that has a referenced constraint.
**How to avoid:** Drop the unique constraint first, then the FK constraint (or just drop
the column — Postgres implicitly drops FK constraints on the column being dropped, but
NOT the unique constraint). Be explicit: `op.drop_constraint` before `op.drop_column`.

### Pitfall 2: events.module_slug is currently a FK to module_templates
**What goes wrong:** After dropping `prereq_overrides` and `module_templates.prereq_slugs`,
the `events.module_slug` FK to `module_templates.slug` will still exist. The spec wants
`module_slug` on events to become a plain string column (not a FK). This requires:
1. Drop the FK constraint on `events.module_slug`
2. The column itself stays (same name, same type), just loses the FK
**How to avoid:** `op.drop_constraint("events_module_slug_fkey", "events", type_="foreignkey")`
— the exact constraint name needs to be verified against what Postgres actually named it.
Use `op.execute("SELECT conname FROM pg_constraint WHERE conrelid='events'::regclass AND contype='f'")` to confirm.

### Pitfall 3: magiclinkpurpose ALTER TYPE requires autocommit
**What goes wrong:** `ALTER TYPE ... ADD VALUE` cannot run inside a transaction.
**Why:** Postgres restriction on DDL involving enum value addition.
**How to avoid:** Use the existing pattern: `with op.get_context().autocommit_block():`.
This is already done correctly in migrations 0003 and 0004.

### Pitfall 4: signupstatus enum still needed after migration
**What goes wrong:** Assuming the signupstatus enum needs changing.
**Reality:** The status enum values (`pending`, `confirmed`, `checked_in`, `attended`,
`no_show`, `waitlisted`, `cancelled`) all survive the v1.1 pivot. No changes needed.
The check-in state machine (Phase 03) is in the "surviving" list from REQUIREMENTS-v1.1.

### Pitfall 5: Test suite will fail at model import time after PrereqOverride removal
**What goes wrong:** Tests that import `from app.models import PrereqOverride` will fail
at collection time, not at runtime, causing confusing pytest errors.
**How to avoid:** Delete the test files that test retired functionality as part of Phase 08.
Do not just skip them — deleted tests do not pollute the test collection.

---

## Architecture Patterns

### Migration File Structure

Follow the established pattern (from 0006 — the cleanest example):
```python
"""Phase 8: schema realignment — volunteers table, v1.1 column additions, prereq retirement.

Revision ID: 0009_phase8_schema_realignment
Revises: 0008_phase7_user_deleted_at
Create Date: 2026-04-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0009_phase8_schema_realignment"
down_revision: Union[str, None] = "0008_phase7_user_deleted_at"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Section 1: Create volunteers table
    # Section 2: events — add quarter/year/week_number/school, drop module_slug FK
    # Section 3: slots — add slot_type enum
    # Section 4: signups — drop user_id FK, add volunteer_id FK
    # Section 5: magic_link_tokens — add volunteer_id FK, extend magiclinkpurpose
    # Section 6: Retire prereq_overrides table
    # Section 7: Retire module_templates.prereq_slugs column
    ...

def downgrade() -> None:
    # Reverse in exact opposite order
    ...
```

### Model File Structure

`backend/app/models.py` is a single flat file. After Phase 08, add the new `Volunteer`
class near the top (after enums, before `User`), and add new enums (`Quarter`, `SlotType`).
Update the `Signup` model to replace `user_id`/`user` with `volunteer_id`/`volunteer`.

---

## Validation Architecture

Test framework: pytest 8.3.3, run via docker one-off container (see CLAUDE.md).
Quick run command:
```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R08-01 | volunteers table created with correct columns | integration | `pytest tests/test_models_phase8.py::TestVolunteer -x` | No — Wave 0 |
| R08-02 | events.quarter column queryable with WHERE clause | integration | `pytest tests/test_models_phase8.py::TestEventWeekQuery -x` | No — Wave 0 |
| R08-03 | slots.slot_type enum saves and retrieves orientation\|period | integration | `pytest tests/test_models_phase8.py::TestSlotType -x` | No — Wave 0 |
| R08-04 | signups.volunteer_id FK enforced; signups.user_id gone | integration | `pytest tests/test_models_phase8.py::TestSignupVolunteerFK -x` | No — Wave 0 |
| R08-07 | alembic downgrade base + upgrade head round-trips clean | system | shell command (see above) | N/A |
| R08-06 | prereq_overrides table and module_templates.prereq_slugs do not exist | integration | `pytest tests/test_models_phase8.py::TestRetiredTables -x` | No — Wave 0 |

### Wave 0 Gaps
- [ ] `backend/tests/test_models_phase8.py` — covers R08-01 through R08-06
- [ ] No new conftest needed — existing `tests/fixtures/` and db session setup reuse

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ON DELETE CASCADE is correct for signups.volunteer_id FK | FK Surgery Pattern | If RESTRICT is wanted, migration must be changed; CASCADE could silently delete history |
| A2 | Slot.start_time/end_time (DateTime) satisfies the spec's "date" field; no separate DATE column needed | Model Inventory | If a separate DATE column is needed, adds one more column to the migration |
| A3 | phonenumbers>=8.13,<9 is the appropriate pin | Standard Stack | Version range may have changed; verify with `pip index versions phonenumbers` |
| A4 | The FK constraint on events.module_slug is named `events_module_slug_fkey` by Postgres | Pitfall 2 | Wrong constraint name causes migration failure; must verify actual name before running |
| A5 | Deleting test files for prereq functionality (rather than skipping) is the right approach for Phase 08 | Blast Radius section | If tests should be preserved for Phase 12 reference, skip instead |

---

## Environment Availability

All execution happens inside the docker network. No new external dependencies for Phase 08.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 16 | Migration target | On docker network | 16 | — |
| uni-volunteer-scheduler-backend image | Migration runner | Built | current | Rebuild with `docker compose build` |
| Test DB (test_uvs) | pytest | Must pre-exist | — | `docker exec ... psql -c "CREATE DATABASE test_uvs;"` |

---

## Sources

### Primary (HIGH confidence — direct codebase inspection)
- `backend/alembic/versions/2465a60b9dbc_initial_schema.py` — enum leak confirmed
- `backend/alembic/versions/0004_phase3_check_in_state_machine_schema.py` — correct enum pattern
- `backend/alembic/versions/0006_phase5_module_templates_csv_imports.py` — correct enum pattern
- `backend/alembic/versions/b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py` — unique constraint name confirmed
- `backend/app/models.py` — full model inventory
- `backend/app/schemas.py` — full schema inventory
- `backend/app/magic_link_service.py` — current MagicLinkToken usage
- `backend/requirements.txt` — phonenumbers absence confirmed
- `.planning/REQUIREMENTS-v1.1-accountless.md` — locked decisions
- `.planning/ROADMAP.md` — success criteria

### Secondary (MEDIUM confidence)
- Stage 0 finding (in STATE.md): `privacymode` confirmed leaking from round-trip test

---

## Metadata

**Confidence breakdown:**
- Enum downgrade checklist: HIGH — read every migration file directly
- Model inventory: HIGH — read models.py directly
- Blast radius enumeration: HIGH — grepped every file
- FK surgery pattern: HIGH — matches Alembic and Postgres documented behavior
- phonenumbers absence: HIGH — grep of requirements.txt confirmed
- ON DELETE semantics: ASSUMED (A1) — needs Andy confirmation

**Research date:** 2026-04-09
**Valid until:** Stable (this is codebase inspection, not ecosystem research)
