---
phase: 08-schema-realignment-migration
plan: 01
subsystem: database / ORM
tags: [alembic, migration, schema, volunteers, signups, enum, prereqs-retirement]
dependency_graph:
  requires: []
  provides: [volunteers-table, event-structured-columns, slot-type-date-location, signup-volunteer-fk, magic-link-volunteer-fk, prereqs-retired]
  affects: [routers/signups, routers/admin, routers/users, services/prereqs, app/emails, app/celery_app, app/magic_link_service]
tech_stack:
  added: [phonenumbers>=8.13]
  patterns: [autocommit_block for ALTER TYPE ADD VALUE, create_type=False enum pattern, sa.Enum.drop(checkfirst=True) in downgrade]
key_files:
  created:
    - backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py
    - .planning/phases/08-schema-realignment-migration/08-verification-psql.txt
    - .planning/phases/08-schema-realignment-migration/08-schema-after.sql
  modified:
    - backend/alembic/versions/2465a60b9dbc_initial_schema.py
    - backend/app/models.py
    - backend/app/schemas.py
    - backend/app/services/prereqs.py
    - backend/requirements.txt
    - backend/tests/fixtures/factories.py
    - backend/tests/test_magic_link_service.py (5 tests skipped)
    - backend/tests/test_models_phase3.py (2 classes skipped)
    - backend/tests/test_admin.py (2 tests skipped)
    - backend/tests/test_admin_phase7.py (3 tests skipped)
    - backend/tests/test_contract.py (1 test skipped)
    - backend/tests/test_roster_endpoints.py (1 test skipped)
  deleted:
    - backend/tests/test_admin_prereq_overrides.py
    - backend/tests/test_prereqs_service.py
    - backend/tests/test_signups_prereq.py
    - backend/tests/test_models_phase4.py
    - backend/tests/test_module_timeline.py
decisions:
  - D-01: signups.volunteer_id ON DELETE RESTRICT (attendance history is source of truth)
  - D-04: dev data deleted in migration (no backfill; throwaway data)
  - D-05: prereq retirement scope = model + schema stubs + 5 test files; router/service = Phase 12
  - D-06: signup.user breakage accepted; 74 tests skip-marked for Phase 09 rewire
metrics:
  duration: ~4h
  completed: 2026-04-09
  tasks_completed: 15/15
  files_changed: 24
requirements:
  - R08-01
  - R08-02
  - R08-03
  - R08-04
  - R08-05
  - R08-06
  - R08-07
  - R08-08
  - R08-09
---

# Phase 08 Plan 01: v1.1 Schema Realignment Migration Summary

**One-liner:** Single Alembic migration 0009 lands the v1.1 volunteer-keyed schema — new `volunteers` table, event/slot structured columns, `signups.volunteer_id` FK with RESTRICT, `magic_link_tokens` volunteer extension, prereq_overrides retirement, and full enum-downgrade sweep across all migrations.

---

## What Shipped

### Enum-leak fix (2465a60b9dbc_initial_schema.py) — commit b802bdf

Added four explicit `sa.Enum(name=...).drop(op.get_bind(), checkfirst=True)` calls to the `downgrade()` function in the initial schema migration, AFTER all `drop_table()` calls:

- `signupstatus`
- `userrole`
- `notificationtype`
- `privacymode`

Without these, every `downgrade base && upgrade head` round-trip failed with `DuplicateObject: type "signupstatus" already exists`.

### New migration 0009_phase08_v1_1_schema_realignment.py — commit 01b13b9

Single migration covering all v1.1 schema surgery in 7 sections:

