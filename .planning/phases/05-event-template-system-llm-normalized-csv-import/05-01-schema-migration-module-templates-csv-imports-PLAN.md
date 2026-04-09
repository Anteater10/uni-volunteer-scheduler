---
phase: 05
plan: 01
name: "Schema & Migration — full module_templates + csv_imports tracking"
wave: 1
depends_on: []
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/
  - backend/app/schemas.py
  - backend/tests/test_models_phase5.py
autonomous: true
requirements:
  - "`module_templates` table (slug PK, name, prereq slugs, default capacity, duration, materials)"
  - "seed with current modules"
---

# Plan 05-01: Schema & Migration — Full module_templates + csv_imports Tracking

<objective>
Promote the `module_templates` table stub from phase 4's plan into a full-featured table
with `default_capacity`, `duration_minutes`, `materials`, `description`, `metadata`, and
`deleted_at` (soft delete). Add a `csv_imports` table to track import jobs (status, raw CSV
hash, result payload). Add `Event.module_slug` nullable FK. Create an Alembic migration that
round-trips. Seed placeholder templates.
</objective>

<must_haves>
- `module_templates` table with columns: `slug TEXT PK`, `name TEXT NOT NULL`, `prereq_slugs TEXT[] NOT NULL DEFAULT '{}'`, `default_capacity INT NOT NULL DEFAULT 20`, `duration_minutes INT NOT NULL DEFAULT 90`, `materials TEXT[] NOT NULL DEFAULT '{}'`, `description TEXT`, `metadata JSONB NOT NULL DEFAULT '{}'`, `deleted_at TIMESTAMPTZ NULL`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
- `csv_imports` table with columns: `id UUID PK`, `uploaded_by UUID FK users.id NOT NULL`, `filename TEXT NOT NULL`, `raw_csv_hash TEXT NOT NULL`, `status TEXT NOT NULL DEFAULT 'pending'` (enum: pending, processing, ready, committed, failed), `result_payload JSONB`, `error_message TEXT`, `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`
- `events.module_slug TEXT NULL FK module_templates.slug`
- Alembic migration that applies cleanly and round-trips (upgrade -> downgrade -> upgrade)
- Seed rows for `orientation`, `intro-bio`, `intro-chem`, `intro-physics`, `intro-astro` with prereq_slugs `[]` for orientation and `['orientation']` for the intros (annotated TODO(data))
- Pydantic schemas for ModuleTemplateRead, ModuleTemplateCreate, ModuleTemplateUpdate, CsvImportRead
</must_haves>

<tasks>

<task id="05-01-01" parallel="false">
<read_first>
- backend/app/models.py
- backend/app/database.py
</read_first>
<action>
Edit `backend/app/models.py`:

1. Add `ARRAY` import from `sqlalchemy.dialects.postgresql`:
   ```python
   from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
   ```

2. Add `CsvImportStatus` enum:
   ```python
   class CsvImportStatus(str, enum.Enum):
       pending = "pending"
       processing = "processing"
       ready = "ready"
       committed = "committed"
       failed = "failed"
   ```

3. Add `ModuleTemplate` model:
   ```python
   class ModuleTemplate(Base):
       __tablename__ = "module_templates"
       slug = Column(String, primary_key=True)
       name = Column(String(255), nullable=False)
       prereq_slugs = Column(ARRAY(String), nullable=False, server_default="{}")
       default_capacity = Column(Integer, nullable=False, server_default="20")
       duration_minutes = Column(Integer, nullable=False, server_default="90")
       materials = Column(ARRAY(String), nullable=False, server_default="{}")
       description = Column(Text, nullable=True)
       metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
       deleted_at = Column(DateTime(timezone=True), nullable=True)
       created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
       updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
   ```

4. Add `CsvImport` model:
   ```python
   class CsvImport(Base):
       __tablename__ = "csv_imports"
       id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
       uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
       filename = Column(String(512), nullable=False)
       raw_csv_hash = Column(String(64), nullable=False)
       status = Column(Enum(CsvImportStatus, name="csvimportstatus"), default=CsvImportStatus.pending, nullable=False)
       result_payload = Column(JSONB, nullable=True)
       error_message = Column(Text, nullable=True)
       created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
       updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
       uploader = relationship("User")
   ```

