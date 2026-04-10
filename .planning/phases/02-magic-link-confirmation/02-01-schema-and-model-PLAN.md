---
phase: 02
plan: 01
name: Schema & Model — pending status + magic_link_tokens table
wave: 1
depends_on: []
files_modified:
  - backend/app/models.py
  - backend/alembic/versions/
  - backend/tests/test_models_magic_link.py
autonomous: true
requirements:
  - MagicLinkToken table
  - registered→confirmed transition
---

# Plan 02-01: Schema & Model

<objective>
Add `pending` to `SignupStatus` and create the `magic_link_tokens` table via
an Alembic migration. Update SQLAlchemy models. Existing rows grandfathered
as `confirmed`.
</objective>

<must_haves>
- `SignupStatus.pending` exists in the enum (Python + Postgres)
- `magic_link_tokens` table exists with all fields from CONTEXT.md
- Unique index on `token_hash`, composite index on `(email, created_at DESC)`
- Migration is reversible (downgrade drops the table; enum value removal documented as irreversible with a no-op)
- Alembic migration applied successfully against a fresh DB
- Existing `confirmed` rows remain `confirmed` after upgrade
</must_haves>

<tasks>

<task id="01-01-01" parallel="false">
<action>
Edit `backend/app/models.py`. Locate the `SignupStatus` enum (currently around line 35 with `confirmed`, `waitlisted`, `cancelled`). Add `pending = "pending"` as the FIRST member of the enum. The final enum must be:

```python
class SignupStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    waitlisted = "waitlisted"
    cancelled = "cancelled"
```

Then, in the same file, add a new SQLAlchemy model class `MagicLinkToken` with these exact fields:

```python
class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    signup_id = Column(UUID(as_uuid=True), ForeignKey("signups.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    signup = relationship("Signup", backref="magic_link_tokens")

    __table_args__ = (
        Index("ix_magic_link_tokens_email_created_at", "email", "created_at"),
    )
```

Ensure imports include `uuid`, `Column`, `String`, `DateTime`, `ForeignKey`, `Index`, `func`, `relationship`, and `UUID` from `sqlalchemy.dialects.postgresql`. Add any missing imports at the top of the file.
</action>
<read_first>
- backend/app/models.py
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
- .planning/phases/02-magic-link-confirmation/02-RESEARCH.md
</read_first>
<acceptance_criteria>
- `grep -q 'pending = "pending"' backend/app/models.py`
- `grep -q 'class MagicLinkToken' backend/app/models.py`
- `grep -q 'token_hash' backend/app/models.py`
- `grep -q 'ix_magic_link_tokens_email_created_at' backend/app/models.py`
- `grep -q 'ForeignKey("signups.id", ondelete="CASCADE")' backend/app/models.py`
- `python -c "from backend.app.models import SignupStatus, MagicLinkToken; assert SignupStatus.pending.value == 'pending'"` exits 0
</acceptance_criteria>
</task>

<task id="01-01-02" parallel="false">
<action>
Generate a new Alembic migration file in `backend/alembic/versions/`. Name it with the pattern `{revision}_add_pending_status_and_magic_link_tokens.py`. Use `alembic revision -m "add pending status and magic link tokens"` to create the skeleton, then fill the `upgrade()` and `downgrade()` functions:

`upgrade()` must:
1. Add `pending` to the `signupstatus` Postgres enum OUTSIDE a transaction:
   ```python
   with op.get_context().autocommit_block():
       op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'pending'")
   ```
2. Create the `magic_link_tokens` table with:
   - `id UUID PRIMARY KEY`
   - `token_hash TEXT NOT NULL UNIQUE`
   - `signup_id UUID NOT NULL REFERENCES signups(id) ON DELETE CASCADE`
   - `email TEXT NOT NULL`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
   - `expires_at TIMESTAMPTZ NOT NULL`
   - `consumed_at TIMESTAMPTZ NULL`
3. Create index `ix_magic_link_tokens_email_created_at` on `(email, created_at DESC)`.

`downgrade()` must:
1. Drop the `magic_link_tokens` table (drops the index automatically).
2. Document with a comment: `# Note: removing enum value 'pending' from signupstatus is not supported by Postgres; intentionally skipped.`

The migration docstring must include: `"Existing signup rows predate magic-link and are grandfathered as 'confirmed'. New rows default to 'pending' at the service layer, not at the DB column default."`
</action>
<read_first>
- backend/alembic/versions/ (list existing migrations to see latest revision ID for `down_revision`)
- backend/alembic/env.py
- backend/app/models.py (post task 01-01-01 edits)
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
</read_first>
<acceptance_criteria>
- New file matching `backend/alembic/versions/*_add_pending_status_and_magic_link_tokens.py` exists
- File contains `ALTER TYPE signupstatus ADD VALUE`
- File contains `autocommit_block()`
- File contains `op.create_table('magic_link_tokens'` or `op.create_table("magic_link_tokens"`
- File contains `op.create_index('ix_magic_link_tokens_email_created_at'` or double-quoted variant
- File contains `op.drop_table('magic_link_tokens'` or double-quoted variant
- File contains the grandfathered-rows docstring line
- `cd backend && alembic upgrade head` exits 0
- `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
</acceptance_criteria>
</task>

<task id="01-01-03" parallel="false">
<action>
Create `backend/tests/test_models_magic_link.py` with pytest tests that:

1. Import `SignupStatus` and assert `SignupStatus.pending.value == "pending"`.
2. Create a `Signup` row with status `pending`, flush, and assert it persists.
3. Create a `MagicLinkToken` row linked to the signup, flush, and assert:
   - `token_hash` uniqueness is enforced (second insert with same hash raises `IntegrityError`)
   - `consumed_at` defaults to `None`
   - `created_at` is auto-populated
4. Delete the parent `Signup` and assert cascade delete removes the token row.

Use the existing test database fixture from `backend/tests/conftest.py` (discover it by reading the file).
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/models.py
- backend/tests/ (list existing tests for fixture patterns)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_models_magic_link.py` exists
- File contains `SignupStatus.pending`
- File contains `MagicLinkToken`
- File contains `IntegrityError`
- File contains `CASCADE` test (delete signup, assert token gone)
- `cd backend && pytest tests/test_models_magic_link.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Models import cleanly: `python -c "from backend.app.models import SignupStatus, MagicLinkToken"` exits 0
- Migration applies: `cd backend && alembic upgrade head` exits 0
- Migration round-trips: `cd backend && alembic downgrade -1 && alembic upgrade head` exits 0
- Unit tests pass: `cd backend && pytest tests/test_models_magic_link.py -v` exits 0
- Existing tests still pass: `cd backend && pytest -q` exits 0
</verification>
