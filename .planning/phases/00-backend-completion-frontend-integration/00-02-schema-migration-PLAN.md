---
phase: 00-backend-completion-frontend-integration
plan: 02
type: execute
wave: 1
depends_on: [01]
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/0002_phase0_schema_hardening.py
  - backend/app/routers/events.py
  - backend/app/routers/slots.py
  - backend/app/routers/signups.py
  - backend/app/celery_app.py
  - backend/app/deps.py
autonomous: true
requirements:
  - TZ-01
  - TZ-02
  - CELERY-02
  - CELERY-03
  - AUTH-02
must_haves:
  truths:
    - "Every DateTime column in models.py uses timezone=True"
    - "No occurrences of datetime.utcnow() remain in backend/app/"
    - "No occurrences of _to_naive_utc remain in backend/app/"
    - "Signup model has reminder_sent boolean column defaulting False"
    - "slots.start_time has a btree index"
    - "RefreshToken.token column stores SHA-256 hash (renamed token_hash)"
    - "Alembic upgrade + downgrade both run clean on a fresh Postgres"
  artifacts:
    - path: "backend/alembic/versions/0002_phase0_schema_hardening.py"
      provides: "Single Alembic revision for TZ + reminder_sent + slot index + refresh token hash"
      contains: "def upgrade"
    - path: "backend/app/models.py"
      provides: "Timezone-aware columns, reminder_sent, token_hash"
  key_links:
    - from: "backend/app/models.py::Signup.reminder_sent"
      to: "backend/app/celery_app.py::schedule_reminders (Plan 04 consumes)"
      via: "boolean idempotency guard"
      pattern: "reminder_sent"
    - from: "backend/app/models.py::Slot.start_time"
      to: "PostgreSQL btree index"
      via: "Alembic op.create_index"
      pattern: "create_index.*slots.*start_time"
---

<objective>
Land every schema change Phase 0 requires in a single Alembic revision so downstream plans (auth hardening, Celery reliability, refactors) never conflict on `models.py` or `alembic/versions/`. Covers: full timezone migration, `Signup.reminder_sent`, `slots.start_time` index, `RefreshToken.token` → `token_hash`.