1. **volunteers table** — UUID PK, email UNIQUE, first_name, last_name, phone_e164 (nullable), created_at, updated_at
2. **Dev data DELETE** — DELETE FROM magic_link_tokens; DELETE FROM signups (D-04)
3. **events** — dropped FK `events_module_slug_fkey` (captured via Task 1 audit); added quarter (enum), year, week_number, school
4. **slots** — added slot_type (slottype enum, NOT NULL, server_default 'period'), date (DATE NOT NULL, CURRENT_DATE default), location (nullable)
5. **signups** — dropped uq_signups_user_id_slot_id + user_id column; added volunteer_id FK to volunteers with ON DELETE RESTRICT; new uq_signups_volunteer_id_slot_id
6. **magic_link_tokens** — added volunteer_id FK (nullable, CASCADE); extended magiclinkpurpose enum with signup_confirm + signup_manage via autocommit_block
7. **prereq_overrides** — dropped table; dropped module_templates.prereq_slugs column

`downgrade()` reverses all sections in strict reverse order with proper enum cleanup.

### models.py — commit 38d6c37

- Added `Volunteer` model with signups backref
- Added `Quarter` and `SlotType` enums
- Extended `MagicLinkPurpose` with `SIGNUP_CONFIRM` and `SIGNUP_MANAGE`
- `Signup`: `user_id` → `volunteer_id`, `user` relationship → `volunteer` relationship
- `MagicLinkToken`: added `volunteer_id` FK column and `volunteer` relationship
- `Event`: `module_slug` now plain String (ForeignKey arg removed); added quarter/year/week_number/school
- `Slot`: added slot_type/date/location
- `ModuleTemplate`: dropped `prereq_slugs` column
- `PrereqOverride` model: DELETED
- `User.signups` relationship: REMOVED

### schemas.py — commit cf1b56f

- Removed `prereq_slugs` field from `ModuleTemplateBase`, `ModuleTemplateUpdate`, `ModuleTemplateRead`
- Kept `PrereqOverrideCreate` and `PrereqOverrideRead` as stub schemas to prevent router import failure until Phase 12 removes the prereq router code (admin.py references `schemas.PrereqOverrideRead` at module level)

### Test cleanup — commits d0acf80, 3dc823a

**Deleted 5 files:**
- `test_admin_prereq_overrides.py`
- `test_prereqs_service.py`
- `test_signups_prereq.py`
- `test_models_phase4.py`
- `test_module_timeline.py`

**Surgical edits:**
- `test_models_phase5.py`: removed `prereq_slugs` from expected column set
- `test_templates_crud.py`: removed `prereq_slugs` kwarg from ModuleTemplate creation

**Skip-marked 74 tests** across 14 files (see Phase 09 follow-up section below).

**SlotFactory fix:** Added `slot_type = SlotType.PERIOD` to `SlotFactory` in `fixtures/factories.py` to satisfy the new NOT NULL constraint.

### Dependency and service fixes — commit 2f17d6a

- Added `phonenumbers>=8.13,<9` to `requirements.txt` (phonenumbers 8.13.55 confirmed importable)
- Added `try/except` guard around `PrereqOverride` import in `services/prereqs.py` to prevent conftest import failure; Phase 12 will remove the entire service

---

## Verification Gate Results

### Gate 1: Forward upgrade (Task 8) — PASS

```
docker run ... alembic upgrade head
INFO: Running upgrade 0008_phase7_user_deleted_at -> 0009_phase08_v1_1_schema_realignment
```

```
SELECT version_num FROM alembic_version;
         version_num
--------------------------------------
 0009_phase08_v1_1_schema_realignment
```

### Gate 2: Round-trip migration (Task 9) — PASS

```
alembic upgrade head && alembic downgrade base && alembic upgrade head
```

All 10 migrations ran without `DuplicateObject` or `already exists` errors. Full command output confirmed PASS.

### Gate 3: psql shape inspection (Task 10) — PASS

See `08-verification-psql.txt` for full output. Key assertions confirmed:

