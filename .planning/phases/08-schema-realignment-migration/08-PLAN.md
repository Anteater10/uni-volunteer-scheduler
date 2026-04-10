---
phase: 08-schema-realignment-migration
plan: 01
type: execute
wave: 1
status: ready
created: 2026-04-09
depends_on: []
files_modified:
  - backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py
  - backend/alembic/versions/2465a60b9dbc_initial_schema.py
  - backend/app/models.py
  - backend/app/schemas.py
  - backend/requirements.txt
  - backend/tests/test_admin_prereq_overrides.py
  - backend/tests/test_prereqs_service.py
  - backend/tests/test_signups_prereq.py
  - backend/tests/test_models_phase4.py
  - backend/tests/test_module_timeline.py
autonomous: true
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

must_haves:
  truths:
    - "Fresh `alembic upgrade head` lands the head revision at 0009_phase08_v1_1_schema_realignment"
    - "`alembic downgrade base && alembic upgrade head` round-trips with zero DuplicateObject errors"
    - "The `volunteers` table exists with id/email/first_name/last_name/phone_e164/created_at/updated_at"
    - "`signups.volunteer_id` FK exists with ON DELETE RESTRICT and `signups.user_id` no longer exists"
    - "`events` has quarter/year/week_number/module_slug/school columns and no FK from module_slug to module_templates"
    - "`slots` has slot_type/date/location columns"
    - "`magic_link_tokens` has volunteer_id column and magiclinkpurpose enum includes signup_confirm and signup_manage"
    - "`prereq_overrides` table and `module_templates.prereq_slugs` column no longer exist"
    - "`pytest -q` passes at the new baseline (prereq_override + signup.user tests deleted)"
  artifacts:
    - path: backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py
      provides: "Single migration covering all v1.1 schema surgery"
      contains: "revision: str = \"0009_phase08_v1_1_schema_realignment\""
    - path: backend/app/models.py
      provides: "Volunteer model, Quarter + SlotType enums, updated Signup/MagicLinkToken/Event/Slot/ModuleTemplate"
      contains: "class Volunteer"
    - path: backend/requirements.txt
      provides: "phonenumbers dependency for Phase 09"
      contains: "phonenumbers"
  key_links:
    - from: "backend/app/models.py Signup.volunteer_id"
      to: "volunteers.id"
      via: "ForeignKey ondelete=RESTRICT"
      pattern: "volunteer_id.*ForeignKey.*volunteers\\.id.*RESTRICT"
    - from: "backend/app/models.py MagicLinkToken"
      to: "MagicLinkPurpose.SIGNUP_CONFIRM / SIGNUP_MANAGE"
      via: "Python enum extension"
      pattern: "SIGNUP_CONFIRM|SIGNUP_MANAGE"
    - from: "alembic migration 0009 upgrade()"
      to: "ALTER TYPE magiclinkpurpose ADD VALUE"
      via: "autocommit_block or transactional_ddl=False"
      pattern: "autocommit_block|transactional_ddl"
---

<objective>
Land the v1.1 schema in a single new Alembic migration plus in-place enum-downgrade fixes to prior migrations, update SQLAlchemy models and Pydantic schemas to match, add the `phonenumbers` dependency for Phase 09, and delete retired prereq-override tests so the suite collects cleanly.

Purpose: Phase 08 is the structural foundation for the v1.1 account-less pivot. Every subsequent phase (09 public API, 10 browse/form, 11 manage-link, 12 retirement, 13 E2E) assumes the new shape exists and the enum round-trip bug is fixed.

Output: One new alembic revision file, edited prior migration, updated models/schemas, deleted retired tests, phonenumbers pin, and a verification report (clean round-trip, pytest green at new baseline, manual `\d` inspection).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS-v1.1-accountless.md
@.planning/phases/08-schema-realignment-migration/08-RESEARCH.md
@CLAUDE.md

@backend/app/models.py
@backend/app/schemas.py
@backend/alembic/versions/2465a60b9dbc_initial_schema.py
@backend/alembic/versions/0004_phase3_check_in_state_machine_schema.py
@backend/alembic/versions/0006_phase5_module_templates_csv_imports.py
@backend/alembic/versions/0008_phase7_user_deleted_at.py
@backend/requirements.txt

<interfaces>
<!-- Key reference patterns extracted from the codebase for executor use. -->
<!-- No exploration needed — use these verbatim where applicable. -->

Correct enum lifecycle pattern (from 0004 and 0006 — the reference migrations):
```python
from sqlalchemy.dialects import postgresql

# upgrade()
my_enum = postgresql.ENUM("val_a", "val_b", name="myenum", create_type=False)
my_enum.create(op.get_bind(), checkfirst=True)

op.add_column(
    "some_table",
    sa.Column(
        "my_col",
        postgresql.ENUM("val_a", "val_b", name="myenum", create_type=False),
        nullable=False,
        server_default="val_a",
    ),
)

# downgrade()
op.drop_column("some_table", "my_col")
sa.Enum(name="myenum").drop(op.get_bind(), checkfirst=True)
```

Signups unique constraint name (from migration b8f0c2e41a9d):
  `uq_signups_user_id_slot_id`  → replace with `uq_signups_volunteer_id_slot_id`

Down revision to target:
  `down_revision: Union[str, None] = "0008_phase7_user_deleted_at"`

Enums leaking in initial migration (from RESEARCH §Enum Downgrade Checklist):
  `privacymode`, `userrole`, `signupstatus`, `notificationtype`
  — all created implicitly via `sa.Enum(...)` inside `create_table()`,
  none dropped on downgrade. Fix: append four `sa.Enum(name=...).drop(...)`
  calls to the very end of `downgrade()` in 2465a60b9dbc_initial_schema.py,
  AFTER the drop_table calls.