5. Add `module_slug` column to `Event`:
   ```python
   module_slug = Column(String, ForeignKey("module_templates.slug"), nullable=True)
   ```
</action>
<acceptance_criteria>
- `grep -c "class ModuleTemplate" backend/app/models.py` returns `1`
- `grep -c "class CsvImport" backend/app/models.py` returns `1`
- `grep "class CsvImportStatus" backend/app/models.py` returns a match
- `grep "module_slug.*ForeignKey.*module_templates" backend/app/models.py` returns a match
- `grep "ARRAY\|JSONB" backend/app/models.py` returns matches for both imports
- `grep "default_capacity" backend/app/models.py` returns a match
- `grep "duration_minutes" backend/app/models.py` returns a match
- `grep "materials" backend/app/models.py` returns a match
- `grep 'deleted_at' backend/app/models.py` returns a match
</acceptance_criteria>
</task>

<task id="05-01-02" parallel="false">
<read_first>
- backend/app/schemas.py
- backend/app/models.py
</read_first>
<action>
Edit `backend/app/schemas.py`:

1. Import `CsvImportStatus` from models.
2. Add module template schemas:
   ```python
   # =========================
   # MODULE TEMPLATE SCHEMAS
   # =========================
   class ModuleTemplateBase(BaseModel):
       name: str
       prereq_slugs: List[str] = []
       default_capacity: int = 20
       duration_minutes: int = 90
       materials: List[str] = []
       description: Optional[str] = None
       metadata: dict = {}

   class ModuleTemplateCreate(ModuleTemplateBase):
       slug: str

   class ModuleTemplateUpdate(BaseModel):
       name: Optional[str] = None
       prereq_slugs: Optional[List[str]] = None
       default_capacity: Optional[int] = None
       duration_minutes: Optional[int] = None
       materials: Optional[List[str]] = None
       description: Optional[str] = None
       metadata: Optional[dict] = None

   class ModuleTemplateRead(ORMBase, ModuleTemplateBase):
       slug: str
       deleted_at: Optional[datetime] = None
       created_at: datetime
       updated_at: datetime
   ```

3. Add CSV import schemas:
   ```python
   # =========================
   # CSV IMPORT SCHEMAS
   # =========================
   class CsvImportRead(ORMBase):
       id: UUID
       uploaded_by: UUID
       filename: str
       status: str
       result_payload: Optional[dict] = None
       error_message: Optional[str] = None
       created_at: datetime
       updated_at: datetime
   ```
</action>
<acceptance_criteria>
- `grep "class ModuleTemplateCreate" backend/app/schemas.py` returns a match
- `grep "class ModuleTemplateRead" backend/app/schemas.py` returns a match
- `grep "class ModuleTemplateUpdate" backend/app/schemas.py` returns a match
- `grep "class CsvImportRead" backend/app/schemas.py` returns a match
- `grep "default_capacity.*int.*20" backend/app/schemas.py` returns a match
- `grep "duration_minutes.*int.*90" backend/app/schemas.py` returns a match
</acceptance_criteria>
</task>

<task id="05-01-03" parallel="false">
<read_first>
- backend/alembic/versions/
- backend/app/models.py (after task 01)
</read_first>
<action>
Generate Alembic migration via `alembic revision --autogenerate -m "phase5_module_templates_csv_imports"`.

The migration MUST:
1. Create `module_templates` table with all columns from the model
2. Create `csv_imports` table with all columns from the model
3. Add `events.module_slug` nullable FK column
4. Create the `csvimportstatus` enum type
5. Insert seed data for templates:
   ```python
   op.execute("""
   INSERT INTO module_templates (slug, name, prereq_slugs, default_capacity, duration_minutes, materials, description)
   VALUES
     ('orientation', 'Orientation', '{}', 30, 60, '{}', 'First-time volunteer orientation -- TODO(data)'),
     ('intro-bio', 'Intro to Biology', '{orientation}', 20, 90, '{}', 'Biology module -- TODO(data)'),
     ('intro-chem', 'Intro to Chemistry', '{orientation}', 20, 90, '{}', 'Chemistry module -- TODO(data)'),
     ('intro-physics', 'Intro to Physics', '{orientation}', 20, 90, '{}', 'Physics module -- TODO(data)'),
     ('intro-astro', 'Intro to Astronomy', '{orientation}', 20, 90, '{}', 'Astronomy module -- TODO(data)')
   ON CONFLICT (slug) DO NOTHING;
   """)
   ```