- `volunteers`: id (uuid PK, gen_random_uuid()), email (varchar(255) NOT NULL), first_name, last_name, phone_e164 (nullable), created_at, updated_at; UNIQUE CONSTRAINT uq_volunteers_email
- `events`: quarter (quarter enum), year, week_number, module_slug (plain varchar, NO FK to module_templates), school — all present; `events_module_slug_fkey` ABSENT from FK section
- `slots`: slot_type (slottype NOT NULL, default 'period'::slottype), date (date NOT NULL, default CURRENT_DATE), location (nullable); start_time/end_time still present
- `signups`: volunteer_id (uuid NOT NULL) with FK `fk_signups_volunteer_id -> volunteers(id) ON DELETE RESTRICT`; unique constraint `uq_signups_volunteer_id_slot_id`; no user_id column
- `magic_link_tokens`: volunteer_id (uuid nullable) FK to volunteers(id) ON DELETE CASCADE; existing signup_id FK preserved
- `magiclinkpurpose` enum: email_confirm, check_in, signup_confirm, signup_manage
- `quarter` enum: winter, spring, summer, fall
- `slottype` enum: orientation, period
- `module_templates`: NO prereq_slugs column
- `prereq_overrides`: "Did not find any relation named 'prereq_overrides'"

### pg_dump snapshot (Task 11) — CAPTURED

File: `08-schema-after.sql` — full schema-only dump of `uni_volunteer` after migration.

### Gate 4: pytest baseline (Task 12) — PASS

```
pytest -q --no-cov
76 passed, 74 skipped in 9.79s
```

**Before Phase 08:** 185 passed (v1.0 baseline)
**After Phase 08:** 76 passed, 74 skipped, 0 failed

**Delta:** -109 tests running (5 files deleted, 74 skip-marked due to signup.user_id removal)

### alembic check (Task 13) — PARTIAL (pre-existing drift)

`alembic check` exits non-zero due to drift that is **pre-existing from prior phases** (not introduced by Phase 08):

- `csv_imports.created_at/updated_at` nullable mismatch (pre-existing)
- `magic_link_tokens.token_hash/email` TEXT vs String type (pre-existing)
- Various unique constraint vs index style differences in portal_events, refresh_tokens, magic_link_tokens (pre-existing)

**New drift introduced by Phase 08:** The `volunteers` table has both a non-unique `ix_volunteers_email` index AND a separate `uq_volunteers_email` unique constraint (migration style), while the model uses `unique=True, index=True` which SQLAlchemy represents as a single unique index. Functionally equivalent — uniqueness is enforced either way.

**Decision:** Accept this drift as a known issue. Fixing `alembic check` across all migrations is a separate cleanup task outside Phase 08 scope.

---

## Deviations from Plan

### 1. [Rule 2 - Missing Critical Functionality] schemas.py PrereqOverride stubs kept

**Found during:** Task 5 / Task 12 (pytest run)

**Issue:** Plan's D-05 said to delete PrereqOverride schemas from schemas.py. But admin.py (Phase 12 scope, cannot touch) references `schemas.PrereqOverrideRead` at module level — deleting the schema caused an `AttributeError` at import time, preventing conftest from loading, which caused the entire test suite to fail at collection.

**Fix:** Kept `PrereqOverrideCreate` and `PrereqOverrideRead` as stub schemas. The fields are still correct (unchanged from original); only the "live" usage via Module templates was removed.

**Files modified:** `backend/app/schemas.py`

**Commit:** cf1b56f

### 2. [Rule 1 - Bug Fix] services/prereqs.py PrereqOverride import guard

**Found during:** Task 12 (pytest run)

**Issue:** `services/prereqs.py` imports `PrereqOverride` from models. After Phase 08 removes the class, this caused `ImportError` at `conftest.py` load time (import chain: conftest → app.main → routers/users.py → services/prereqs.py → PrereqOverride). The entire test suite was uncollectable.

**Fix:** Added try/except import guard in `services/prereqs.py`:
```python
try:
    from app.models import PrereqOverride
except ImportError:
    PrereqOverride = None
```

**Files modified:** `backend/app/services/prereqs.py`

**Commit:** 2f17d6a

### 3. [Rule 2 - Missing] SlotFactory slot_type field

**Found during:** Task 12 (pytest run)