Purpose: Consolidating schema changes into one wave eliminates merge conflicts and guarantees E2E runs against the final schema.
Output: One Alembic revision that upgrades and downgrades cleanly; models.py updated; all `datetime.utcnow()` and `_to_naive_utc` call sites removed.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/00-01-SUMMARY.md
@backend/app/models.py
@backend/app/routers/events.py
@backend/app/routers/slots.py
@backend/app/routers/signups.py
@backend/app/celery_app.py
@backend/app/deps.py
@backend/alembic/env.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update models.py — timezone-aware columns, reminder_sent, token_hash, slot index</name>
  <files>backend/app/models.py</files>
  <read_first>
    - backend/app/models.py (full file — identify every DateTime column, the RefreshToken model, the Signup model, the Slot model)
    - 00-RESEARCH.md "Timezone Migration" section and "Pitfall 3: Enum ALTER TYPE"
    - 00-CONTEXT.md "Timezone Migration" and "Celery Reliability" decision blocks
  </read_first>
  <action>
    1. At the top of `models.py`, ensure `from sqlalchemy import DateTime, Index` is imported and `from datetime import datetime, timezone` is imported.
    2. For EVERY `Column(DateTime, ...)` occurrence in the file, change to `Column(DateTime(timezone=True), ...)`. Columns to update (verify by reading — expected set): `User.created_at`, `User.updated_at`, `Event.start_time`, `Event.end_time`, `Event.created_at`, `Event.updated_at`, `Slot.start_time`, `Slot.end_time`, `Slot.created_at`, `Slot.updated_at`, `Signup.created_at`, `Signup.updated_at`, `Notification.created_at`, `Notification.sent_at`, `AuditLog.created_at`, `RefreshToken.created_at`, `RefreshToken.expires_at`, and any others discovered.
    3. Replace every `default=datetime.utcnow` with `default=lambda: datetime.now(timezone.utc)` in Column defaults.
    4. Add to the `Signup` model:
       ```python
       reminder_sent = Column(Boolean, nullable=False, default=False, server_default="false")
       ```
    5. Rename `RefreshToken.token` → `token_hash`. Update the `unique=True, index=True` constraints on the renamed column. Add a docstring comment: `# SHA-256 hex digest, never the raw token`.
    6. Add an index on `Slot.start_time`:
       ```python
       __table_args__ = (Index("ix_slots_start_time", "start_time"),)
       ```
       (merge with any existing `__table_args__`).
    7. Do NOT modify the `SignupStatus` enum — `registered` is deferred to Phase 3 per API-AUDIT.md open-question resolution.
  </action>
  <verify>
    <automated>cd backend && python -c "from app.models import User, Event, Slot, Signup, RefreshToken; from sqlalchemy import inspect; assert hasattr(Signup, 'reminder_sent'); assert hasattr(RefreshToken, 'token_hash'); assert not hasattr(RefreshToken, 'token'); print('ok')" && ! grep -n "DateTime)" backend/app/models.py | grep -v "timezone=True"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "DateTime(timezone=True)" backend/app/models.py` returns ≥ 10
    - `grep -q "DateTime)" backend/app/models.py` fails (no naive DateTime columns left — excluding comments)
    - `grep -q "reminder_sent" backend/app/models.py` succeeds
    - `grep -q "token_hash" backend/app/models.py` succeeds
    - `grep -q '"token"' backend/app/models.py | grep -i refresh` fails (old column gone from RefreshToken)
    - `grep -q "ix_slots_start_time" backend/app/models.py` succeeds
    - `grep -q "datetime.utcnow" backend/app/models.py` fails
    - `python -c "from app.models import *"` from `backend/` exits 0
  </acceptance_criteria>
  <done>models.py is timezone-clean, has reminder_sent and token_hash, and declares the slot index.</done>
</task>

<task type="auto">
  <name>Task 2: Author Alembic revision 0002_phase0_schema_hardening</name>
  <files>backend/alembic/versions/0002_phase0_schema_hardening.py</files>
  <read_first>
    - backend/alembic/versions/ (list existing revisions to determine `down_revision`)
    - backend/alembic/env.py (to confirm Base.metadata wiring)
    - 00-RESEARCH.md "Alembic + DateTime(timezone=True) migration patterns" + "Pitfall 3" (enum ALTER TYPE)
    - backend/app/models.py (just-edited file)
  </read_first>
  <action>
    Create `backend/alembic/versions/0002_phase0_schema_hardening.py` with a single revision that:
    1. Header: `revision = "0002_phase0_schema_hardening"`, `down_revision = "<most recent existing revision id>"` (read from existing files).
    2. `upgrade()`:
       - For each DateTime column identified in Task 1, run:
         ```python
         op.alter_column("users", "created_at",
             type_=sa.DateTime(timezone=True),
             postgresql_using="created_at AT TIME ZONE 'UTC'")
         ```
         Repeat for every table/column combination. Backfill assumes stored naive values were UTC.
       - `op.add_column("signups", sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.false()))`
       - `op.create_index("ix_slots_start_time", "slots", ["start_time"])`
       - Rename refresh token column and hash existing values:
         ```python
         op.alter_column("refresh_tokens", "token", new_column_name="token_hash", existing_type=sa.String(length=512))
         # Data backfill: existing raw tokens are invalid after rename — force reissue by truncating
         op.execute("DELETE FROM refresh_tokens")
         ```
         (Research confirms existing refresh tokens are low value; forcing re-login is acceptable per CONTEXT.md "auth hardening" — no user-data loss.)
    3. `downgrade()`: Reverse each operation (drop index, drop column reminder_sent, rename token_hash → token, `alter_column` back to naive using `AT TIME ZONE 'UTC'` again — not a perfect inverse but acceptable for dev rollbacks).
    4. Do NOT modify any enum types. Do NOT touch the `signups.status` column.
  </action>
  <verify>
    <automated>cd backend && alembic upgrade head 2>&1 | tee /tmp/alembic-up.log && grep -q "0002_phase0_schema_hardening" /tmp/alembic-up.log && alembic downgrade -1 2>&1 | tee /tmp/alembic-down.log && alembic upgrade head</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/alembic/versions/0002_phase0_schema_hardening.py` exists
    - `grep -q "def upgrade" backend/alembic/versions/0002_phase0_schema_hardening.py` succeeds
    - `grep -q "def downgrade" backend/alembic/versions/0002_phase0_schema_hardening.py` succeeds
    - `grep -q "create_index.*ix_slots_start_time" backend/alembic/versions/0002_phase0_schema_hardening.py` succeeds
    - `grep -q "reminder_sent" backend/alembic/versions/0002_phase0_schema_hardening.py` succeeds
    - `grep -q "token_hash" backend/alembic/versions/0002_phase0_schema_hardening.py` succeeds
    - `alembic upgrade head` exits 0 against a fresh Postgres
    - `alembic downgrade -1 && alembic upgrade head` exits 0
  </acceptance_criteria>
  <done>Single Alembic revision applies and rolls back cleanly; schema matches models.py.</done>