6. Downgrade drops `events.module_slug`, drops `csv_imports` table, drops `module_templates` table, drops `csvimportstatus` enum

Verify round-trip: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
</action>
<acceptance_criteria>
- A new file exists in `backend/alembic/versions/` containing `phase5_module_templates_csv_imports`
- `grep "module_templates" backend/alembic/versions/*phase5*` returns matches
- `grep "csv_imports" backend/alembic/versions/*phase5*` returns matches
- `grep "module_slug" backend/alembic/versions/*phase5*` returns matches
- `grep "orientation" backend/alembic/versions/*phase5*` returns a match (seed data)
- Migration round-trips without error: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` exits 0
</acceptance_criteria>
</task>

<task id="05-01-04" parallel="false">
<read_first>
- backend/app/models.py
- backend/app/schemas.py
</read_first>
<action>
Create `backend/tests/test_models_phase5.py`:

```python
"""Phase 5 model tests — ModuleTemplate + CsvImport + Event.module_slug."""
import pytest
from app.models import ModuleTemplate, CsvImport, CsvImportStatus, Event


def test_module_template_columns():
    """ModuleTemplate has all required columns."""
    cols = {c.name for c in ModuleTemplate.__table__.columns}
    expected = {"slug", "name", "prereq_slugs", "default_capacity", "duration_minutes",
                "materials", "description", "metadata", "deleted_at", "created_at", "updated_at"}
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_csv_import_columns():
    """CsvImport has all required columns."""
    cols = {c.name for c in CsvImport.__table__.columns}
    expected = {"id", "uploaded_by", "filename", "raw_csv_hash", "status",
                "result_payload", "error_message", "created_at", "updated_at"}
    assert expected.issubset(cols), f"Missing columns: {expected - cols}"


def test_csv_import_status_enum():
    """CsvImportStatus has all expected values."""
    assert set(CsvImportStatus) == {
        CsvImportStatus.pending,
        CsvImportStatus.processing,
        CsvImportStatus.ready,
        CsvImportStatus.committed,
        CsvImportStatus.failed,
    }


def test_event_has_module_slug():
    """Event model has nullable module_slug FK."""
    cols = {c.name for c in Event.__table__.columns}
    assert "module_slug" in cols
    col = Event.__table__.c.module_slug
    assert col.nullable is True
```
</action>
<acceptance_criteria>
- `test -f backend/tests/test_models_phase5.py` exits 0
- `grep "test_module_template_columns" backend/tests/test_models_phase5.py` returns a match
- `grep "test_csv_import_columns" backend/tests/test_models_phase5.py` returns a match
- `grep "test_event_has_module_slug" backend/tests/test_models_phase5.py` returns a match
- `python -m pytest backend/tests/test_models_phase5.py -x` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- `alembic upgrade head` succeeds
- `alembic downgrade -1 && alembic upgrade head` round-trips
- `python -m pytest backend/tests/test_models_phase5.py -x` passes
- `SELECT slug FROM module_templates;` returns 5 seed rows (orientation, intro-bio, intro-chem, intro-physics, intro-astro)
</verification>

<threat_model>
- **Input validation on slug PK:** Slug is TEXT PK — ensure CRUD endpoints (plan 03) validate slug format (alphanumeric + hyphens, max 64 chars). Migration itself has no injection risk since seeds are hardcoded.
- **JSONB metadata injection:** `metadata` JSONB column accepts arbitrary JSON. CRUD endpoints must validate payload size (max 10KB) to prevent storage abuse. No threat at schema level.
- **Soft delete bypass:** `deleted_at` field — queries must filter `WHERE deleted_at IS NULL` to avoid exposing deleted templates. Handled in plan 03 service layer.
</threat_model>