**Issue:** `SlotFactory` did not include `slot_type`, causing `IntegrityError: null value in column "slot_type"` for every test that creates a Slot via the factory. The new `slot_type NOT NULL` column has no server_default in the model (removed to avoid SQLAlchemy create_all enum cast issue).

**Fix:** Added `slot_type = SlotType.PERIOD` to SlotFactory.

**Files modified:** `backend/tests/fixtures/factories.py`

**Commit:** d0acf80

### 4. [Rule 3 - Blocking] SlotType server_default removed from model

**Found during:** Task 12 (pytest run)

**Issue:** Model had `server_default="period"` then `server_default=text("'period'::slottype")` on the slot_type column. Both caused `DataError: invalid input value for enum slottype` when conftest ran `Base.metadata.create_all()` on a fresh test_uvs database — Postgres rejected the DEFAULT value as invalid during CREATE TABLE.

**Fix:** Removed `server_default` from the model's `slot_type` column definition. The migration still has `server_default="period"` (correct for ALTER TABLE ADD COLUMN). The factory fix (deviation 3) handles the test path.

**Files modified:** `backend/app/models.py`

**Commit:** 38d6c37 (included in same models commit)

### 5. alembic check not fully clean

`alembic check` exits non-zero due to pre-existing drift from prior phases plus the volunteers unique constraint style difference. This is not a Phase 08 regression — the drift existed before and is a known issue with the project's migration/model sync approach. Documented above.

---

## Flagged for Phase 09 Planner — Tests to Re-wire

All 74 skipped tests are due to `Signup.user_id` removal. Each carries `reason="Phase 08: Signup.user_id removed; Phase 09 will rewire"`.

### File-level skips (pytestmark):

| File | Count | What it covers |
|------|-------|----------------|
| `test_signups.py` | 8 | Signup router — POST/cancel capacity/waitlist behavior |
| `test_check_in_endpoints.py` | 9 | Check-in HTTP endpoints — organizer/self check-in |
| `test_check_in_service.py` | 8 | Check-in state machine service layer |
| `test_concurrent_check_in.py` | 10 | Concurrency gate for double check-in |
| `test_models_magic_link.py` | 5 | MagicLinkToken creation + cascade delete via Signup |
| `test_notifications_phase6.py` | 6 | Reminder pipeline idempotency |
| `test_celery_reminders.py` | 4 | Celery reminder task window + idempotency |
| `test_magic_link_router.py` | 6 | Magic link router — consume/resend endpoints |

### Individual test skips:

| File | Test | What it covers |
|------|------|----------------|
| `test_magic_link_service.py` | `test_issue_token_returns_raw_stores_hash` | issue_token() returns raw and stores hash |
| `test_magic_link_service.py` | `test_consume_token_ok_flips_to_confirmed` | consume_token() confirms signup |
| `test_magic_link_service.py` | `test_consume_token_used_on_second_call` | consume_token() idempotency |
| `test_magic_link_service.py` | `test_consume_token_expired` | expired token returns expired result |
| `test_magic_link_service.py` | `test_consume_token_cancelled_signup` | cancelled signup returns not_found |
| `test_models_phase3.py::TestSignupCheckedInTransition` | both | Signup checked_in status transition + checked_in_at persistence |
| `test_models_phase3.py::TestMagicLinkTokenPurpose` | both | MagicLinkToken purpose enum values via Signup |
| `test_admin.py` | `test_admin_delete_user` | Admin delete user endpoint |
| `test_admin.py` | `test_admin_cancel_signup_promotes_waitlist` | Admin cancel uses promote_waitlist_fifo |
| `test_admin_phase7.py` | `test_analytics_volunteer_hours_shape` | Analytics volunteer hours endpoint |
| `test_admin_phase7.py` | `test_ccpa_export_returns_user_data` | CCPA export endpoint shape |
| `test_admin_phase7.py` | `test_ccpa_delete_preserves_signups` | CCPA delete anonymizes but keeps signups |
| `test_contract.py` | `test_createSignup_trailing_slash` | POST /signups/ trailing slash is 2xx |
| `test_roster_endpoints.py` | `test_organizer_fetches_roster` | Roster endpoint returns signup rows |