</task>

<task type="auto">
  <name>Task 3: Remove _to_naive_utc and datetime.utcnow from all router/celery/deps call sites</name>
  <files>backend/app/routers/events.py, backend/app/routers/slots.py, backend/app/routers/signups.py, backend/app/celery_app.py, backend/app/deps.py</files>
  <read_first>
    - backend/app/routers/events.py (grep `_to_naive_utc`, `datetime.utcnow`)
    - backend/app/routers/slots.py (same)
    - backend/app/routers/signups.py (same)
    - backend/app/celery_app.py (same; plus reminder window calculation)
    - backend/app/deps.py (same; plus token expiry calculations)
    - 00-CONTEXT.md "Timezone Migration" decision — "Delete all `_to_naive_utc()` helpers"
  </read_first>
  <action>
    1. In every file above, delete any local `def _to_naive_utc` definition.
    2. Replace every `_to_naive_utc(dt)` call with `dt.astimezone(timezone.utc)` if `dt` may be naive incoming from client JSON, or simply `dt` if already known to be aware. For incoming Pydantic fields, the field validator is responsible — Plan 05 centralizes this.
    3. Replace every `datetime.utcnow()` with `datetime.now(timezone.utc)` in these files.
    4. Ensure `from datetime import datetime, timezone` is present at the top of each file.
    5. In `celery_app.py::schedule_reminders`, ensure the 5-minute window calculation uses aware datetimes on both sides of comparisons: `now = datetime.now(timezone.utc); window_start = now + timedelta(hours=24); window_end = window_start + timedelta(minutes=5)`. Do NOT yet add the `reminder_sent` filter — Plan 04 wires that logic along with the redbeat swap.
    6. Do NOT touch other files. Do NOT add the reminder_sent guard here (Plan 04 does it).
  </action>
  <verify>
    <automated>! grep -rn "_to_naive_utc" backend/app/ && ! grep -rn "datetime.utcnow" backend/app/ && cd backend && python -c "from app.routers import events, slots, signups; from app import celery_app, deps; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "_to_naive_utc" backend/app/` returns non-zero (no matches)
    - `grep -rn "datetime.utcnow" backend/app/` returns non-zero (no matches)
    - `grep -q "datetime.now(timezone.utc)" backend/app/routers/signups.py` succeeds
    - `grep -q "datetime.now(timezone.utc)" backend/app/celery_app.py` succeeds
    - `python -c "from app.routers import events, slots, signups"` from `backend/` exits 0
    - `python -c "from app import celery_app, deps"` from `backend/` exits 0
  </acceptance_criteria>
  <done>Timezone drift eliminated from every in-scope backend file; imports still clean; Plan 04 now has a timezone-aware celery_app to build on.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Alembic migration → production DB | Data transformation; incorrect `AT TIME ZONE` assumption could shift timestamps |
| Refresh token column rename | Forces all users to re-login; no data loss but session disruption |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-05 | Tampering | Alembic TZ backfill could mis-convert if stored values were not UTC | mitigate | Research confirmed codebase uses `datetime.utcnow()` exclusively — stored values ARE naive UTC. `AT TIME ZONE 'UTC'` is correct. Document assumption in migration docstring. |
| T-00-06 | Denial of Service | Index creation on large `slots` table could lock | accept | Dev/staging only at this phase; Phase 8 deploy runbook must use `CONCURRENTLY` for prod migration — noted in migration file comment |
| T-00-07 | Elevation of Privilege | Raw refresh tokens exist in DB until migration runs | mitigate | Migration deletes all existing refresh tokens (`DELETE FROM refresh_tokens`), forcing re-login. Plan 03 wires new SHA-256 hash flow. |
| T-00-08 | Information Disclosure | Downgrade path leaves tokens deleted | accept | Downgrade is dev-only; forcing re-login is acceptable |
</threat_model>

<verification>
- `alembic upgrade head` exits 0
- `alembic downgrade -1 && alembic upgrade head` exits 0
- `grep -rn "_to_naive_utc" backend/app/` returns empty
- `grep -rn "datetime.utcnow" backend/app/` returns empty
- `python -c "from app.models import Signup; assert hasattr(Signup, 'reminder_sent')"` exits 0
</verification>

<success_criteria>
One Alembic revision consolidates TZ migration, reminder_sent column, slot index, and refresh token hash rename; all naive-datetime helpers removed from app code; models.py imports cleanly.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-02-SUMMARY.md`
</output>
