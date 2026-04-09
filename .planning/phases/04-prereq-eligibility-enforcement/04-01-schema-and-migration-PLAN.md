---
phase: 04
plan: 01
name: Schema & Migration — module_templates stub, prereq_overrides, Event.module_slug
wave: 1
depends_on: []
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/
  - backend/tests/test_models_phase4.py
autonomous: true
requirements:
  - module_templates stub table (forward-compatible with phase 5)
  - prereq_overrides table (admin audit-trailed overrides)
  - Event.module_slug nullable FK
  - Seed placeholder templates (TODO(data))
---

# Plan 04-01: Schema & Migration

<objective>
Introduce the minimal `module_templates` stub (PK `slug`, `name`, `prereq_slugs TEXT[]`,
timestamps), the `prereq_overrides` table with audit fields, and a nullable
`Event.module_slug` FK. Ship an Alembic migration that round-trips and seed a handful
of placeholder templates marked `TODO(data)`.
</objective>

<must_haves>
- `module_templates` table: `slug TEXT PK`, `name TEXT NOT NULL`, `prereq_slugs TEXT[] NOT NULL DEFAULT '{}'`, `created_at`, `updated_at`
- `prereq_overrides` table: `id UUID PK`, `user_id UUID FK users.id`, `module_slug TEXT FK module_templates.slug`, `reason TEXT NOT NULL CHECK(length(reason) >= 10)`, `created_by UUID FK users.id`, `created_at`, `revoked_at TIMESTAMPTZ NULL`
- `events.module_slug TEXT NULL FK module_templates.slug`
- Schema is forward-compatible: phase 5 will ADD columns to `module_templates`, never rename
- Migration applies cleanly and round-trips (upgrade → downgrade → upgrade)
- Seed rows inserted for `orientation`, `intro-bio`, `intro-chem` with empty `prereq_slugs` (orientation) and `['orientation']` for the intros, each annotated `TODO(data)` in a comment
</must_haves>

<tasks>

<task id="04-01-01" parallel="false">
<action>
Edit `backend/app/models.py`:

1. Add `ModuleTemplate` model:
   ```python
   class ModuleTemplate(Base):
       __tablename__ = "module_templates"
       slug = Column(String, primary_key=True)
       name = Column(String, nullable=False)
       prereq_slugs = Column(ARRAY(String), nullable=False, server_default="{}")
       created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
       updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
   ```
   Import `ARRAY` from `sqlalchemy.dialects.postgresql` if not already imported.

2. Add `PrereqOverride` model:
   ```python
   class PrereqOverride(Base):
       __tablename__ = "prereq_overrides"
       id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
       user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
       module_slug = Column(String, ForeignKey("module_templates.slug"), nullable=False)
       reason = Column(String, nullable=False)
       created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
       created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
       revoked_at = Column(DateTime(timezone=True), nullable=True)
       __table_args__ = (CheckConstraint("length(reason) >= 10", name="prereq_overrides_reason_min_len"),)
   ```

3. Add `module_slug = Column(String, ForeignKey("module_templates.slug"), nullable=True)` to the `Event` model.
</action>
<read_first>
- backend/app/models.py
- .planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md
</read_first>
<acceptance_criteria>
- `grep -q 'class ModuleTemplate' backend/app/models.py`
- `grep -q 'class PrereqOverride' backend/app/models.py`
- `grep -q 'prereq_slugs' backend/app/models.py`
- `grep -q 'module_slug' backend/app/models.py`
- `grep -q 'prereq_overrides_reason_min_len' backend/app/models.py`
- `python -c "from backend.app.models import ModuleTemplate, PrereqOverride"` exits 0
</acceptance_criteria>
</task>

<task id="04-01-02" parallel="false">
<action>
Generate an Alembic migration: `cd backend && alembic revision -m "phase4 prereq module templates and overrides"`.

`upgrade()`:
1. `op.create_table("module_templates", ...)` with columns matching the model. Use `sa.ARRAY(sa.String)` with `server_default=sa.text("'{}'")` for `prereq_slugs`.
2. `op.create_table("prereq_overrides", ...)` including the `CheckConstraint("length(reason) >= 10", name="prereq_overrides_reason_min_len")`.
3. `op.add_column("events", sa.Column("module_slug", sa.String(), sa.ForeignKey("module_templates.slug"), nullable=True))`.
4. Seed placeholder rows via `op.bulk_insert` on the `module_templates` table — `orientation` (empty prereqs), `intro-bio` (`['orientation']`), `intro-chem` (`['orientation']`). Precede with a `# TODO(data): replace with real Sci Trek modules` comment.

`downgrade()`:
1. `op.drop_column("events", "module_slug")`
2. `op.drop_table("prereq_overrides")`
3. `op.drop_table("module_templates")`

Docstring: `"Phase 4: prereq stub schema. module_templates is a minimal stub; phase 5 will ADD columns (never rename). Forward compatible."`
</action>
<read_first>
- backend/alembic/versions/ (find latest revision for down_revision)
- backend/alembic/env.py
- backend/app/models.py (after 04-01-01)
</read_first>
<acceptance_criteria>
- New file `backend/alembic/versions/*phase4_prereq_module_templates_and_overrides.py` exists
- File contains `create_table('module_templates'` (or double-quoted)
- File contains `create_table('prereq_overrides'`
- File contains `prereq_overrides_reason_min_len`
- File contains `module_slug`
- File contains `TODO(data)`
- File contains `bulk_insert` with `orientation`
- `cd backend && alembic upgrade head` exits 0
- `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
</acceptance_criteria>
</task>

<task id="04-01-03" parallel="false">
<action>
Create `backend/tests/test_models_phase4.py` with tests that:

1. Import `ModuleTemplate`, `PrereqOverride`, `Event` from `backend.app.models`.
2. Assert the three seed rows exist: `orientation`, `intro-bio`, `intro-chem`, and that `intro-bio.prereq_slugs == ['orientation']`.
3. Create an `Event` with `module_slug="orientation"`, flush, assert stored.
4. Create a `PrereqOverride` with a 10-char reason, flush, assert stored and `revoked_at is None`.
5. Create a `PrereqOverride` with a 5-char reason and assert the DB raises an `IntegrityError` on flush (CHECK constraint).
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/models.py
- backend/tests/test_models_phase3.py (fixture pattern)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_models_phase4.py` exists
- Contains `ModuleTemplate`
- Contains `PrereqOverride`
- Contains `IntegrityError`
- `cd backend && pytest tests/test_models_phase4.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Models import: `python -c "from backend.app.models import ModuleTemplate, PrereqOverride, Event"` exits 0
- Migration applies: `cd backend && alembic upgrade head` exits 0
- Migration round-trips: `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
- New tests pass: `cd backend && pytest tests/test_models_phase4.py -v` exits 0
- Existing tests still pass: `cd backend && pytest -q` exits 0
</verification>