### What Phase 09 needs to fix in each:

1. All tests using `signup.user.email` → replace with `signup.volunteer.email` (or equivalent)
2. All tests using `SignupFactory(user=..., user_id=...)` → update factory to use `volunteer=..., volunteer_id=...` (requires creating `Volunteer` rows instead of `User` rows)
3. `magic_link_service.issue_token()` call signature may need updating once Phase 09 rewires the service
4. Admin router endpoints that reference `signup.user` need router-level rewire

---

## Flagged for Phase 12 Planner — Runtime Breakage Sites

These files IMPORT or REFERENCE `signup.user` / `user_id` or `PrereqOverride` and will fail at RUNTIME (not collection time). The app will NOT boot cleanly after Phase 08.

### signup.user / Signup.user_id references:

| File | Lines | Description |
|------|-------|-------------|
| `backend/app/magic_link_service.py` | ~100 | Accesses `signup.user.email` for email lookup |
| `backend/app/emails.py` | ~56, 79, 102, 126, 151 | `signup.user.email` / `signup.user.name` in email builders |
| `backend/app/celery_app.py` | ~141 | `signup.user` in reminder task |
| `backend/app/routers/admin.py` | ~205, 283, 369, 451, 539, 587, 652, 654, 959 | Various admin endpoints accessing signup.user |

### PrereqOverride / prereq_slugs references (Phase 12):

| File | Description |
|------|-------------|
| `backend/app/routers/admin.py` lines 1172-1255 | `@router.get("/prereq-overrides")` etc. — all will fail because table is gone |
| `backend/app/routers/signups.py` lines 47, 88, 179, 185 | Prereq check calls into `services.prereqs` |
| `backend/app/routers/users.py` lines 186-187, 221-224 | Prereq service calls |
| `backend/app/services/prereqs.py` (whole file) | Entire file references dropped table/model |
| `frontend/src/pages/admin/TemplatesSection.jsx` | prereq_slugs UI |
| `frontend/src/pages/EventDetailPage.jsx` | prereq UI |
| `frontend/src/pages/AdminTemplatesPage.jsx` | prereq UI |
| `frontend/src/lib/api.js` lines 281-284 | prereq API calls |

**The app will NOT boot after Phase 08 until Phase 09 (signup.user sites) and Phase 12 (prereq sites) land. This is expected per D-05 and D-06.**

---

## Commits

| Commit | Description |
|--------|-------------|
| b802bdf | fix(alembic): drop privacymode/userrole/signupstatus/notificationtype on initial downgrade |
| 01b13b9 | feat(08): alembic migration 0009 — v1.1 schema realignment |
| 38d6c37 | feat(08): models.py — Volunteer, Quarter, SlotType; rewire Signup/MagicLinkToken; retire PrereqOverride |
| cf1b56f | feat(08): schemas.py — stub PrereqOverride schemas for router compat; drop prereq_slugs |
| d0acf80 | chore(08): delete retired prereq-override test files; surgical prereq_slugs removal |
| 3dc823a | chore(08): skip signup.user tests pending Phase 09 rewire |
| 2f17d6a | chore(08): add phonenumbers>=8.13 for Phase 09; guard prereqs.py import |
| 95df720 | docs(08): psql shape inspection + pg_dump schema snapshot |

## Self-Check

- [x] 0009 migration file exists: `backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py`
- [x] models.py has Volunteer class
- [x] models.py has no PrereqOverride class
- [x] Gate 1 PASS: alembic_version = 0009_phase08_v1_1_schema_realignment
- [x] Gate 2 PASS: round-trip zero DuplicateObject errors
- [x] Gate 3 PASS: all psql shape assertions confirmed
- [x] Gate 4 PASS: 76 passed, 74 skipped, 0 failed
- [x] 8 commits on branch referencing Phase 08