MagicLinkPurpose current Python enum (from models.py) values to preserve:
  `email_confirm`, `check_in`  (these stay — Postgres can't remove enum values)
  Phase 08 ADDS: `signup_confirm`, `signup_manage`

ALTER TYPE ADD VALUE must run outside a transaction — use:
```python
with op.get_context().autocommit_block():
    op.execute("ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_confirm'")
    op.execute("ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_manage'")
```
Downgrade of ADD VALUE is a no-op (Postgres has no DROP VALUE) — document in a comment.
</interfaces>
</context>

<locked_decisions>
These decisions came from Andy and are NON-NEGOTIABLE. Do not second-guess.

1. **D-01** `signups.volunteer_id` ON DELETE = **RESTRICT** (not CASCADE).
   Rationale: attendance history is the source of truth for future prereq / orientation checks.
   Admin "delete volunteer" must fail if signups exist — forces cancel-then-delete workflow.
   Note: RESEARCH.md §FK Surgery recommended CASCADE. Andy overrode. Use RESTRICT.

2. **D-02** `slots` gets **both** new columns: `date DATE NOT NULL` AND `location VARCHAR(255)`.
   Literal v1.1 spec match. Existing `start_time` / `end_time` DateTime columns stay — Phase 3
   organizer roster still uses them.
   Note: RESEARCH.md §Model Inventory A2 assumed the DATE column wasn't needed. Andy overrode. Add both.
   NOT NULL on `date` is satisfied via server_default of `CURRENT_DATE` at migration time (dev data
   is throwaway; seed data in Phase 13 will populate properly).

3. **D-03** `magic_link_tokens` changes: ADD a new `volunteer_id` UUID FK column (nullable, FK to
   volunteers.id, ON DELETE CASCADE is fine here since tokens are ephemeral). The existing
   `signup_id` FK stays. EXTEND the existing `magiclinkpurpose` enum with `signup_confirm` and
   `signup_manage` values. Old values `email_confirm` and `check_in` stay (Postgres cannot remove
   enum values; Phase 09 simply stops issuing them).

4. **D-04** Dev data is throwaway — NO backfill. The migration may drop/rebuild rows in affected
   tables. No data-migration step; NOT NULL columns use server_defaults only during the migration.

5. **D-05** `prereq_overrides` retirement scope for Phase 08 = model class + schema classes +
   `prereq_slugs` field on template schemas + the 5 affected test files. Router / service /
   frontend cleanup is Phase 12 scope. Do NOT touch `routers/admin.py`, `routers/signups.py`,
   `routers/users.py`, `services/prereqs.py`, or any frontend file in this phase.

6. **D-06** `signup.user` relationship breakage is expected and accepted in Phase 08. The model
   gets a `volunteer` relationship instead. Code call-sites in `emails.py`, `magic_link_service.py`,
   `celery_app.py`, `admin.py` will break after this phase — Phase 09/12 will fix them. Any test
   file that touches `signup.user` becomes invalid here; the PLAN's final task lists them so the
   Phase 09 planner picks them up.

7. **D-07** The existing FK `events.module_slug` → `module_templates.slug` is **dropped**. The
   column stays as a plain String. Module templates will be referenced by the import flow at the
   app layer only. The exact FK constraint name must be confirmed at runtime (see Task 1).

8. **D-08** Revision ID uses slug form: `0009_phase08_v1_1_schema_realignment`.
   `down_revision = "0008_phase7_user_deleted_at"`.
</locked_decisions>

<threat_model>
## Trust Boundaries

Phase 08 is a schema-only migration. No new trust boundaries are introduced. No new API
endpoints, no new external input, no new authn/authz surfaces.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-01 | Information Disclosure | `volunteers.phone_e164` column (new PII) | accept | Stored inside Postgres on private docker network; covered by existing DB-at-rest posture. No new exposure vector added in Phase 08. Normalization lands in Phase 09. |
| T-08-02 | Tampering | Migration correctness (wrong constraint drop could orphan data) | mitigate | Round-trip `downgrade base && upgrade head` against scratch db before committing. Dev data is throwaway (D-04), so blast radius is zero. |
| T-08-03 | Denial of Service | Enum leak causes every future round-trip to fail | mitigate | Explicit `sa.Enum(name=...).drop(...)` calls in downgrade of 2465a60b9dbc AND in the new 0009 downgrade. Verified via round-trip test. |

**Summary:** No new authn/authz surface; no new external input; phone_e164 is the only new
sensitive field and it's covered by existing DB-at-rest controls. No additional mitigations
required beyond what the validation gates already enforce.
</threat_model>

<validation>
## Validation Strategy (Nyquist Dimension 8)

Four layers catch different classes of bug:

1. **Round-trip migration test** — structural correctness of upgrade/downgrade symmetry.
   Runs the full chain from base to head and back, catching any enum leak or orphaned
   constraint. This is the gate that proves the Phase 08 enum sweep worked.

2. **Pytest at new baseline** — no-regression for surviving code. Expected to be LOWER than
   the 185 v1.0 baseline because we're deleting the 5 prereq-override test files and because
   tests that touch `signup.user` will break (they're flagged for Phase 09). Record the new
   baseline number in SUMMARY.md.

3. **Manual `psql \d` inspection** — shape inspection after a fresh upgrade. Confirms
   columns, types, FKs, and constraints land exactly as intended. Catches subtle issues
   autogen sanity misses (e.g., default values, nullability on FK columns).

4. **`pg_dump --schema-only` before/after diff** — complete schema state capture, rolled
   into the verification report in SUMMARY.md.

## Requirements → Test Map

| Req ID | Behavior | Gate |
|--------|----------|------|
| R08-01 | volunteers table exists with correct shape | Task 14 psql `\d volunteers` |
| R08-02 | events has quarter/year/week_number/module_slug/school; module_slug FK dropped | Task 14 psql `\d events` |
| R08-03 | slots has slot_type/date/location | Task 14 psql `\d slots` |
| R08-04 | signups.volunteer_id FK with RESTRICT; user_id gone | Task 14 psql `\d signups` |
| R08-05 | magic_link_tokens.volunteer_id exists; enum has signup_confirm + signup_manage | Task 14 psql `\d magic_link_tokens` + `\dT+ magiclinkpurpose` |
| R08-06 | prereq_overrides dropped; module_templates.prereq_slugs dropped | Task 14 psql `\d prereq_overrides` fails; `\d module_templates` has no prereq_slugs |
| R08-07 | Round-trip clean | Task 13 round-trip command |
| R08-08 | Models + schemas match migration | Task 15 `alembic check` |
| R08-09 | pytest baseline green | Task 15 pytest |
</validation>

<tasks>

<task type="auto">
  <name>Task 1: Audit — capture the exact FK constraint name on events.module_slug</name>
  <files>
    (no file written; record the output inline in the migration task's comment block)
  </files>
  <action>
    Per D-07 and RESEARCH Pitfall 2, the actual Postgres-assigned FK constraint name on
    `events.module_slug → module_templates.slug` must be confirmed at runtime before writing
    the `op.drop_constraint(...)` call. Do NOT guess.

    Run this command against the live dev db (inside the docker network):

    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d events"
    ```

    Alternative (more targeted):
    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c \
      "SELECT conname FROM pg_constraint WHERE conrelid='events'::regclass AND contype='f';"
    ```

    Find the line for the FK that references `module_templates(slug)`. Record the exact
    constraint name (likely something like `events_module_slug_fkey` but MUST be verified).
    Paste the captured name into a Python comment at the top of Task 3's migration file so
    future readers can trace where it came from. Example comment:

        # FK constraint name captured 2026-04-09 via `\d events`:
        #   events_module_slug_fkey  (references module_templates.slug)

    If the dev db is not running, `docker compose up -d db` first.
  </action>
  <verify>
    <automated>docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "SELECT conname FROM pg_constraint WHERE conrelid='events'::regclass AND contype='f';" | grep -i module_slug</automated>
  </verify>
  <done>The exact FK constraint name is captured and will be hard-coded into Task 3's migration file (no op.execute lookup at migration runtime).</done>
</task>

<task type="auto">
  <name>Task 2: Enum-leak sweep — fix downgrade() in 2465a60b9dbc_initial_schema.py</name>
  <files>backend/alembic/versions/2465a60b9dbc_initial_schema.py</files>
  <action>
    Per RESEARCH §Enum Downgrade Checklist, the initial schema migration leaks four enum types
    on downgrade: `privacymode`, `userrole`, `signupstatus`, `notificationtype`. Each is created
    implicitly via `sa.Enum(...)` inside `create_table()`, and `drop_table()` only drops the
    column, not the type.

    Fix: at the **very end** of the existing `downgrade()` function (AFTER all `op.drop_table(...)`
    calls — ordering matters; the types cannot be dropped while columns still reference them),
    append:

    ```python
    # Phase 08 fix: explicitly drop enum types that create_table() created implicitly.
    # Without these, downgrade→upgrade round-trips fail with DuplicateObject.
    sa.Enum(name="signupstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="privacymode").drop(op.get_bind(), checkfirst=True)
    ```

    Do NOT touch `upgrade()` — it's shipped and working. Do NOT touch the enum definitions
    themselves. The only edit is the four new `.drop()` lines at the end of `downgrade()`.

    Before editing, Read the file once to confirm the exact current shape of `downgrade()` and
    find the insertion point (last line of the function body, after the last drop_table).

    RESEARCH §Enum Downgrade Checklist also scanned 0003, 0004, 0005, 0006, 0007, 0008 and
    confirmed those migrations are clean (0004 and 0006 are the reference correct pattern).
    Only 2465a60b9dbc needs editing. If during the Task 13 round-trip test new enum-leak errors
    surface from migrations not in the research checklist, loop back and fix them — but start
    from this single file.
  </action>
  <verify>
    <automated>python3 -c "import re,pathlib; t=pathlib.Path('backend/alembic/versions/2465a60b9dbc_initial_schema.py').read_text(); dn=re.search(r'def downgrade\(\).*?(?=\ndef |\Z)', t, re.S).group(); drops=set(re.findall(r'sa\.Enum\(name=\"(\w+)\"\)\.drop', dn)); need={'signupstatus','userrole','notificationtype','privacymode'}; assert need <= drops, f'missing: {need-drops}'; print('ok')"</automated>
  </verify>
  <done>`downgrade()` in 2465a60b9dbc_initial_schema.py ends with four explicit `sa.Enum(name=...).drop(op.get_bind(), checkfirst=True)` calls covering signupstatus, userrole, notificationtype, privacymode. The verify command parses only the downgrade() body and asserts all four drop names are present, so it cannot pass on a stale upgrade()-only match.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Write new alembic migration 0009_phase08_v1_1_schema_realignment.py</name>
  <files>backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py</files>
  <action>
    Create a NEW alembic migration file using the slug-form naming per CLAUDE.md conventions.
    Revision header:

    ```python
    """Phase 08 v1.1: schema realignment — volunteers, event/slot columns, signup FK rewire,
    magic-link extensions, prereq retirement.

    Revision ID: 0009_phase08_v1_1_schema_realignment
    Revises: 0008_phase7_user_deleted_at
    Create Date: 2026-04-09
    """
    from typing import Sequence, Union
    from alembic import op
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    revision: str = "0009_phase08_v1_1_schema_realignment"
    down_revision: Union[str, None] = "0008_phase7_user_deleted_at"
    branch_labels = None
    depends_on = None
    ```

    **Transaction handling for ALTER TYPE ADD VALUE:** Postgres requires `ALTER TYPE ... ADD VALUE`
    to run outside a transaction. Use `with op.get_context().autocommit_block():` around those
    specific statements (pattern already used in 0003 and 0004 — see interfaces block). Do NOT
    disable transactional_ddl at file level — the rest of the migration benefits from the
    transaction.

    Structure `upgrade()` in clearly labelled sections (match RESEARCH §Architecture Patterns):

    **Section 1 — Create `volunteers` table (R08-01):**
    ```python
    op.create_table(
        "volunteers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_volunteers_email"),
    )
    op.create_index("ix_volunteers_email", "volunteers", ["email"])
    ```

    **Section 2 — Drop dev data that will be orphaned by FK rewire (D-04):**
    ```python
    # Dev data is throwaway per locked decision D-04. Clear signups + magic_link_tokens
    # so the FK rewire and NOT NULL columns don't trip on pre-existing rows.
    op.execute("DELETE FROM magic_link_tokens")
    op.execute("DELETE FROM signups")
    ```

    **Section 3 — events: new columns + drop module_slug FK (R08-02, D-07):**
    Create the `quarter` enum using the explicit `create_type=False` + `.create()` pattern:
    ```python
    quarter_enum = postgresql.ENUM(
        "winter", "spring", "summer", "fall",
        name="quarter",
        create_type=False,
    )
    quarter_enum.create(op.get_bind(), checkfirst=True)

    # Drop the existing FK from events.module_slug -> module_templates.slug.
    # Constraint name captured via Task 1 audit: <PASTE EXACT NAME FROM TASK 1 HERE>
    op.drop_constraint("<exact-fk-name-from-task-1>", "events", type_="foreignkey")

    # Add new structured columns.
    op.add_column(
        "events",
        sa.Column(
            "quarter",
            postgresql.ENUM("winter", "spring", "summer", "fall",
                            name="quarter", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("events", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("week_number", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("school", sa.String(length=255), nullable=True))
    # events.module_slug column stays — only the FK constraint was dropped.
    ```
    Columns stay nullable in the migration because dev data has no sensible default; Phase 13
    seed data will populate them. Phase 09 will treat them as required at the app layer.

    **Section 4 — slots: new columns (R08-03, D-02):**
    ```python
    slot_type_enum = postgresql.ENUM(
        "orientation", "period",
        name="slottype",
        create_type=False,
    )
    slot_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "slots",
        sa.Column(
            "slot_type",
            postgresql.ENUM("orientation", "period", name="slottype", create_type=False),
            nullable=False,
            server_default="period",  # harmless default; seed data overrides
        ),
    )
    op.add_column(
        "slots",
        sa.Column(
            "date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),  # per D-02/D-04 dev data is throwaway
        ),
    )
    op.add_column("slots", sa.Column("location", sa.String(length=255), nullable=True))
    ```
    The `start_time` and `end_time` DateTime columns stay — Phase 3 organizer roster uses them.

    **Section 5 — signups: drop user_id FK, add volunteer_id FK with RESTRICT (R08-04, D-01):**
    ```python
    # Drop the old unique constraint that references user_id.
    op.drop_constraint("uq_signups_user_id_slot_id", "signups", type_="unique")
    # Drop the FK column (Postgres drops the FK constraint implicitly with the column).
    op.drop_column("signups", "user_id")

    # Add new FK to volunteers. RESTRICT per locked decision D-01 — attendance history
    # is the source of truth; forces cancel-then-delete workflow for volunteers.
    op.add_column(
        "signups",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_signups_volunteer_id",
        "signups", "volunteers",
        ["volunteer_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_signups_volunteer_id_slot_id",
        "signups",
        ["volunteer_id", "slot_id"],
    )
    ```

    **Section 6 — magic_link_tokens: add volunteer_id FK + extend purpose enum (R08-05, D-03):**
    ```python
    op.add_column(
        "magic_link_tokens",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_magic_link_tokens_volunteer_id",
        "magic_link_tokens", "volunteers",
        ["volunteer_id"], ["id"],
        ondelete="CASCADE",  # tokens are ephemeral; cascade is fine here
    )

    # Extend magiclinkpurpose enum. ALTER TYPE ADD VALUE cannot run inside a transaction,
    # so use an autocommit_block. Postgres cannot remove enum values, so the downgrade of
    # this step is intentionally a no-op (documented in downgrade() below).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_confirm'"
        )
        op.execute(
            "ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_manage'"
        )
    ```

    **Section 7 — Retire prereq_overrides (R08-06, D-05):**
    ```python
    op.drop_table("prereq_overrides")
    op.drop_column("module_templates", "prereq_slugs")
    ```

    **`downgrade()` — full reverse order with enum cleanup (no leaks):**
    ```python
    def downgrade() -> None:
        # Section 7 reverse
        op.add_column(
            "module_templates",
            sa.Column("prereq_slugs", postgresql.ARRAY(sa.String()), nullable=True),
        )
        op.create_table(
            "prereq_overrides",
            # ... full original shape from migration 0005 — copy exact column list
        )

        # Section 6 reverse
        # NOTE: Postgres has no DROP VALUE. signup_confirm/signup_manage remain in the
        # magiclinkpurpose type after downgrade. This is a known Postgres limitation, not a bug.
        op.drop_constraint("fk_magic_link_tokens_volunteer_id", "magic_link_tokens",
                           type_="foreignkey")
        op.drop_column("magic_link_tokens", "volunteer_id")

        # Section 5 reverse
        op.drop_constraint("uq_signups_volunteer_id_slot_id", "signups", type_="unique")
        op.drop_constraint("fk_signups_volunteer_id", "signups", type_="foreignkey")
        op.drop_column("signups", "volunteer_id")
        # ASSUMPTION: dev data is throwaway (D-04). Any signup rows that were
        # created via the volunteer-keyed schema after upgrade have no user_id
        # to fall back on, so we wipe the table before re-adding the NOT NULL
        # user_id column. This is safe per locked decision D-04 and matches the
        # upgrade()'s own DELETE FROM signups in section 2.
        op.execute("DELETE FROM signups")
        op.add_column(
            "signups",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        )
        # Re-add the original FK + unique constraint
        op.create_foreign_key(
            "signups_user_id_fkey", "signups", "users",
            ["user_id"], ["id"], ondelete="CASCADE",
        )
        op.create_unique_constraint(
            "uq_signups_user_id_slot_id", "signups", ["user_id", "slot_id"],
        )

        # Section 4 reverse
        op.drop_column("slots", "location")
        op.drop_column("slots", "date")
        op.drop_column("slots", "slot_type")
        sa.Enum(name="slottype").drop(op.get_bind(), checkfirst=True)

        # Section 3 reverse
        op.drop_column("events", "school")
        op.drop_column("events", "week_number")
        op.drop_column("events", "year")
        op.drop_column("events", "quarter")
        sa.Enum(name="quarter").drop(op.get_bind(), checkfirst=True)
        # Recreate the FK on events.module_slug -> module_templates.slug
        op.create_foreign_key(
            "<exact-fk-name-from-task-1>", "events", "module_templates",
            ["module_slug"], ["slug"],
        )

        # Section 1 reverse (volunteers table last because signups FK'd into it)
        op.drop_index("ix_volunteers_email", table_name="volunteers")
        op.drop_table("volunteers")
    ```

    **Copy the full prereq_overrides column list from migration 0005** (read it first; don't
    guess column shapes). Match every column name, type, nullable, and FK exactly so the
    downgrade round-trips.

    **Hard rules:**
    - Every `CREATE TYPE` in upgrade has a matching `.drop(... checkfirst=True)` in downgrade.
    - Reverse order in downgrade is strict — drop children before parents.
    - The `<exact-fk-name-from-task-1>` placeholder MUST be replaced with the name captured in Task 1.
    - Do NOT include a data-migration step — D-04 says dev data is throwaway.
  </action>
  <verify>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app uni-volunteer-scheduler-backend sh -c "python -c 'import ast; ast.parse(open(\"alembic/versions/0009_phase08_v1_1_schema_realignment.py\").read())'"</automated>
  </verify>
  <done>New migration file parses cleanly; revision id is `0009_phase08_v1_1_schema_realignment`; down_revision is `0008_phase7_user_deleted_at`; the Task 1 FK constraint name is hard-coded (no placeholders left).</done>
</task>

<task type="auto">
  <name>Task 4: Update models.py — add Volunteer, Quarter, SlotType; update Event, Slot, Signup, MagicLinkToken, ModuleTemplate; delete PrereqOverride</name>
  <files>backend/app/models.py</files>
  <action>
    `backend/app/models.py` is a single flat file (confirmed in RESEARCH §Model Inventory).
    All edits land here in one pass:

    1. **Add new Python enums** near the top, alongside existing enums (UserRole, SignupStatus,
       etc.):
       ```python
       class Quarter(str, enum.Enum):
           WINTER = "winter"
           SPRING = "spring"
           SUMMER = "summer"
           FALL = "fall"

       class SlotType(str, enum.Enum):
           ORIENTATION = "orientation"
           PERIOD = "period"
       ```

    2. **Extend MagicLinkPurpose Python enum** (D-03) — add two values, keep existing:
       ```python
       class MagicLinkPurpose(str, enum.Enum):
           EMAIL_CONFIRM = "email_confirm"   # legacy, kept for Postgres compatibility
           CHECK_IN = "check_in"             # legacy
           SIGNUP_CONFIRM = "signup_confirm"  # NEW Phase 08
           SIGNUP_MANAGE = "signup_manage"    # NEW Phase 08
       ```

    3. **Add `Volunteer` model** (place after enums, before User — matches RESEARCH recommendation):
       ```python
       class Volunteer(Base):
           __tablename__ = "volunteers"

           id = Column(UUID(as_uuid=True), primary_key=True,
                       server_default=text("gen_random_uuid()"))
           email = Column(String(255), nullable=False, unique=True, index=True)
           first_name = Column(String(100), nullable=False)
           last_name = Column(String(100), nullable=False)
           phone_e164 = Column(String(20), nullable=True)
           created_at = Column(DateTime(timezone=True),
                               server_default=func.now(), nullable=False)
           updated_at = Column(DateTime(timezone=True),
                               server_default=func.now(), nullable=False,
                               onupdate=func.now())

           signups = relationship("Signup", back_populates="volunteer")
       ```

    4. **Update `Event` model** — add new columns:
       ```python
       quarter = Column(SqlEnum(Quarter, name="quarter"), nullable=True)
       year = Column(Integer, nullable=True)
       week_number = Column(Integer, nullable=True)
       school = Column(String(255), nullable=True)
       # module_slug column stays as String — just remove the ForeignKey(...) arg if present
       ```
       Inspect the existing `module_slug` definition. Per D-07 and RESEARCH, drop the
       `ForeignKey("module_templates.slug")` from the Column(...) call. The column itself stays.
       The `module_template` relationship (if any) should also be removed.

    5. **Update `Slot` model** — add `slot_type`, `date`, `location`:
       ```python
       slot_type = Column(SqlEnum(SlotType, name="slottype"), nullable=False,
                          server_default="period")
       date = Column(Date, nullable=False, server_default=text("CURRENT_DATE"))
       location = Column(String(255), nullable=True)
       ```
       Keep existing `start_time`, `end_time`, `capacity`, `current_count`, `event_id`.

    6. **Update `Signup` model** (D-06):
       - DELETE: `user_id = Column(... ForeignKey("users.id") ...)`
       - DELETE: `user = relationship("User", back_populates="signups")`
       - ADD: `volunteer_id = Column(UUID(as_uuid=True), ForeignKey("volunteers.id", ondelete="RESTRICT"), nullable=False)`
       - ADD: `volunteer = relationship("Volunteer", back_populates="signups")`
       - Update `__table_args__` unique constraint: `UniqueConstraint("volunteer_id", "slot_id", name="uq_signups_volunteer_id_slot_id")`
       - KEEP everything else: slot_id, status, timestamp, reminder fields, checked_in_at

    7. **Update `User` model** — remove the `signups` relationship that back_populates to Signup.user.
       Per RESEARCH §Model Inventory, User.signups relationship exists and must be removed
       because Signup no longer has a `user` attribute. Grep for `relationship("Signup"` inside
       the User class and delete that line.

    8. **Update `MagicLinkToken` model** (D-03):
       - ADD: `volunteer_id = Column(UUID(as_uuid=True), ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=True)`
       - ADD: `volunteer = relationship("Volunteer")`
       - KEEP: existing `signup_id`, `email`, `purpose`, `token_hash`, `created_at`, `expires_at`, `consumed_at`
       - The `purpose` column keeps its existing SqlEnum type annotation; the Python enum now
         has the new values so SQLAlchemy will accept them.

    9. **Update `ModuleTemplate` model** (D-05):
       - DELETE: `prereq_slugs = Column(ARRAY(String), ...)`

    10. **Delete `PrereqOverride` model entirely** (D-05). Remove the full class definition.
        Also remove any relationships back-pointing to it from User and ModuleTemplate (e.g.
        `prereq_overrides = relationship("PrereqOverride", ...)`).

    11. **Update any `__init__.py` exports** if models.py is re-exported anywhere. If
        `backend/app/models/__init__.py` exists, remove PrereqOverride from its exports and
        add Volunteer. If models is a flat file (per RESEARCH), skip this step.

    Read models.py first (in its entirety) to understand the current shape before editing.
    Make all edits in a single file write.
  </action>
  <verify>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app uni-volunteer-scheduler-backend sh -c "python -c 'from app import models; assert hasattr(models, \"Volunteer\"); assert not hasattr(models, \"PrereqOverride\"); assert models.MagicLinkPurpose.SIGNUP_CONFIRM; assert models.MagicLinkPurpose.SIGNUP_MANAGE; assert models.Quarter.WINTER; assert models.SlotType.ORIENTATION'"</automated>
  </verify>
  <done>models.py imports cleanly in a one-off container, Volunteer exists, PrereqOverride gone, new enums present, Signup has volunteer relationship instead of user, ModuleTemplate has no prereq_slugs.</done>
</task>

<task type="auto">
  <name>Task 5: Update schemas.py — delete prereq_override schemas, drop prereq_slugs from template schemas</name>
  <files>backend/app/schemas.py</files>
  <action>
    Per D-05 and RESEARCH §Blast Radius, edit `backend/app/schemas.py`:

    1. **Delete Pydantic classes** (around lines 408–421 per RESEARCH):
       - `PrereqOverrideCreate`
       - `PrereqOverrideRead`
       (Any other PrereqOverride-named schema classes — grep for `PrereqOverride` inside
       schemas.py and delete the full class definitions.)

    2. **Remove `prereq_slugs` field** from these three template schemas (around lines 439, 453, 464):
       - `ModuleTemplateBase`
       - `ModuleTemplateUpdate`
       - `ModuleTemplateRead`
       Remove the line `prereq_slugs: list[str] | None = None` (or whatever the exact shape is)
       from each class body.

    3. **Scan for any other references** to PrereqOverride or prereq_slugs inside schemas.py
       with grep-in-editor. Delete anything that no longer has a corresponding model field.

    **Do NOT touch** any file under `routers/`, `services/`, or `frontend/` — those are Phase 12
    scope per D-05. The router/service files will break import at runtime after this change;
    that's expected and Phase 09/12 will fix them.

    Read schemas.py first to confirm exact class names and line numbers before editing.
  </action>
  <verify>
    <automated>grep -c "PrereqOverride\|prereq_slugs" backend/app/schemas.py || true</automated>
  </verify>
  <done>schemas.py contains zero references to PrereqOverride or prereq_slugs. Module template schemas still load correctly (verified in Task 15 alembic check).</done>
</task>

<task type="auto">
  <name>Task 6: Delete retired prereq-override test files</name>
  <files>
    backend/tests/test_admin_prereq_overrides.py,
    backend/tests/test_prereqs_service.py,
    backend/tests/test_signups_prereq.py,
    backend/tests/test_models_phase4.py,
    backend/tests/test_module_timeline.py
  </files>
  <action>
    Per D-05 and RESEARCH §prereq_overrides Blast Radius, delete these 5 test files. They
    reference `PrereqOverride`, `prereq_slugs`, or the retired prereq service, and will fail
    at import/collection time once models.py and schemas.py land (Tasks 4-5).

    Delete using the appropriate filesystem tool (not git rm — gsd-tools commit step handles
    staging). Files to delete:
    1. `backend/tests/test_admin_prereq_overrides.py`  — entire file
    2. `backend/tests/test_prereqs_service.py`         — entire file
    3. `backend/tests/test_signups_prereq.py`          — entire file
    4. `backend/tests/test_models_phase4.py`           — entire file (TestPrereqOverride class + prereq_slugs tests dominate; RESEARCH flags it for full deletion)
    5. `backend/tests/test_module_timeline.py`         — entire file (references prereq_slugs AND PrereqOverride per RESEARCH)

    NOTE: RESEARCH also lists `test_models_phase5.py` and `test_templates_crud.py` as touching
    `prereq_slugs`. Andy's locked decision D-05 names 5 test files, so only those 5 are deleted
    here. For `test_models_phase5.py` and `test_templates_crud.py`, instead of deleting them:
    grep the files and either (a) remove only the prereq_slugs assertions if they're isolated
    lines, or (b) if the entire test function is about prereq_slugs, delete just that function.
    Do NOT delete the whole file.

    After the surgical edits to test_models_phase5.py and test_templates_crud.py, run:
    ```bash
    grep -n "prereq_slugs\|PrereqOverride" backend/tests/test_models_phase5.py backend/tests/test_templates_crud.py
    ```
    Expect zero matches. If matches remain, remove them.

    **Do NOT touch** `test_magic_link_service.py` or any other file that references
    `signup.user` — those are flagged for Phase 09 (see Task 16 below).
  </action>
  <verify>
    <automated>test ! -f backend/tests/test_admin_prereq_overrides.py && test ! -f backend/tests/test_prereqs_service.py && test ! -f backend/tests/test_signups_prereq.py && test ! -f backend/tests/test_models_phase4.py && test ! -f backend/tests/test_module_timeline.py && echo OK</automated>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest --collect-only backend/tests/test_models_phase5.py backend/tests/test_templates_crud.py -q" </automated>
  </verify>
  <done>All 5 named test files deleted. `test_models_phase5.py` and `test_templates_crud.py` no longer reference prereq_slugs or PrereqOverride AND still collect cleanly under pytest (no SyntaxError, no ImportError, no orphaned-comma fallout from the surgical edits).</done>
</task>

<task type="auto">
  <name>Task 7: Add phonenumbers to backend/requirements.txt</name>
  <files>backend/requirements.txt</files>
  <action>
    Per RESEARCH §Standard Stack, add `phonenumbers` to `backend/requirements.txt`. The column
    lands in Phase 08 migration (`volunteers.phone_e164`); the normalization logic lands in
    Phase 09. Adding the dependency now prevents a hidden dependency gap when Phase 09 imports it.

    Add one line (RESEARCH recommends `phonenumbers>=8.13,<9` as a stable semver range):

    ```
    phonenumbers>=8.13,<9
    ```

    Place it alphabetically (after any `passlib`, `psycopg2-binary` and before `pydantic` —
    depends on current alpha ordering in the file).

    After adding, rebuild the backend image so subsequent pytest and migration runs pick up
    the new dependency:
    ```bash
    docker compose build backend
    ```
    (The migrate/celery_worker/celery_beat services reuse the same image.)
  </action>
  <verify>
    <automated>grep -q "^phonenumbers" backend/requirements.txt && docker run --rm uni-volunteer-scheduler-backend python -c "import phonenumbers; print(phonenumbers.__version__)"</automated>
  </verify>
  <done>phonenumbers pinned in requirements.txt; backend image rebuilt; `python -c "import phonenumbers"` works inside the container.</done>
</task>

<task type="auto">
  <name>Task 8: Run the new migration forward on a fresh db (gate 1 — forward upgrade)</name>
  <files>(no file written; verification only)</files>
  <action>
    **Gate 1 of 4: forward upgrade on a fresh db.**

    Per RESEARCH §Validation and the locked verification strategy, tear down the dev db volume
    and bring it up clean, then run the full upgrade:

    ```bash
    docker compose down
    docker volume rm uni-volunteer-scheduler_pgdata 2>/dev/null || true
    docker compose up -d db
    # wait ~3s for postgres to be ready
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE uni_volunteer;"
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"
    docker compose run --rm migrate
    ```

    Then confirm the head revision:
    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer \
      -c "SELECT version_num FROM alembic_version;"
    ```

    Expected output: `0009_phase08_v1_1_schema_realignment`

    If the migration fails:
    - Read the error carefully. The most likely failures are:
      (a) Wrong FK constraint name in Task 3 (go back to Task 1 and re-capture).
      (b) Column order issue (e.g., adding volunteer_id NOT NULL before creating volunteers table).
      (c) Enum type already exists because a prior run partially applied — drop the volume and retry.
    - Fix the migration file, re-run `docker compose run --rm migrate`.

    Do NOT proceed to Task 9 until Gate 1 is green.
  </action>
  <verify>
    <automated>docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "SELECT version_num FROM alembic_version;" | grep "0009_phase08_v1_1_schema_realignment"</automated>
  </verify>
  <done>`alembic_version.version_num` = `0009_phase08_v1_1_schema_realignment` in the fresh `uni_volunteer` db.</done>
</task>

<task type="auto">
  <name>Task 9: Round-trip migration test (gate 2 — downgrade base + upgrade head)</name>
  <files>(no file written; verification only)</files>
  <action>
    **Gate 2 of 4: round-trip against a scratch db.** This is the gate that catches the enum-leak
    fixes from Task 2.

    Use a dedicated scratch database so the dev data in `uni_volunteer` isn't disturbed:

    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres \
      -c "DROP DATABASE IF EXISTS migration_test;"
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres \
      -c "CREATE DATABASE migration_test;"

    docker run --rm \
      --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/migration_test" \
      uni-volunteer-scheduler-backend \
      sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head"
    ```

    **Pass criteria:** the command exits 0, AND stderr contains zero `DuplicateObject` or
    `already exists` errors. Pipe stderr to grep to verify:
    ```bash
    # (re-run with stderr capture if first run was clean)
    ... 2>&1 | grep -Ei "DuplicateObject|already exists" && echo "FAIL" || echo "PASS"
    ```

    If the round-trip fails with a DuplicateObject on an enum type:
    - The enum is leaking in some migration's downgrade.
    - Identify which enum (error message names it) and which migration created it (grep the
      migrations for `CREATE TYPE <enum_name>` or `sa.Enum(...name="<enum_name>")`).
    - Add the corresponding `sa.Enum(name="<enum_name>").drop(op.get_bind(), checkfirst=True)`
      to that migration's downgrade(), at the end, after the drop_table calls.
    - Commit the fix as a separate small commit (one enum per commit is ideal but grouping
      fixes in the same migration file into one commit is also fine).
    - Re-run this task.

    **Expected enums covered by Task 2:** privacymode, userrole, signupstatus, notificationtype
    (all from 2465a60b9dbc). If the round-trip surfaces ANY other enum, fix it now — Phase 08
    is the "fix enum downgrades across all migrations" phase per ROADMAP.

    Do NOT proceed to Task 10 until Gate 2 is green.
  </action>
  <verify>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/migration_test" uni-volunteer-scheduler-backend sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head" 2>&1 | (! grep -Ei "DuplicateObject|already exists")</automated>
  </verify>
  <done>Round-trip completes with zero DuplicateObject errors; head revision after the round-trip is `0009_phase08_v1_1_schema_realignment`.</done>
</task>

<task type="auto">
  <name>Task 10: Manual psql shape inspection (gate 3 — \d on every affected table)</name>
  <files>.planning/phases/08-schema-realignment-migration/08-verification-psql.txt</files>
  <action>
    **Gate 3 of 4: shape inspection.** Capture the output of `\d` on every affected table so
    the SUMMARY.md can reference it and any future regression can diff against it.

    Run these commands in sequence against the fresh `uni_volunteer` db from Task 8, piping
    all output into a single verification file:

    ```bash
    {
      echo "=== \\d volunteers ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d volunteers"
      echo
      echo "=== \\d events ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d events"
      echo
      echo "=== \\d slots ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d slots"
      echo
      echo "=== \\d signups ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d signups"
      echo
      echo "=== \\d magic_link_tokens ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d magic_link_tokens"
      echo
      echo "=== \\dT+ magiclinkpurpose ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\dT+ magiclinkpurpose"
      echo
      echo "=== \\dT+ quarter ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\dT+ quarter"
      echo
      echo "=== \\dT+ slottype ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\dT+ slottype"
      echo
      echo "=== \\d module_templates ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d module_templates"
      echo
      echo "=== \\d prereq_overrides (should fail) ==="
      docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d prereq_overrides" 2>&1 || true
    } > .planning/phases/08-schema-realignment-migration/08-verification-psql.txt
    ```

    Then read the file and confirm each of these shape assertions (eyeball + document any
    surprises in the SUMMARY):

    - `volunteers` has: id (uuid PK), email (varchar(255) NOT NULL UNIQUE), first_name,
      last_name, phone_e164 (nullable), created_at, updated_at; UNIQUE constraint on email.
    - `events` has: quarter (quarter enum), year, week_number, module_slug (plain varchar,
      NO "Foreign-key constraints" section mentioning module_templates), school.
    - `slots` has: slot_type (slottype enum NOT NULL), date (date NOT NULL), location (nullable).
      start_time, end_time, capacity still present.
    - `signups` has: volunteer_id (uuid NOT NULL) with FK to `volunteers(id) ON DELETE RESTRICT`
      and no `user_id` column. Unique constraint `uq_signups_volunteer_id_slot_id`.
    - `magic_link_tokens` has: volunteer_id (uuid nullable) FK to `volunteers(id) ON DELETE CASCADE`,
      plus the existing signup_id FK still there.
    - `magiclinkpurpose` enum values: `email_confirm`, `check_in`, `signup_confirm`, `signup_manage`.
    - `quarter` enum values: `winter`, `spring`, `summer`, `fall`.
    - `slottype` enum values: `orientation`, `period`.
    - `module_templates` has no `prereq_slugs` column.
    - `\d prereq_overrides` fails with "Did not find any relation named 'prereq_overrides'".

    If ANY assertion fails, stop and fix the migration before proceeding.
  </action>
  <verify>
    <automated>grep -q "volunteer_id" .planning/phases/08-schema-realignment-migration/08-verification-psql.txt && grep -q "uq_signups_volunteer_id_slot_id" .planning/phases/08-schema-realignment-migration/08-verification-psql.txt && grep -q "signup_confirm" .planning/phases/08-schema-realignment-migration/08-verification-psql.txt && grep -q "signup_manage" .planning/phases/08-schema-realignment-migration/08-verification-psql.txt && ! grep -q "prereq_slugs" .planning/phases/08-schema-realignment-migration/08-verification-psql.txt</automated>
  </verify>
  <done>Verification file exists, all shape assertions pass, file will be referenced from SUMMARY.md.</done>
</task>

<task type="auto">
  <name>Task 11: pg_dump schema-only snapshot for SUMMARY reference</name>
  <files>.planning/phases/08-schema-realignment-migration/08-schema-after.sql</files>
  <action>
    Per the locked validation strategy (Nyquist Dimension 8), capture a full schema-only dump
    so future phases can diff against the Phase 08 baseline. Dump the `uni_volunteer` db:

    ```bash
    docker exec uni-volunteer-scheduler-db-1 pg_dump -U postgres --schema-only uni_volunteer \
      > .planning/phases/08-schema-realignment-migration/08-schema-after.sql
    ```

    The file is ~a few hundred lines of CREATE TABLE + CREATE TYPE + CREATE INDEX statements.
    It is NOT a commit target for review but IS checked in as a reference artifact. Subsequent
    phases can diff against it to catch unintended schema changes.
  </action>
  <verify>
    <automated>test -s .planning/phases/08-schema-realignment-migration/08-schema-after.sql && grep -q "CREATE TABLE public.volunteers" .planning/phases/08-schema-realignment-migration/08-schema-after.sql</automated>
  </verify>
  <done>Schema dump file exists and contains the volunteers table definition.</done>
</task>

<task type="auto">
  <name>Task 12: pytest at new baseline (gate 4 — test suite passes)</name>
  <files>(no file written; verification only)</files>
  <action>
    **Gate 4 of 4: pytest at the new baseline.** Run the suite via the docker-network one-off
    container pattern from CLAUDE.md:

    ```bash
    # First run may need the test db recreated with fresh schema
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS test_uvs;"
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"

    docker run --rm \
      --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
      uni-volunteer-scheduler-backend \
      sh -c "pytest -q"
    ```

    **Expected result:** the suite passes at a NEW baseline lower than the v1.0 185-test
    baseline, because:
    - 5 prereq_override test files are deleted (Task 6): -N tests
    - Surgical prereq_slugs removals from test_models_phase5.py / test_templates_crud.py: -a few tests
    - Tests that touch `signup.user` will FAIL, not just be removed (per D-06). These must
      either be DELETED or marked `pytest.mark.skip` with a "Phase 09 fixup" comment so the
      suite can still go green.

    **Handling the signup.user breakage (per D-06):**
    Run `grep -rln "signup.user\b\|\.user\.email" backend/tests/` to find the failing tests.
    Candidates from RESEARCH §Code also referencing signup.user:
    - `backend/tests/test_magic_link_service.py` (lines 32, 42, 50, 59, 77)
    - Any other test touching `signup.user`.

    For each failing test: mark the test function with
    ```python
    @pytest.mark.skip(reason="Phase 08: signup.user removed; Phase 09 will update this test")
    ```
    Do NOT delete these tests — they cover real behavior that Phase 09 will re-wire. Skipping
    preserves them as a checklist for Phase 09.

    **Record the new pytest baseline count** (e.g. "148 passed, 12 skipped") — include in
    SUMMARY.md and the commit message for this task.

    Do NOT mask other failures with skip marks — only tests that break due to the `signup.user`
    relationship removal are eligible. Any test that fails for a different reason is a bug in
    Tasks 3-5 and must be fixed properly.
  </action>
  <verify>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"</automated>
  </verify>
  <done>pytest -q exits 0; new baseline count recorded; skipped tests are limited to those touching signup.user and each has a "Phase 09" reason string.</done>
</task>

<task type="auto">
  <name>Task 13: alembic check — autogen sanity</name>
  <files>(no file written; verification only)</files>
  <action>
    Run `alembic check` to confirm models.py matches the migration (autogen sanity). This
    catches any drift between Task 3 (migration) and Task 4 (model).

    ```bash
    docker run --rm \
      --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" \
      uni-volunteer-scheduler-backend \
      sh -c "alembic check"
    ```

    **Pass criteria:** exit 0, no diffs reported. If diffs appear:
    - A model column is missing from the migration → add it to migration (Task 3) OR remove it from model (Task 4).
    - A migration column is missing from the model → add it to the model.
    - Common gotcha: server_default values. Alembic check is strict about server_default equality.
      If a spurious diff appears about server_default text, adjust the model to match the
      migration's exact text() expression.

    Known acceptable diffs:
    - None. The goal is a clean `alembic check`.
  </action>
  <verify>
    <automated>docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" uni-volunteer-scheduler-backend sh -c "alembic check"</automated>
  </verify>
  <done>`alembic check` exits 0 with no model/migration drift.</done>
</task>

<task type="auto">
  <name>Task 14: Commit strategy — stage logical chunks as separate commits</name>
  <files>(git operations; no file written)</files>
  <action>
    Per the planning spec, aim for ~6-10 atomic commits that each map to a logical chunk.
    Order matters: the new migration depends on models being updated for alembic check to pass,
    but the migration can be committed before models. Recommended order:

    **Commit 1 — enum-leak fix (Task 2):**
    ```
    fix(alembic): drop privacymode/userrole/signupstatus/notificationtype on initial downgrade
    ```
    Files: `backend/alembic/versions/2465a60b9dbc_initial_schema.py`

    **Commit 2 — new migration (Task 3):**
    ```
    feat(08): alembic migration 0009 — v1.1 schema realignment
    ```
    Files: `backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py`

    **Commit 3 — models (Task 4):**
    ```
    feat(08): models.py — Volunteer, Quarter, SlotType; rewire Signup/MagicLinkToken; retire PrereqOverride
    ```
    Files: `backend/app/models.py`

    **Commit 4 — schemas (Task 5):**
    ```
    feat(08): schemas.py — drop PrereqOverride + prereq_slugs
    ```
    Files: `backend/app/schemas.py`

    **Commit 5 — test deletions (Task 6):**
    ```
    chore(08): delete retired prereq-override test files
    ```
    Files: the 5 deleted test files + any surgical edits to test_models_phase5.py and test_templates_crud.py

    **Commit 6 — signup.user skip marks (Task 12 sub-step):**
    ```
    chore(08): skip signup.user tests pending Phase 09 rewire
    ```
    Files: whatever test files got `pytest.mark.skip` decorators in Task 12.

    **Commit 7 — phonenumbers dep (Task 7):**
    ```
    chore(08): add phonenumbers>=8.13 for Phase 09 phone normalization
    ```
    Files: `backend/requirements.txt`

    **Commit 8 — verification artifacts (Tasks 10-11):**
    ```
    docs(08): psql shape inspection + pg_dump schema snapshot
    ```
    Files: `.planning/phases/08-schema-realignment-migration/08-verification-psql.txt`,
           `.planning/phases/08-schema-realignment-migration/08-schema-after.sql`

    Use the gsd-tools commit helper for each commit:
    ```bash
    node "$HOME/.claude/get-shit-done/bin/gsd-tools.cjs" commit "<message>" --files <file list>
    ```

    Do NOT squash. Do NOT amend. Each commit should be independently inspectable.

    If pytest (Task 12) was already green BEFORE Task 6 test deletions because of how files
    were staged, the commit order still holds — commits are about logical atomicity, not
    test-pass order. The round-trip (Task 9) should still pass at commits 1-3 boundary; pytest
    will only pass at commit 6 boundary.
  </action>
  <verify>
    <automated>git log --oneline -10 | grep -E "(08|alembic)" | wc -l | awk '$1 >= 6 {exit 0} {exit 1}'</automated>
  </verify>
  <done>At least 6 commits on the current branch reference Phase 08 or alembic, each atomic and independently buildable.</done>
</task>

<task type="auto">
  <name>Task 15: Phase 08 SUMMARY.md — flag signup.user tests for Phase 09 planner</name>
  <files>.planning/phases/08-schema-realignment-migration/08-SUMMARY.md</files>
  <action>
    Per D-06, the Phase 08 SUMMARY must list the exact test files and line-ranges that became
    invalid because `signup.user` was replaced with `signup.volunteer`. The Phase 09 planner
    will pick these up as follow-up items.

    Write `.planning/phases/08-schema-realignment-migration/08-SUMMARY.md` following the
    template at `$HOME/.claude/get-shit-done/templates/summary.md`, including these sections:

    **What shipped:**
    - Enum-leak fix in 2465a60b9dbc (4 enums: privacymode, userrole, signupstatus, notificationtype)
    - New migration 0009_phase08_v1_1_schema_realignment (volunteers table, events columns,
      slots columns, signups FK rewire with RESTRICT, magic_link_tokens extension,
      prereq_overrides retirement)
    - models.py: added Volunteer + Quarter + SlotType; extended MagicLinkPurpose; removed
      PrereqOverride; Signup.user → Signup.volunteer
    - schemas.py: removed PrereqOverride schemas and prereq_slugs fields
    - Deleted 5 retired prereq-override test files
    - Added phonenumbers>=8.13,<9 to requirements.txt

    **Verification results:**
    - Gate 1 (forward upgrade): PASS — head = 0009_phase08_v1_1_schema_realignment
    - Gate 2 (round-trip): PASS — zero DuplicateObject errors
    - Gate 3 (psql shape): PASS — see 08-verification-psql.txt
    - Gate 4 (pytest): PASS — new baseline = <N> passed, <M> skipped (vs v1.0 185 passed)
    - alembic check: PASS — no drift
    - pg_dump snapshot: 08-schema-after.sql

    **Flagged for Phase 09 planner — tests that need to be re-wired:**
    List every test file + function name + line number that had to be `pytest.mark.skip`'d
    in Task 12 due to `signup.user` removal. For each, note what the test is covering (e.g.
    "magic_link_service.issue_token — verifies email is pulled from signup.user.email").
    This is the checklist Phase 09 uses when it fixes the `signup → volunteer` code paths.

    **Flagged for Phase 12 planner — code that will break at runtime:**
    Per RESEARCH §Code also referencing signup.user, these files import and reference
    `signup.user` and will fail at runtime:
    - `backend/app/magic_link_service.py` line 100
    - `backend/app/emails.py` lines 56, 79, 102, 126, 151
    - `backend/app/celery_app.py` line 141
    - `backend/app/routers/admin.py` lines 205, 283, 369, 451, 539, 587, 652, 654, 959

    And per RESEARCH §prereq_overrides Blast Radius, these files reference PrereqOverride
    or prereq_slugs and will fail at import:
    - `backend/app/routers/admin.py` lines 1172-1255
    - `backend/app/routers/signups.py` lines 47, 88, 179, 185
    - `backend/app/routers/users.py` lines 186-187, 221-224
    - `backend/app/services/prereqs.py` (whole file)
    - `frontend/src/pages/admin/TemplatesSection.jsx`
    - `frontend/src/pages/EventDetailPage.jsx`
    - `frontend/src/pages/AdminTemplatesPage.jsx`
    - `frontend/src/lib/api.js` lines 281-284

    The app will NOT boot after Phase 08 until Phase 09 (for signup.user sites) and Phase 12
    (for prereq sites) land. This is expected and accepted per D-05 and D-06. Record it
    clearly so it's not a surprise.

    **Open items:** (none expected; list any that came up during execution)
  </action>
  <verify>
    <automated>test -f .planning/phases/08-schema-realignment-migration/08-SUMMARY.md && grep -q "signup.user" .planning/phases/08-schema-realignment-migration/08-SUMMARY.md && grep -q "phonenumbers" .planning/phases/08-schema-realignment-migration/08-SUMMARY.md</automated>
  </verify>
  <done>SUMMARY.md written with all 4 gate results, Phase 09 follow-up list (skip-marked tests), and Phase 12 follow-up list (runtime/import breakage sites).</done>
</task>

</tasks>

<verification>
## Phase 08 overall verification checklist

Run these in order. Each maps to a gate above; Phase 08 is complete when all are green.

- [ ] Gate 1: `alembic upgrade head` lands `0009_phase08_v1_1_schema_realignment` on a fresh db (Task 8)
- [ ] Gate 2: `alembic downgrade base && alembic upgrade head` round-trips with zero DuplicateObject errors (Task 9)
- [ ] Gate 3: `\d` shape inspection passes for volunteers/events/slots/signups/magic_link_tokens/module_templates (Task 10)
- [ ] Gate 3: prereq_overrides no longer exists; module_templates.prereq_slugs gone (Task 10)
- [ ] Gate 3: magiclinkpurpose enum contains signup_confirm + signup_manage (Task 10)
- [ ] pg_dump schema snapshot captured (Task 11)
- [ ] Gate 4: `pytest -q` exits 0 at new baseline (Task 12)
- [ ] `alembic check` exits 0 with no drift (Task 13)
- [ ] phonenumbers importable inside backend container (Task 7)
- [ ] 6+ atomic commits on the branch (Task 14)
- [ ] SUMMARY.md flags Phase 09 re-wire tests and Phase 12 runtime breakage sites (Task 15)
</verification>

<success_criteria>
Phase 08 is done when:

1. `alembic upgrade head` on a fresh db lands `0009_phase08_v1_1_schema_realignment`. [ROADMAP success #1]
2. `alembic downgrade base && alembic upgrade head` round-trips cleanly with no DuplicateObject errors. [ROADMAP success #2]
3. `volunteers` table exists with the locked column set; `signups.volunteer_id` FK with ON DELETE RESTRICT is enforced; `signups.user_id` is gone. [ROADMAP success #3, D-01]
4. `prereq_overrides` table and `module_templates.prereq_slugs` column no longer exist in the schema. [ROADMAP success #5, D-05]
5. `events` has structured columns (quarter enum, year, week_number, module_slug as plain string, school); the FK from events.module_slug to module_templates is dropped. [D-07, R08-02]
6. `slots` has slot_type, date, location columns alongside the existing start_time/end_time. [D-02, R08-03]
7. `magic_link_tokens` has volunteer_id FK; magiclinkpurpose enum includes signup_confirm and signup_manage. [D-03, R08-05]
8. `pytest -q` passes at the new baseline; signup.user tests are skip-marked with Phase 09 comments, not broken. [D-06, R08-09]
9. `alembic check` exits 0 — models.py matches the migration. [R08-08]
10. phonenumbers>=8.13,<9 is in requirements.txt and importable. [Phase 09 prep]
11. SUMMARY.md lists the exact tests Phase 09 must re-wire and the exact code sites Phase 12 must clean up.
</success_criteria>

<output>
After completion, create `.planning/phases/08-schema-realignment-migration/08-SUMMARY.md`
(Task 15 handles this). The SUMMARY must include all 4 gate results, the pytest baseline
delta, the pg_dump snapshot reference, and the Phase 09 / Phase 12 follow-up checklists.
</output>
