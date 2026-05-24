# Phase 35-01 — Human-Feedback Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship per-response (👍/👎) and per-session (1–5) human feedback on top of the Phase 33 + 34 copilot. Surface aggregates to staff via a new admin page. Log every rating as structured INFO so the Phase 35-02+ eval harness can replay them.

**Architecture:** Two new tables (`copilot_message_ratings`, `copilot_session_ratings`) added by Alembic `0023`. New `backend/app/copilot/feedback/` package with `aggregates.py` for the weekly roll-up and bottom-quartile SQL. Four new endpoints under the existing `/api/v1/copilot` prefix, all gated by the existing `_require_flag_on` + `_require_admin_or_organizer` pair. A new SSE event `message_persisted` lets the frontend thread the assistant message id into each bubble. Three new frontend components (`MessageRatingButtons`, `SessionRatingModal`, `AdminCopilotFeedbackPage`) plus an admin nav entry and route wiring.

**Tech stack:** Python 3.11 / FastAPI / SQLAlchemy / Alembic / Postgres / pytest / React 19 / Vitest / Tailwind v4.

**Spec:** `docs/superpowers/specs/2026-05-23-phase-35-01-human-feedback-design.md`

**Branch:** `feature/v1.4-phase-35-01-human-feedback`

---

## Preamble — why six sub-phases (not eleven)

Phase 34 used eleven sub-phases because it had three separate moving parts (summariser, extractor, profile-block) plus a Celery beat job and an adversarial suite. Phase 35-01 has no Celery work, no adversarial pass (deliberately deferred — see spec §8 "Adversarial scope"), and the backend slice is tight enough that "schema" and "ORM" collapse into one sub-phase. The split below keeps each sub-phase to a coherent commit cluster (3–6 tasks) and lets the frontend SSE-wiring task land in its own sub-phase because it touches both backend and frontend simultaneously and benefits from a single bisectable commit boundary.

Sub-phase split:

| Sub-phase | Topic | Tasks |
|---|---|---|
| 35-01-A | Schema + ORM (Alembic 0023 + models + fixtures) | T1–T3 |
| 35-01-B | Pydantic schemas + 4 endpoints | T4–T9 |
| 35-01-C | Weekly aggregates + bottom-quartile SQL | T10–T12 |
| 35-01-D | SSE `message_persisted` event + frontend id wiring | T13–T15 |
| 35-01-E | Frontend components (rating buttons, modal, admin page) | T16–T20 |
| 35-01-F | Closeout (SUMMARY + ROADMAP + STATE; no PR) | T21–T23 |

Each task ships **failing test → minimal impl → passing test → commit**. Every backend endpoint test MUST include `monkeypatch.setattr(settings, "copilot_enabled", True)` — we learned the hard way in Phase 34 that the global flag defaults to off in the test environment, so any endpoint test that skips this line will return 404 instead of the real response.

### Plan-vs-reality preamble (READ FIRST — applies to every backend test snippet below)

The test snippets in this plan use **imagined fixtures `authed_client_admin` and `admin_user` that DO NOT exist** in the codebase. The actual pattern used across all of `backend/tests/copilot/api/*` (e.g. `test_profile_endpoints.py`) is:

```python
from tests.fixtures.helpers import auth_headers, make_user

def test_foo(client, db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    resp = client.post(url, json=body, headers=auth_headers(client, admin))
```

When executing any task in this plan, **mechanically rewrite** every `authed_client_admin.post(...)` to `client.post(..., headers=auth_headers(client, admin))` and every `def test_x(..., authed_client_admin, admin_user)` to `def test_x(client, db_session)` followed by `admin = make_user(db_session, role=models.UserRole.admin); db_session.commit()`. The autouse `_enable_copilot` fixture from `test_profile_endpoints.py` is the canonical reference — copy that pattern.

Other adaptations that will surface during execution:
- `other_admin_user` is only defined in `backend/tests/copilot/adversarial/conftest.py`. If a task needs it, define it locally in the new test file as `make_user(db_session, role=models.UserRole.admin)` rather than importing.
- Pydantic schema imports may need `model_config = ConfigDict(from_attributes=True)` for ORM→Pydantic conversion (Pydantic v2 syntax) — the plan snippets show v1 syntax in places.

---

## File structure

New files (backend):
- `backend/alembic/versions/0023_add_copilot_feedback_tables.py`
- `backend/app/copilot/feedback/__init__.py`
- `backend/app/copilot/feedback/aggregates.py`
- `backend/tests/copilot/feedback/__init__.py`
- `backend/tests/copilot/feedback/test_aggregates.py`
- `backend/tests/copilot/feedback/test_models.py`
- `backend/tests/copilot/api/test_rating_schemas.py`
- `backend/tests/copilot/api/test_message_rating_endpoint.py`
- `backend/tests/copilot/api/test_session_rating_endpoint.py`
- `backend/tests/copilot/api/test_feedback_admin_endpoints.py`
- `backend/tests/copilot/api/test_message_persisted_sse.py`

Modified files (backend):
- `backend/app/models.py` — add `CopilotMessageRating` + `CopilotSessionRating`.
- `backend/app/copilot/schemas.py` — add `MessageRatingCreate`, `MessageRatingRead`, `SessionRatingCreate`, `SessionRatingRead`, `WeeklyFeedback`, `WeeklyFeedbackResponse`, `BottomMessageEntry`, `BottomMessagesResponse`.
- `backend/app/copilot/router.py` — add four endpoints; emit `event: message_persisted` after each assistant message persist.

New files (frontend):
- `frontend/src/copilot/MessageRatingButtons.jsx`
- `frontend/src/copilot/SessionRatingModal.jsx`
- `frontend/src/copilot/__tests__/MessageRatingButtons.test.jsx`
- `frontend/src/copilot/__tests__/SessionRatingModal.test.jsx`
- `frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx`
- `frontend/src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx`

Modified files (frontend):
- `frontend/src/copilot/useCopilotStream.js` — capture `message_persisted` event; expose via callback.
- `frontend/src/copilot/CopilotDrawer.jsx` — thread assistant message id into each rendered bubble; mount `<SessionRatingModal />`; intercept close path.
- `frontend/src/pages/admin/AdminLayout.jsx` — add nav entry.
- `frontend/src/App.jsx` — wire `/admin/copilot-feedback` route.

Docs (two-folder rule, one per sub-phase):
- `docs/documentation/35-01-human-feedback/01-schema.md` … `06-closeout.md`
- `docs/learning/35-01-human-feedback/01-schema.md` … `06-closeout.md`

CI gate (modified):
- `.github/workflows/ci.yml` — add per-package coverage gate `app.copilot.feedback` at 95%.

---

## 35-01-A — Schema + ORM

### Task 1 (35-01-A-Task-01): Alembic 0023 — two tables + indexes

**Files:**
- Create: `backend/alembic/versions/0023_add_copilot_feedback_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""add copilot_message_ratings and copilot_session_ratings

Revision ID: 0023_add_copilot_feedback_tables
Revises: 0022_add_copilot_user_profiles_and_session_columns
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023_add_copilot_feedback_tables"
down_revision = "0022_add_copilot_user_profiles_and_session_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "copilot_message_ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("value IN ('up', 'down')", name="ck_message_rating_value"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_rating_per_user"),
    )
    op.create_index(
        "ix_copilot_message_ratings_message_id",
        "copilot_message_ratings",
        ["message_id"],
    )
    op.execute(
        "CREATE INDEX ix_copilot_message_ratings_value_down "
        "ON copilot_message_ratings (created_at DESC) WHERE value = 'down'"
    )

    op.create_table(
        "copilot_session_ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value BETWEEN 1 AND 5", name="ck_session_rating_value_range"
        ),
        sa.UniqueConstraint("session_id", "user_id", name="uq_session_rating_per_user"),
    )
    op.create_index(
        "ix_copilot_session_ratings_session_id",
        "copilot_session_ratings",
        ["session_id"],
    )
    op.execute(
        "CREATE INDEX ix_copilot_session_ratings_value_low "
        "ON copilot_session_ratings (created_at DESC) WHERE value <= 2"
    )


def downgrade():
    op.drop_index(
        "ix_copilot_session_ratings_value_low",
        table_name="copilot_session_ratings",
    )
    op.drop_index(
        "ix_copilot_session_ratings_session_id",
        table_name="copilot_session_ratings",
    )
    op.drop_table("copilot_session_ratings")
    op.drop_index(
        "ix_copilot_message_ratings_value_down",
        table_name="copilot_message_ratings",
    )
    op.drop_index(
        "ix_copilot_message_ratings_message_id",
        table_name="copilot_message_ratings",
    )
    op.drop_table("copilot_message_ratings")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose run --rm migrate
```

Verify:
```bash
docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d copilot_message_ratings"
docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c "\d copilot_session_ratings"
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0023_add_copilot_feedback_tables.py
git commit -m "$(cat <<'EOF'
feat(35-01-A): copilot_message_ratings + copilot_session_ratings schema
EOF
)"
```

**Plan vs reality note:** The partial indexes use `op.execute()` because Alembic's `create_index(... postgresql_where=...)` syntax is finicky with autogenerate. Raw SQL is the path Phase 31 also took (see `0019_enable_pgvector_corpus_tables.py`). Down-revision is `0022_*` — confirmed against `ls backend/alembic/versions/`.

### Task 2 (35-01-A-Task-02): ORM models + fixtures

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/tests/copilot/feedback/__init__.py` (empty)
- Create: `backend/tests/copilot/feedback/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/feedback/test_models.py
import uuid

from app import models


def _seed_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def _seed_message(db_session, sess, role=None):
    msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=sess.id,
        role=role or models.CopilotMessageRole.assistant,
        content="ok",
    )
    db_session.add(msg)
    db_session.commit()
    return msg


def test_copilot_message_rating_round_trip(db_session, admin_user):
    sess = _seed_session(db_session, admin_user)
    msg = _seed_message(db_session, sess)
    r = models.CopilotMessageRating(
        message_id=msg.id, user_id=admin_user.id, value="up"
    )
    db_session.add(r)
    db_session.commit()
    fetched = (
        db_session.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=admin_user.id)
        .one()
    )
    assert fetched.value == "up"
    assert fetched.created_at is not None


def test_copilot_session_rating_round_trip(db_session, admin_user):
    sess = _seed_session(db_session, admin_user)
    r = models.CopilotSessionRating(
        session_id=sess.id, user_id=admin_user.id, value=4, comment=None
    )
    db_session.add(r)
    db_session.commit()
    fetched = (
        db_session.query(models.CopilotSessionRating)
        .filter_by(session_id=sess.id, user_id=admin_user.id)
        .one()
    )
    assert fetched.value == 4
```

- [ ] **Step 2: Run, expect fail**

```bash
docker run --rm --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/copilot/feedback/test_models.py -v --no-cov"
```

Expected: `AttributeError: module 'app.models' has no attribute 'CopilotMessageRating'`.

- [ ] **Step 3: Implement** — append to `backend/app/models.py`:

```python
class CopilotMessageRating(Base):
    """Phase 35-01: per-message 👍/👎 rating.

    Unique on (message_id, user_id). Subsequent ratings overwrite via the
    upsert path in the router (see ``POST /messages/{id}/rating``).
    """

    __tablename__ = "copilot_message_ratings"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("copilot_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    value = Column(String(8), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("CopilotMessage")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_rating_per_user"),
    )


class CopilotSessionRating(Base):
    """Phase 35-01: end-of-session 1-5 rating.

    Write-once. Unique on (session_id, user_id); second submission 409s.
    """

    __tablename__ = "copilot_session_ratings"

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    value = Column(SmallInteger, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("CopilotSession")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_rating_per_user"),
    )
```

Ensure `SmallInteger`, `UniqueConstraint`, `String`, `Text` are imported at the top of `models.py` — most already are. Add `SmallInteger` if missing.

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py \
        backend/tests/copilot/feedback/__init__.py \
        backend/tests/copilot/feedback/test_models.py
git commit -m "$(cat <<'EOF'
feat(35-01-A): CopilotMessageRating + CopilotSessionRating ORM
EOF
)"
```

**Plan vs reality note:** The existing `backend/tests/copilot/conftest.py` provides `admin_user` and `db_session`. We do not need a new `other_admin_user` fixture — that one was added in Phase 34 and is reusable. Confirm it exists before writing test 6.

### Task 3 (35-01-A-Task-03): Sub-phase 35-01-A docs

**Files:**
- Create: `docs/documentation/35-01-human-feedback/01-schema.md`
- Create: `docs/learning/35-01-human-feedback/01-schema.md`

- [ ] **Step 1: Documentation (≥80 lines)** — table shapes, FK CASCADE rationale, partial indexes (`value='down'` and `value<=2`) and how they support the bottom-quartile drill-down query, why we keep `comment` separate from the value (privacy: drop comment text from structured logs while keeping value), the upsert vs insert-only difference between the two tables.

- [ ] **Step 2: Learning (≥80 lines)** — teaching note on "rating tables: upsert vs insert-only" — why per-message ratings are mutable (user changed their mind) and per-session ratings are not (the session is gone), with worked example of what happens if you swap the rule.

- [ ] **Step 3: Commit**

```bash
git add docs/documentation/35-01-human-feedback/01-schema.md \
        docs/learning/35-01-human-feedback/01-schema.md
git commit -m "$(cat <<'EOF'
docs(35-01-A): schema — documentation + learning
EOF
)"
```

---

## 35-01-B — Pydantic schemas + endpoints

### Task 4 (35-01-B-Task-01): Pydantic schemas with `model_validator`

**Files:**
- Modify: `backend/app/copilot/schemas.py`
- Create: `backend/tests/copilot/api/test_rating_schemas.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/api/test_rating_schemas.py
import pytest
from pydantic import ValidationError

from app.copilot.schemas import (
    MessageRatingCreate,
    SessionRatingCreate,
)


def test_message_rating_up_no_comment_ok():
    r = MessageRatingCreate(value="up")
    assert r.value == "up"
    assert r.comment is None


def test_message_rating_down_requires_comment():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="down")


def test_message_rating_down_whitespace_comment_rejected():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="down", comment="   ")


def test_message_rating_down_real_comment_ok():
    r = MessageRatingCreate(value="down", comment="wrong week")
    assert r.value == "down"
    assert r.comment == "wrong week"


def test_message_rating_comment_max_length():
    with pytest.raises(ValidationError):
        MessageRatingCreate(value="up", comment="x" * 1001)


def test_session_rating_high_no_comment_ok():
    r = SessionRatingCreate(value=4)
    assert r.value == 4


def test_session_rating_low_requires_comment():
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=2)


def test_session_rating_one_with_comment_ok():
    r = SessionRatingCreate(value=1, comment="lost my data")
    assert r.value == 1
    assert r.comment == "lost my data"


def test_session_rating_value_bounds():
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=0)
    with pytest.raises(ValidationError):
        SessionRatingCreate(value=6)
```

- [ ] **Step 2: Run, expect fail**

```bash
docker run --rm --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest tests/copilot/api/test_rating_schemas.py -v --no-cov"
```

- [ ] **Step 3: Implement** — append to `backend/app/copilot/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import conint, model_validator


_MAX_COMMENT_LEN = 1000


class MessageRatingCreate(BaseModel):
    value: Literal["up", "down"]
    comment: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "MessageRatingCreate":
        if self.comment is not None and len(self.comment) > _MAX_COMMENT_LEN:
            raise ValueError("comment exceeds 1000 characters")
        if self.value == "down" and not (self.comment or "").strip():
            raise ValueError("comment is required for thumbs-down ratings")
        return self


class MessageRatingRead(BaseModel):
    message_id: str
    value: Literal["up", "down"]
    comment: str | None
    updated_at: datetime


class SessionRatingCreate(BaseModel):
    value: conint(ge=1, le=5)
    comment: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "SessionRatingCreate":
        if self.comment is not None and len(self.comment) > _MAX_COMMENT_LEN:
            raise ValueError("comment exceeds 1000 characters")
        if self.value <= 2 and not (self.comment or "").strip():
            raise ValueError("comment is required for ratings of 2 or lower")
        return self


class SessionRatingRead(BaseModel):
    session_id: str
    value: int
    comment: str | None
    created_at: datetime


class WeeklyFeedback(BaseModel):
    iso_week: str
    thumbs_up_rate: float | None
    session_rating_avg: float | None
    n_messages: int
    n_sessions: int


class WeeklyFeedbackResponse(BaseModel):
    weeks: list[WeeklyFeedback]


class BottomMessageEntry(BaseModel):
    message_id: str
    session_id: str
    model_id: str | None
    rater_role: str
    rated_at: datetime
    comment: str | None
    assistant_text: str
    prior_user_text: str | None


class BottomMessagesResponse(BaseModel):
    messages: list[BottomMessageEntry]
```

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/schemas.py \
        backend/tests/copilot/api/test_rating_schemas.py
git commit -m "$(cat <<'EOF'
feat(35-01-B): rating pydantic schemas with required-comment validators
EOF
)"
```

### Task 5 (35-01-B-Task-02): `POST /messages/{message_id}/rating`

**Files:**
- Modify: `backend/app/copilot/router.py`
- Create: `backend/tests/copilot/api/test_message_rating_endpoint.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/api/test_message_rating_endpoint.py
import uuid

import pytest

from app import models
from app.config import settings


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_message(db_session, user, role=None):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id="openrouter/auto",
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    msg = models.CopilotMessage(
        id=uuid.uuid4(), session_id=sess.id,
        role=role or models.CopilotMessageRole.assistant, content="ok",
    )
    db_session.add(msg)
    db_session.commit()
    return sess, msg


def test_post_up_rating_creates_row(db_session, authed_client_admin, admin_user):
    _, msg = _seed_message(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating", json={"value": "up"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"] == "up"
    assert body["comment"] is None


def test_post_down_without_comment_422(db_session, authed_client_admin, admin_user):
    _, msg = _seed_message(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating", json={"value": "down"}
    )
    assert resp.status_code == 422


def test_post_down_with_comment_creates_row(
    db_session, authed_client_admin, admin_user
):
    _, msg = _seed_message(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "down", "comment": "wrong week"},
    )
    assert resp.status_code == 200
    assert resp.json()["comment"] == "wrong week"


def test_post_rating_upserts(db_session, authed_client_admin, admin_user):
    _, msg = _seed_message(db_session, admin_user)
    authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating", json={"value": "up"}
    )
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating",
        json={"value": "down", "comment": "changed mind"},
    )
    assert resp.status_code == 200
    rows = (
        db_session.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=admin_user.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].value == "down"


def test_post_rating_404_for_other_user_message(
    db_session, authed_client_admin, other_admin_user
):
    _, msg = _seed_message(db_session, other_admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating", json={"value": "up"}
    )
    assert resp.status_code == 404


def test_post_rating_404_when_copilot_disabled(
    db_session, authed_client_admin, admin_user, monkeypatch
):
    monkeypatch.setattr(settings, "copilot_enabled", False)
    _, msg = _seed_message(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/messages/{msg.id}/rating", json={"value": "up"}
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — add to `backend/app/copilot/router.py` (after the existing `delete_profile` handler):

```python
from .schemas import (
    BottomMessageEntry,
    BottomMessagesResponse,
    MessageRatingCreate,
    MessageRatingRead,
    SessionRatingCreate,
    SessionRatingRead,
    WeeklyFeedback,
    WeeklyFeedbackResponse,
)


def _load_owned_message(
    db: Session, message_id: UUID, user: models.User
) -> models.CopilotMessage:
    msg = (
        db.query(models.CopilotMessage)
        .join(models.CopilotSession,
              models.CopilotMessage.session_id == models.CopilotSession.id)
        .filter(
            models.CopilotMessage.id == message_id,
            models.CopilotSession.user_id == user.id,
        )
        .first()
    )
    if msg is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return msg


@router.post("/messages/{message_id}/rating", response_model=MessageRatingRead)
def post_message_rating(
    message_id: UUID,
    body: MessageRatingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    msg = _load_owned_message(db, message_id, current_user)
    row = (
        db.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=current_user.id)
        .first()
    )
    if row is None:
        row = models.CopilotMessageRating(
            message_id=msg.id,
            user_id=current_user.id,
            value=body.value,
            comment=(body.comment or None),
        )
        db.add(row)
    else:
        row.value = body.value
        row.comment = body.comment or None
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    logger.info(
        "copilot_message_rated message_id=%s session_id=%s user_id=%s "
        "role=%s value=%s has_comment=%s",
        msg.id, msg.session_id, current_user.id, current_user.role.value,
        row.value, bool(row.comment),
    )
    return MessageRatingRead(
        message_id=str(msg.id),
        value=row.value,
        comment=row.comment,
        updated_at=row.updated_at,
    )
```

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/router.py \
        backend/tests/copilot/api/test_message_rating_endpoint.py
git commit -m "$(cat <<'EOF'
feat(35-01-B): POST /messages/{id}/rating with upsert + ownership check
EOF
)"
```

**Plan vs reality note:** The `_enable_copilot` autouse fixture is mandatory. Phase 34 endpoint tests without it returned 404 every time — wasted ~30 minutes debugging. Every endpoint test file in this phase MUST start with that fixture.

### Task 6 (35-01-B-Task-03): `POST /sessions/{session_id}/rating`

**Files:**
- Modify: `backend/app/copilot/router.py`
- Create: `backend/tests/copilot/api/test_session_rating_endpoint.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/api/test_session_rating_endpoint.py
import uuid

import pytest

from app import models
from app.config import settings


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_session_with_assistant(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id="openrouter/auto",
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(), session_id=sess.id,
            role=models.CopilotMessageRole.assistant, content="ok",
        )
    )
    db_session.commit()
    return sess


def _seed_empty_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id="openrouter/auto",
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def test_post_session_rating_4_no_comment_ok(
    db_session, authed_client_admin, admin_user
):
    sess = _seed_session_with_assistant(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 4}
    )
    assert resp.status_code == 201
    assert resp.json()["value"] == 4


def test_post_session_rating_2_requires_comment(
    db_session, authed_client_admin, admin_user
):
    sess = _seed_session_with_assistant(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 2}
    )
    assert resp.status_code == 422


def test_post_session_rating_409_on_duplicate(
    db_session, authed_client_admin, admin_user
):
    sess = _seed_session_with_assistant(db_session, admin_user)
    first = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 3}
    )
    second = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 4}
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_post_session_rating_404_for_empty_session(
    db_session, authed_client_admin, admin_user
):
    sess = _seed_empty_session(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 4}
    )
    assert resp.status_code == 404


def test_post_session_rating_404_for_other_user(
    db_session, authed_client_admin, other_admin_user
):
    sess = _seed_session_with_assistant(db_session, other_admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/rating", json={"value": 4}
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — add to `router.py`:

```python
@router.post(
    "/sessions/{session_id}/rating",
    response_model=SessionRatingRead,
    status_code=201,
)
def post_session_rating(
    session_id: UUID,
    body: SessionRatingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    sess = _load_owned_session(db, session_id, current_user)
    n_assistant = (
        db.query(models.CopilotMessage)
        .filter(
            models.CopilotMessage.session_id == sess.id,
            models.CopilotMessage.role == models.CopilotMessageRole.assistant,
        )
        .count()
    )
    if n_assistant == 0:
        raise HTTPException(status_code=404, detail="Not Found")
    existing = (
        db.query(models.CopilotSessionRating)
        .filter_by(session_id=sess.id, user_id=current_user.id)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already rated")
    row = models.CopilotSessionRating(
        session_id=sess.id,
        user_id=current_user.id,
        value=body.value,
        comment=body.comment or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "copilot_session_rated session_id=%s user_id=%s role=%s value=%s "
        "has_comment=%s n_messages=%s",
        sess.id, current_user.id, current_user.role.value, row.value,
        bool(row.comment), n_assistant,
    )
    return SessionRatingRead(
        session_id=str(sess.id),
        value=row.value,
        comment=row.comment,
        created_at=row.created_at,
    )
```

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/router.py \
        backend/tests/copilot/api/test_session_rating_endpoint.py
git commit -m "$(cat <<'EOF'
feat(35-01-B): POST /sessions/{id}/rating insert-only with 409 on dup
EOF
)"
```

### Task 7 (35-01-B-Task-04): `GET /admin/feedback/weekly`

**Files:**
- Modify: `backend/app/copilot/router.py`
- Create: `backend/tests/copilot/api/test_feedback_admin_endpoints.py`

- [ ] **Step 1: Write failing test (weekly endpoint only — bottom-messages comes in Task 8)**

```python
# backend/tests/copilot/api/test_feedback_admin_endpoints.py
import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def test_weekly_default_returns_12_weeks(authed_client_admin):
    resp = authed_client_admin.get("/api/v1/copilot/admin/feedback/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert "weeks" in body
    assert len(body["weeks"]) == 12


def test_weekly_query_param_bounded(authed_client_admin):
    resp = authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/weekly?weeks=4"
    )
    assert resp.status_code == 200
    assert len(resp.json()["weeks"]) == 4


def test_weekly_rejects_out_of_range(authed_client_admin):
    assert authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/weekly?weeks=0"
    ).status_code == 422
    assert authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/weekly?weeks=99"
    ).status_code == 422


def test_weekly_404_when_copilot_disabled(authed_client_admin, monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", False)
    resp = authed_client_admin.get("/api/v1/copilot/admin/feedback/weekly")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — add to `router.py` (depends on `feedback.aggregates.weekly_rollup` which lands in Task 10 — we implement the endpoint shell here with an inline placeholder; the real SQL arrives in 35-01-C and we DO NOT recommit then):

Use this implementation now and back it with the real aggregator in Task 10:

```python
from fastapi import Query

from .feedback.aggregates import bottom_messages, weekly_rollup


@router.get(
    "/admin/feedback/weekly", response_model=WeeklyFeedbackResponse,
)
def get_admin_feedback_weekly(
    weeks: int = Query(12, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    return WeeklyFeedbackResponse(weeks=weekly_rollup(db, weeks=weeks))
```

Because `feedback.aggregates` does not exist yet, this commit will fail import. **Stub it now** by creating `backend/app/copilot/feedback/__init__.py` (empty) and `backend/app/copilot/feedback/aggregates.py` with:

```python
"""Phase 35-01: feedback aggregates. Implementations land in 35-01-C tasks."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def weekly_rollup(db: Session, *, weeks: int) -> list[dict[str, Any]]:
    raise NotImplementedError("implemented in 35-01-C Task 10")


def bottom_messages(db: Session, *, limit: int) -> list[dict[str, Any]]:
    raise NotImplementedError("implemented in 35-01-C Task 11")
```

With the stub in place, the import resolves and 3 of the 4 tests pass (the empty-data assertion fails until Task 10). For now, **adjust the tests** by marking the three data-driven tests with `pytest.mark.xfail(reason="aggregator stub — completed in 35-01-C Task 10", strict=True)`. Remove the xfail mark in Task 10.

- [ ] **Step 4: Run** — the 422 + 404 tests pass; the three xfail tests xfail.

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/router.py \
        backend/app/copilot/feedback/__init__.py \
        backend/app/copilot/feedback/aggregates.py \
        backend/tests/copilot/api/test_feedback_admin_endpoints.py
git commit -m "$(cat <<'EOF'
feat(35-01-B): GET /admin/feedback/weekly endpoint shell + aggregator stub
EOF
)"
```

**Plan vs reality note:** The endpoint-before-aggregator order is deliberate — it lets the router-level tests stage first and forces the aggregator surface to be designed against a real consumer. If you prefer aggregator-first, swap T7+T8 with T10+T11. Net commit count is the same.

### Task 8 (35-01-B-Task-05): `GET /admin/feedback/bottom-messages`

**Files:**
- Modify: `backend/app/copilot/router.py`
- Modify: `backend/tests/copilot/api/test_feedback_admin_endpoints.py`

- [ ] **Step 1: Append failing tests**

```python
def test_bottom_messages_default_limit_20(authed_client_admin):
    resp = authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/bottom-messages"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "messages" in body
    assert isinstance(body["messages"], list)


def test_bottom_messages_limit_bounds(authed_client_admin):
    assert authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/bottom-messages?limit=0"
    ).status_code == 422
    assert authed_client_admin.get(
        "/api/v1/copilot/admin/feedback/bottom-messages?limit=200"
    ).status_code == 422
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — add to `router.py`:

```python
@router.get(
    "/admin/feedback/bottom-messages", response_model=BottomMessagesResponse,
)
def get_admin_feedback_bottom_messages(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_flag_on()
    _require_admin_or_organizer(current_user)
    return BottomMessagesResponse(messages=bottom_messages(db, limit=limit))
```

Mark the default-limit test with `pytest.mark.xfail(reason="aggregator stub", strict=True)` for now — it'll pass once Task 11 lands.

- [ ] **Step 4: Run, expect pass for the 422 tests; xfail for the data test.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/router.py \
        backend/tests/copilot/api/test_feedback_admin_endpoints.py
git commit -m "$(cat <<'EOF'
feat(35-01-B): GET /admin/feedback/bottom-messages endpoint shell
EOF
)"
```

### Task 9 (35-01-B-Task-06): Sub-phase 35-01-B docs

**Files:**
- Create: `docs/documentation/35-01-human-feedback/02-endpoints.md`
- Create: `docs/learning/35-01-human-feedback/02-endpoints.md`

- [ ] **Step 1: Documentation (≥80 lines)** — full contract of each of the four endpoints, request/response shapes, 422 vs 404 vs 409 semantics, the upsert vs insert-only difference, why both admin endpoints share `_require_admin_or_organizer` (Section 5 of spec), Query parameter bounds.

- [ ] **Step 2: Learning (≥80 lines)** — teaching note on "validators that span multiple fields" — when to use `model_validator(mode="after")` vs per-field `field_validator`, with a worked example of why the spec's required-comment rule cannot be expressed as a `field_validator`.

- [ ] **Step 3: Commit**

```bash
git add docs/documentation/35-01-human-feedback/02-endpoints.md \
        docs/learning/35-01-human-feedback/02-endpoints.md
git commit -m "$(cat <<'EOF'
docs(35-01-B): endpoints — documentation + learning
EOF
)"
```

---

## 35-01-C — Aggregates + bottom-quartile SQL

### Task 10 (35-01-C-Task-01): `weekly_rollup` — ISO-week date_trunc

**Files:**
- Modify: `backend/app/copilot/feedback/aggregates.py`
- Create: `backend/tests/copilot/feedback/test_aggregates.py`
- Modify: `backend/tests/copilot/api/test_feedback_admin_endpoints.py` (remove xfail marks)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/feedback/test_aggregates.py
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from app.copilot.feedback.aggregates import weekly_rollup


def _seed_msg_rating(db_session, user, sess, value, comment=None, created_at=None):
    msg = models.CopilotMessage(
        id=uuid.uuid4(), session_id=sess.id,
        role=models.CopilotMessageRole.assistant, content="x",
    )
    db_session.add(msg)
    db_session.flush()
    r = models.CopilotMessageRating(
        message_id=msg.id, user_id=user.id, value=value, comment=comment,
    )
    if created_at is not None:
        r.created_at = created_at
        r.updated_at = created_at
    db_session.add(r)
    db_session.commit()
    return msg, r


def _seed_sess(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id="openrouter/auto",
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def test_weekly_rollup_empty_returns_n_rows_with_nulls(db_session):
    rows = weekly_rollup(db_session, weeks=4)
    assert len(rows) == 4
    for r in rows:
        assert r["n_messages"] == 0
        assert r["n_sessions"] == 0
        assert r["thumbs_up_rate"] is None
        assert r["session_rating_avg"] is None
        assert r["iso_week"].startswith("20") and "-W" in r["iso_week"]


def test_weekly_rollup_groups_by_iso_week(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    now = datetime.now(timezone.utc)
    last_week = now - timedelta(days=7)
    _seed_msg_rating(db_session, admin_user, sess, "up", created_at=now)
    _seed_msg_rating(db_session, admin_user, sess, "up", created_at=now)
    _seed_msg_rating(
        db_session, admin_user, sess, "down", comment="x", created_at=now
    )
    _seed_msg_rating(db_session, admin_user, sess, "up", created_at=last_week)
    rows = weekly_rollup(db_session, weeks=4)
    rows_with_data = [r for r in rows if r["n_messages"] > 0]
    assert len(rows_with_data) == 2
    current = next(r for r in rows_with_data if r["n_messages"] == 3)
    assert current["thumbs_up_rate"] == 2 / 3


def test_weekly_rollup_session_rating_avg(db_session, admin_user):
    now = datetime.now(timezone.utc)
    for v in (5, 5, 3):
        sess = _seed_sess(db_session, admin_user)
        db_session.add(
            models.CopilotMessage(
                id=uuid.uuid4(), session_id=sess.id,
                role=models.CopilotMessageRole.assistant, content="x",
            )
        )
        db_session.flush()
        r = models.CopilotSessionRating(
            session_id=sess.id, user_id=admin_user.id, value=v,
        )
        r.created_at = now
        db_session.add(r)
        db_session.commit()
    rows = weekly_rollup(db_session, weeks=4)
    current = next(r for r in rows if r["n_sessions"] > 0)
    assert current["n_sessions"] == 3
    assert abs(current["session_rating_avg"] - (13 / 3)) < 0.01
```

- [ ] **Step 2: Run, expect fail (NotImplementedError)**

- [ ] **Step 3: Implement** — replace the `weekly_rollup` stub in `aggregates.py`:

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text as sa_text

from app import models


def _iso_week_label(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y:04d}-W{w:02d}"


def weekly_rollup(db: Session, *, weeks: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    # build the N-week skeleton (most-recent-first) using Postgres
    # date_trunc('week', now()) which is Monday-start (ISO).
    skeleton: list[dict[str, Any]] = []
    for i in range(weeks):
        week_start = (now - timedelta(weeks=i))
        skeleton.append(
            {
                "iso_week": _iso_week_label(week_start),
                "thumbs_up_rate": None,
                "session_rating_avg": None,
                "n_messages": 0,
                "n_sessions": 0,
            }
        )
    skeleton.reverse()  # oldest first

    cutoff = now - timedelta(weeks=weeks)

    msg_rows = db.execute(
        sa_text(
            """
            SELECT
              to_char(date_trunc('week', created_at), 'IYYY-"W"IW') AS iso_week,
              COUNT(*) FILTER (WHERE value = 'up') AS n_up,
              COUNT(*) FILTER (WHERE value IN ('up','down')) AS n_total
            FROM copilot_message_ratings
            WHERE created_at >= :cutoff
            GROUP BY 1
            """
        ),
        {"cutoff": cutoff},
    ).all()
    msg_by_week = {r.iso_week: (r.n_up, r.n_total) for r in msg_rows}

    sess_rows = db.execute(
        sa_text(
            """
            SELECT
              to_char(date_trunc('week', created_at), 'IYYY-"W"IW') AS iso_week,
              AVG(value)::float AS avg_value,
              COUNT(*) AS n_sessions
            FROM copilot_session_ratings
            WHERE created_at >= :cutoff
            GROUP BY 1
            """
        ),
        {"cutoff": cutoff},
    ).all()
    sess_by_week = {r.iso_week: (r.avg_value, r.n_sessions) for r in sess_rows}

    for entry in skeleton:
        wk = entry["iso_week"]
        if wk in msg_by_week:
            n_up, n_total = msg_by_week[wk]
            entry["n_messages"] = n_total
            entry["thumbs_up_rate"] = (n_up / n_total) if n_total else None
        if wk in sess_by_week:
            avg_value, n_sessions = sess_by_week[wk]
            entry["n_sessions"] = n_sessions
            entry["session_rating_avg"] = avg_value
    return skeleton
```

Also remove `pytest.mark.xfail(...)` from the three weekly tests in `test_feedback_admin_endpoints.py`.

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/feedback/aggregates.py \
        backend/tests/copilot/feedback/test_aggregates.py \
        backend/tests/copilot/api/test_feedback_admin_endpoints.py
git commit -m "$(cat <<'EOF'
feat(35-01-C): weekly_rollup with date_trunc + null-rate handling
EOF
)"
```

**Plan vs reality note:** The Postgres format string `'IYYY-"W"IW'` uses ISO-year (`IYYY`) and ISO-week (`IW`). The double-quoted `"W"` literal is required; SQLAlchemy's bind escape will pass it through. The Python `_iso_week_label` helper uses Python's `datetime.isocalendar()` which matches Postgres ISO semantics — verified against the Phase 34 idle-sweep test pattern.

### Task 11 (35-01-C-Task-02): `bottom_messages` — partial-index drill-down

**Files:**
- Modify: `backend/app/copilot/feedback/aggregates.py`
- Modify: `backend/tests/copilot/feedback/test_aggregates.py`
- Modify: `backend/tests/copilot/api/test_feedback_admin_endpoints.py` (remove last xfail mark)

- [ ] **Step 1: Append failing tests**

```python
from app.copilot.feedback.aggregates import bottom_messages


def test_bottom_messages_only_returns_downs(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    _seed_msg_rating(db_session, admin_user, sess, "up")
    _seed_msg_rating(db_session, admin_user, sess, "down", comment="bad week")
    out = bottom_messages(db_session, limit=10)
    assert len(out) == 1
    assert out[0]["comment"] == "bad week"


def test_bottom_messages_newest_first(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    older = datetime.now(timezone.utc) - timedelta(days=2)
    newer = datetime.now(timezone.utc)
    _seed_msg_rating(
        db_session, admin_user, sess, "down", comment="A", created_at=older
    )
    _seed_msg_rating(
        db_session, admin_user, sess, "down", comment="B", created_at=newer
    )
    out = bottom_messages(db_session, limit=10)
    assert [m["comment"] for m in out] == ["B", "A"]


def test_bottom_messages_includes_prior_user_text(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    user_msg = models.CopilotMessage(
        id=uuid.uuid4(), session_id=sess.id,
        role=models.CopilotMessageRole.user, content="prior question",
    )
    db_session.add(user_msg)
    db_session.flush()
    assistant_msg = models.CopilotMessage(
        id=uuid.uuid4(), session_id=sess.id,
        role=models.CopilotMessageRole.assistant, content="reply",
    )
    db_session.add(assistant_msg)
    db_session.flush()
    db_session.add(
        models.CopilotMessageRating(
            message_id=assistant_msg.id, user_id=admin_user.id,
            value="down", comment="bad",
        )
    )
    db_session.commit()
    out = bottom_messages(db_session, limit=10)
    assert out[0]["prior_user_text"] == "prior question"
    assert out[0]["assistant_text"] == "reply"
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — replace the `bottom_messages` stub:

```python
def bottom_messages(db: Session, *, limit: int) -> list[dict[str, Any]]:
    rows = db.execute(
        sa_text(
            """
            SELECT
              r.id          AS rating_id,
              r.message_id  AS message_id,
              r.comment     AS comment,
              r.created_at  AS rated_at,
              m.content     AS assistant_text,
              m.session_id  AS session_id,
              s.model_id    AS model_id,
              u.role        AS rater_role,
              (
                SELECT prev.content
                FROM copilot_messages prev
                WHERE prev.session_id = m.session_id
                  AND prev.role = 'user'
                  AND prev.created_at < m.created_at
                ORDER BY prev.created_at DESC
                LIMIT 1
              ) AS prior_user_text
            FROM copilot_message_ratings r
            JOIN copilot_messages m  ON m.id = r.message_id
            JOIN copilot_sessions s  ON s.id = m.session_id
            JOIN users u             ON u.id = r.user_id
            WHERE r.value = 'down'
            ORDER BY r.created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).all()
    return [
        {
            "message_id": str(r.message_id),
            "session_id": str(r.session_id),
            "model_id": r.model_id,
            "rater_role": (r.rater_role.value if hasattr(r.rater_role, "value")
                           else str(r.rater_role)),
            "rated_at": r.rated_at,
            "comment": r.comment,
            "assistant_text": r.assistant_text or "",
            "prior_user_text": r.prior_user_text,
        }
        for r in rows
    ]
```

Also remove the last `xfail` mark in `test_feedback_admin_endpoints.py`.

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/feedback/aggregates.py \
        backend/tests/copilot/feedback/test_aggregates.py \
        backend/tests/copilot/api/test_feedback_admin_endpoints.py
git commit -m "$(cat <<'EOF'
feat(35-01-C): bottom_messages drill-down with prior-user-turn join
EOF
)"
```

**Plan vs reality note:** The `r.rater_role` cast is defensive — `models.UserRole` may come back as an enum or a raw string depending on SQLAlchemy's enum reflection. Phase 33 hit this exact issue (see commit history around 32-08). The `hasattr` guard handles both.

### Task 12 (35-01-C-Task-03): Sub-phase 35-01-C docs + CI gate

**Files:**
- Create: `docs/documentation/35-01-human-feedback/03-aggregates.md`
- Create: `docs/learning/35-01-human-feedback/03-aggregates.md`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Documentation (≥80 lines)** — the two SQL queries, why ISO week (`IYYY-"W"IW` format), why the partial index `WHERE value = 'down'` powers the drill-down, the correlated subquery for `prior_user_text` and its cost characteristics on small data, why we do not paginate (limit-bounded already).

- [ ] **Step 2: Learning (≥80 lines)** — teaching note on "rolling weekly aggregates: SQL date_trunc vs Python pandas vs precomputed table" — with worked example showing why date_trunc is the right answer for a 12-week window at our data size.

- [ ] **Step 3: Add CI coverage gate.** Edit `.github/workflows/ci.yml` and insert (after the `app.corpus` gate, around line 173):

```yaml
      - name: Coverage gate — app.copilot.feedback
        env:
          TEST_DATABASE_URL: postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs
        run: |
          cd backend
          pytest -o addopts="" --cov=app.copilot.feedback --cov-branch --cov-fail-under=95 --cov-report=term-missing tests/
```

- [ ] **Step 4: Commit**

```bash
git add docs/documentation/35-01-human-feedback/03-aggregates.md \
        docs/learning/35-01-human-feedback/03-aggregates.md \
        .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
docs(35-01-C): aggregates + CI gate for app.copilot.feedback at 95%
EOF
)"
```

---

## 35-01-D — SSE `message_persisted` event + frontend wiring

### Task 13 (35-01-D-Task-01): Backend emits `event: message_persisted`

**Files:**
- Modify: `backend/app/copilot/router.py`
- Create: `backend/tests/copilot/api/test_message_persisted_sse.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/copilot/api/test_message_persisted_sse.py
import uuid

import pytest

from app import models
from app.config import settings


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id="openrouter/auto",
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def test_messages_endpoint_emits_message_persisted_event(
    db_session, authed_client_admin, admin_user, monkeypatch
):
    from app.copilot import router as copilot_router

    class _StubLLM:
        def chat(self, **_kw):
            return {"final_answer": "hi back"}

    monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: _StubLLM())
    sess = _seed_session(db_session, admin_user)
    resp = authed_client_admin.post(
        f"/api/v1/copilot/sessions/{sess.id}/messages",
        json={"content": "hi"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "event: message_persisted" in body
    # Each persisted event includes a uuid id and role="assistant"
    assert '"role": "assistant"' in body or '"role":"assistant"' in body
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Implement** — locate both assistant-persist sites in `router.py` (around lines 597–607 and 654–675 per current code). After each `db.refresh(assistant_msg)` and BEFORE the `event: done` yield, insert:

```python
        yield _sse_format(
            "message_persisted",
            json.dumps({"id": str(assistant_msg.id), "role": "assistant"}),
        )
```

This is strictly additive — the Phase 30 invariant test (`test_existing_event_shapes_unchanged`) only freezes `token`/`done`/`error`, so a new event name is allowed.

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/copilot/router.py \
        backend/tests/copilot/api/test_message_persisted_sse.py
git commit -m "$(cat <<'EOF'
feat(35-01-D): emit SSE message_persisted event after assistant persist
EOF
)"
```

### Task 14 (35-01-D-Task-02): `useCopilotStream` captures `message_persisted`

**Files:**
- Modify: `frontend/src/copilot/useCopilotStream.js`

- [ ] **Step 1: Extend the hook.** Add an `onMessagePersisted` callback to the destructured options and handle the new event inside `parseSseChunk` consumption loop:

```js
// signature change
export function useCopilotStream(
  sessionId,
  {
    onDone,
    onError,
    onToolCall,
    onToolResult,
    onConfirmationRequest,
    onFinalAnswer,
    onMessagePersisted,
  } = {},
) {
```

Inside the `for (const ev of events)` loop, add a new branch alongside the others:

```js
            } else if (ev.event === "message_persisted") {
              try {
                onMessagePersisted?.(JSON.parse(ev.data));
              } catch {
                // malformed — skip
              }
            }
```

Also add `onMessagePersisted` to the dependency array of the `useCallback`.

- [ ] **Step 2: No new vitest in this task** — the wiring is exercised in Task 15 + Task 16. (We are not adding `useCopilotStream` vitest infrastructure for this single field — the existing tests rely on the integration with `CopilotDrawer`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/copilot/useCopilotStream.js
git commit -m "$(cat <<'EOF'
feat(35-01-D): useCopilotStream captures message_persisted SSE event
EOF
)"
```

### Task 15 (35-01-D-Task-03): `CopilotDrawer` threads id into each bubble

**Files:**
- Modify: `frontend/src/copilot/CopilotDrawer.jsx`

- [ ] **Step 1: Wire the id.** Pass `onMessagePersisted` to `useCopilotStream`. In the existing `useCopilotStream` setup (around line 48), add:

```jsx
  const { send, streaming, partial, error } = useCopilotStream(sessionId, {
    onDone: handleDone,
    onError: handleError,
    onToolCall,
    onToolResult,
    onConfirmationRequest,
    onFinalAnswer,
    onMessagePersisted: ({ id, role }) => {
      if (role !== "assistant") return;
      // Attach the id to the most-recent assistant placeholder. The
      // bubble was appended optimistically in onSubmit/handleDone; we
      // mutate the last assistant row's `id` field.
      setMessages((m) => {
        const next = [...m];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === "assistant" && !next[i].id) {
            next[i] = { ...next[i], id };
            return next;
          }
        }
        return next;
      });
    },
  });
```

If the `handleDone` already appends the assistant message into state, ensure it does NOT also set the `id` — `message_persisted` arrives before `done`, so the `id` is reliably set first. If the existing code path constructs the assistant bubble inside `onDone` only, restructure so the placeholder is appended at stream start (already the case per current `setMessages`-on-final-answer code path). Inspect the current file before mutating; the exact line numbers will shift.

- [ ] **Step 2: No new test** — exercised by `MessageRatingButtons` integration test in Task 17. Manual smoke: open the drawer, send a message, dev-tools inspect: each assistant bubble in `messages` now has an `id` field.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/copilot/CopilotDrawer.jsx
git commit -m "$(cat <<'EOF'
feat(35-01-D): thread assistant message id into each rendered bubble
EOF
)"
```

**Plan vs reality note:** The existing drawer appends the assistant message inside an `onFinalAnswer` callback (line ~85ish). `message_persisted` fires AFTER `final_answer` because the persist happens after the final-answer event in `router.py`. That ordering is what makes the "find last assistant without id and patch in" loop safe. If reorder happens later, this code becomes wrong — flag in the SUMMARY.

### Task 16 (35-01-D-Task-04): Sub-phase 35-01-D docs

**Files:**
- Create: `docs/documentation/35-01-human-feedback/04-sse-wiring.md`
- Create: `docs/learning/35-01-human-feedback/04-sse-wiring.md`

- [ ] **Step 1: Documentation (≥80 lines)** — the new SSE event shape, its position in the event ordering (after `final_answer`, before `done`), why we did not use `done.message_id` (which is already there) — answer: we want to surface the id BEFORE the close marker so optimistic UI can attach immediately, and rating buttons must render on the bubble before the user can scroll past, OR we want symmetry with future events that emit mid-stream (Phase 35-02 multi-model A/B).

- [ ] **Step 2: Learning (≥80 lines)** — teaching note on "additive SSE protocol changes" — why adding a new event name is safe, why mutating an existing event payload is not, with a counter-example showing how a payload addition broke a downstream parser in Phase 32.

- [ ] **Step 3: Commit**

```bash
git add docs/documentation/35-01-human-feedback/04-sse-wiring.md \
        docs/learning/35-01-human-feedback/04-sse-wiring.md
git commit -m "$(cat <<'EOF'
docs(35-01-D): SSE wiring — documentation + learning
EOF
)"
```

---

## 35-01-E — Frontend components

### Task 17 (35-01-E-Task-01): `MessageRatingButtons.jsx`

**Files:**
- Create: `frontend/src/copilot/MessageRatingButtons.jsx`
- Create: `frontend/src/copilot/__tests__/MessageRatingButtons.test.jsx`

- [ ] **Step 1: Write the component**

```jsx
// frontend/src/copilot/MessageRatingButtons.jsx
import React from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

export default function MessageRatingButtons({ messageId, fetcher }) {
  const f = fetcher || window.fetch.bind(window);
  const [state, setState] = React.useState({
    active: null, // 'up' | 'down' | null
    showComment: false,
    comment: "",
    submitting: false,
    error: null,
  });

  if (!messageId) return null;

  async function submit(value, comment) {
    setState((s) => ({ ...s, submitting: true, error: null }));
    try {
      const tok = authStorage.getToken();
      const resp = await f(`${COPILOT_BASE}/messages/${messageId}/rating`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ value, ...(comment ? { comment } : {}) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setState({
        active: value,
        showComment: false,
        comment: "",
        submitting: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({ ...s, submitting: false, error: String(err) }));
    }
  }

  function onUp() {
    submit("up", null);
  }

  function onDown() {
    setState((s) => ({ ...s, showComment: true, active: null }));
  }

  function onSubmitDown() {
    if (!state.comment.trim()) return;
    submit("down", state.comment.trim());
  }

  return (
    <div className="flex flex-col gap-1 mt-1 pl-1">
      <div className="flex gap-2">
        <button
          type="button"
          aria-label="Thumbs up"
          aria-pressed={state.active === "up"}
          onClick={onUp}
          disabled={state.submitting}
          className={`p-1 rounded ${state.active === "up" ? "bg-green-100" : "hover:bg-gray-100"}`}
        >
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button
          type="button"
          aria-label="Thumbs down"
          aria-pressed={state.active === "down"}
          onClick={onDown}
          disabled={state.submitting}
          className={`p-1 rounded ${state.active === "down" ? "bg-red-100" : "hover:bg-gray-100"}`}
        >
          <ThumbsDown className="w-4 h-4" />
        </button>
      </div>
      {state.showComment && (
        <div className="flex flex-col gap-1 mt-1">
          <textarea
            aria-label="Comment for thumbs-down rating"
            value={state.comment}
            onChange={(e) => setState((s) => ({ ...s, comment: e.target.value }))}
            placeholder="Tell us what went wrong (required)"
            className="border rounded px-2 py-1 text-xs"
            rows={2}
            maxLength={1000}
          />
          <button
            type="button"
            onClick={onSubmitDown}
            disabled={!state.comment.trim() || state.submitting}
            className="self-end px-2 py-1 rounded bg-indigo-600 text-white text-xs disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      )}
      {state.error && (
        <p role="alert" className="text-xs text-red-600">{state.error}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the vitest**

```jsx
// frontend/src/copilot/__tests__/MessageRatingButtons.test.jsx
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MessageRatingButtons from "../MessageRatingButtons";

function makeFetch(handler) {
  return vi.fn(async (url, opts = {}) => handler(url, opts));
}

describe("MessageRatingButtons", () => {
  it("renders nothing without a messageId", () => {
    const { container } = render(<MessageRatingButtons />);
    expect(container.firstChild).toBeNull();
  });

  it("posts immediately on thumbs-up", async () => {
    const fetcher = makeFetch(async (url, opts) => {
      expect(url).toMatch(/\/messages\/m1\/rating$/);
      expect(JSON.parse(opts.body)).toEqual({ value: "up" });
      return { ok: true, status: 200, json: async () => ({}) };
    });
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs up"));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  });

  it("reveals textarea on thumbs-down, blocks submit until non-empty", async () => {
    const fetcher = makeFetch(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs down"));
    expect(fetcher).not.toHaveBeenCalled();
    const submit = screen.getByRole("button", { name: /submit/i });
    expect(submit).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText(/Comment for thumbs-down/i),
      { target: { value: "wrong week" } },
    );
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const [, opts] = fetcher.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ value: "down", comment: "wrong week" });
  });

  it("switching from up to down clears prior active state", async () => {
    const fetcher = makeFetch(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    render(<MessageRatingButtons messageId="m1" fetcher={fetcher} />);
    fireEvent.click(screen.getByLabelText("Thumbs up"));
    await waitFor(() =>
      expect(screen.getByLabelText("Thumbs up")).toHaveAttribute("aria-pressed", "true"),
    );
    fireEvent.click(screen.getByLabelText("Thumbs down"));
    expect(screen.getByLabelText("Thumbs up")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("Thumbs down")).toHaveAttribute("aria-pressed", "false");
  });
});
```

- [ ] **Step 3: Run**

```bash
cd frontend && npm run test -- --run src/copilot/__tests__/MessageRatingButtons.test.jsx
```

- [ ] **Step 4: Mount in `CopilotDrawer.jsx`** — inside the `messages.map((m, i) => ...)` loop, after the existing `<MessageBubble />` and citation row, add (only for assistant rows that have an `id`):

```jsx
              {m.role === "assistant" && m.id && (
                <MessageRatingButtons messageId={m.id} />
              )}
```

Add the import at the top: `import MessageRatingButtons from "./MessageRatingButtons";`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/copilot/MessageRatingButtons.jsx \
        frontend/src/copilot/__tests__/MessageRatingButtons.test.jsx \
        frontend/src/copilot/CopilotDrawer.jsx
git commit -m "$(cat <<'EOF'
feat(35-01-E): MessageRatingButtons component + drawer mount
EOF
)"
```

### Task 18 (35-01-E-Task-02): `SessionRatingModal.jsx` + drawer close intercept

**Files:**
- Create: `frontend/src/copilot/SessionRatingModal.jsx`
- Create: `frontend/src/copilot/__tests__/SessionRatingModal.test.jsx`
- Modify: `frontend/src/copilot/CopilotDrawer.jsx`

- [ ] **Step 1: Write the component**

```jsx
// frontend/src/copilot/SessionRatingModal.jsx
import React from "react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

export default function SessionRatingModal({
  sessionId,
  open,
  onCancel,
  onSubmitted,
  fetcher,
}) {
  const f = fetcher || window.fetch.bind(window);
  const [value, setValue] = React.useState(0);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState(null);

  if (!open) return null;
  const commentRequired = value > 0 && value <= 2;
  const canSubmit =
    value >= 1 && value <= 5 && (!commentRequired || comment.trim().length > 0);

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const tok = authStorage.getToken();
      const resp = await f(`${COPILOT_BASE}/sessions/${sessionId}/rating`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({
          value,
          ...(comment.trim() ? { comment: comment.trim() } : {}),
        }),
      });
      if (!resp.ok && resp.status !== 201) throw new Error(`HTTP ${resp.status}`);
      onSubmitted?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Rate this session"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
    >
      <div className="bg-white rounded-lg shadow-lg p-6 w-[24rem]">
        <h3 className="font-semibold mb-2">How did this session go?</h3>
        <div className="flex gap-2 mb-3" role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={value === n}
              aria-label={`${n} star${n === 1 ? "" : "s"}`}
              onClick={() => setValue(n)}
              className={`w-10 h-10 rounded text-lg ${value >= n ? "bg-yellow-300" : "bg-gray-100"}`}
            >
              ★
            </button>
          ))}
        </div>
        {commentRequired && (
          <p className="text-xs text-red-600 mb-1">Comment required for 2 stars or fewer.</p>
        )}
        <textarea
          aria-label="Session rating comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={commentRequired ? "Tell us what went wrong (required)" : "Optional comment"}
          className="w-full border rounded px-2 py-1 text-sm mb-3"
          rows={3}
          maxLength={1000}
        />
        {error && <p role="alert" className="text-xs text-red-600 mb-2">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="px-3 py-1 rounded border text-sm"
          >
            Cancel close
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || submitting}
            className="px-3 py-1 rounded bg-indigo-600 text-white text-sm disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write the vitest**

```jsx
// frontend/src/copilot/__tests__/SessionRatingModal.test.jsx
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SessionRatingModal from "../SessionRatingModal";

function makeFetch(handler) {
  return vi.fn(async (url, opts = {}) => handler(url, opts));
}

describe("SessionRatingModal", () => {
  it("does not render when open is false", () => {
    const { container } = render(
      <SessionRatingModal sessionId="s1" open={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("Submit is disabled until a value is chosen", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });

  it("requires comment when value ≤2", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    fireEvent.click(screen.getByLabelText("2 stars"));
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Session rating comment"), {
      target: { value: "bad" },
    });
    expect(screen.getByRole("button", { name: /submit/i })).not.toBeDisabled();
  });

  it("submits without comment when value ≥3", async () => {
    const fetcher = makeFetch(async (url, opts) => {
      expect(url).toMatch(/\/sessions\/s1\/rating$/);
      expect(JSON.parse(opts.body)).toEqual({ value: 4 });
      return { ok: true, status: 201, json: async () => ({}) };
    });
    const onSubmitted = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onSubmitted={onSubmitted}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByLabelText("4 stars"));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
  });

  it("Cancel close invokes onCancel without posting", () => {
    const fetcher = vi.fn();
    const onCancel = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onCancel={onCancel}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel close/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Wire into `CopilotDrawer.jsx`.** Replace the existing `onClose` close path:

```jsx
  const [ratingOpen, setRatingOpen] = React.useState(false);

  function requestClose() {
    const hasAssistant = messages.some((m) => m.role === "assistant");
    if (hasAssistant && sessionId) {
      setRatingOpen(true);
      return;
    }
    void closeAndDismiss();
  }

  async function closeAndDismiss() {
    setRatingOpen(false);
    try {
      const tok = authStorage.getToken();
      await fetch(`${COPILOT_BASE}/sessions/${sessionId}/close`, {
        method: "POST",
        credentials: "include",
        headers: tok ? { Authorization: `Bearer ${tok}` } : {},
      });
    } catch {
      // best-effort close — surface drawer dismissal regardless
    }
    onClose?.();
  }
```

Change every `onClick={onClose}` inside the drawer to `onClick={requestClose}` (the backdrop and the X button — both around lines 134 and 149).

At the bottom of the drawer JSX, mount the modal:

```jsx
      {sessionId && (
        <SessionRatingModal
          sessionId={sessionId}
          open={ratingOpen}
          onCancel={() => setRatingOpen(false)}
          onSubmitted={closeAndDismiss}
        />
      )}
```

Add the import: `import SessionRatingModal from "./SessionRatingModal";` and `import authStorage from "../lib/authStorage";` if not present.

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npm run test -- --run src/copilot/__tests__/SessionRatingModal.test.jsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/copilot/SessionRatingModal.jsx \
        frontend/src/copilot/__tests__/SessionRatingModal.test.jsx \
        frontend/src/copilot/CopilotDrawer.jsx
git commit -m "$(cat <<'EOF'
feat(35-01-E): SessionRatingModal + drawer close-intercept wiring
EOF
)"
```

**Plan vs reality note:** The `POST /sessions/{id}/close` endpoint already exists (Phase 34). The rating modal is mounted at drawer level rather than at `App.jsx` because the drawer owns `sessionId`; lifting it higher would duplicate state.

### Task 19 (35-01-E-Task-03): `AdminCopilotFeedbackPage.jsx` + route + nav

**Files:**
- Create: `frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx`
- Create: `frontend/src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx`
- Modify: `frontend/src/pages/admin/AdminLayout.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Write the page**

```jsx
// frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx
import React from "react";
import authStorage from "../../lib/authStorage";
import { COPILOT_BASE } from "../../copilot/api";

export default function AdminCopilotFeedbackPage({ fetcher }) {
  const f = fetcher || window.fetch.bind(window);
  const [weekly, setWeekly] = React.useState(null);
  const [bottom, setBottom] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [expanded, setExpanded] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const tok = authStorage.getToken();
        const headers = tok ? { Authorization: `Bearer ${tok}` } : {};
        const [w, b] = await Promise.all([
          f(`${COPILOT_BASE}/admin/feedback/weekly`, { headers, credentials: "include" }),
          f(`${COPILOT_BASE}/admin/feedback/bottom-messages`, { headers, credentials: "include" }),
        ]);
        if (!w.ok) throw new Error(`weekly HTTP ${w.status}`);
        if (!b.ok) throw new Error(`bottom HTTP ${b.status}`);
        const wj = await w.json();
        const bj = await b.json();
        if (!cancelled) {
          setWeekly(wj.weeks || []);
          setBottom(bj.messages || []);
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [f]);

  if (error) return <p role="alert" className="text-red-600">{error}</p>;
  if (weekly === null || bottom === null) return <p>Loading…</p>;

  return (
    <div className="space-y-6">
      <section>
        <h2 className="font-semibold mb-2">Weekly feedback</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th>ISO week</th>
              <th>👍 rate</th>
              <th>Avg session rating</th>
              <th>Messages rated</th>
              <th>Sessions rated</th>
            </tr>
          </thead>
          <tbody>
            {weekly.map((w) => (
              <tr key={w.iso_week} className="border-b">
                <td>{w.iso_week}</td>
                <td>{w.thumbs_up_rate == null ? "—" : `${Math.round(w.thumbs_up_rate * 100)}%`}</td>
                <td>{w.session_rating_avg == null ? "—" : w.session_rating_avg.toFixed(2)}</td>
                <td>{w.n_messages}</td>
                <td>{w.n_sessions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2 className="font-semibold mb-2">Bottom-quartile messages</h2>
        {bottom.length === 0 ? (
          <p className="text-sm text-gray-500">No 👎 ratings yet.</p>
        ) : (
          <ul className="space-y-2">
            {bottom.map((m) => (
              <li key={m.message_id} className="border rounded p-2">
                <button
                  type="button"
                  onClick={() => setExpanded(expanded === m.message_id ? null : m.message_id)}
                  className="text-left text-sm w-full"
                >
                  <div className="font-mono text-xs text-gray-500">
                    {new Date(m.rated_at).toLocaleString()} — {m.rater_role} — model: {m.model_id || "?"}
                  </div>
                  <div className="text-sm italic">"{m.comment}"</div>
                </button>
                {expanded === m.message_id && (
                  <div className="mt-2 text-xs space-y-1">
                    {m.prior_user_text && (
                      <div><strong>Prior user turn:</strong> {m.prior_user_text}</div>
                    )}
                    <div><strong>Assistant reply:</strong> {m.assistant_text}</div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Write the vitest**

```jsx
// frontend/src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdminCopilotFeedbackPage from "../AdminCopilotFeedbackPage";

function makeFetch(routes) {
  return vi.fn(async (url) => {
    for (const key of Object.keys(routes)) {
      if (url.endsWith(key)) return routes[key]();
    }
    throw new Error(`unexpected ${url}`);
  });
}

describe("AdminCopilotFeedbackPage", () => {
  it("renders weekly table and bottom-quartile drill-down", async () => {
    const fetcher = makeFetch({
      "/admin/feedback/weekly": async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          weeks: [
            { iso_week: "2026-W21", thumbs_up_rate: 0.75, session_rating_avg: 4.2, n_messages: 8, n_sessions: 2 },
          ],
        }),
      }),
      "/admin/feedback/bottom-messages": async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          messages: [
            {
              message_id: "m1", session_id: "s1", model_id: "gpt-4o-mini",
              rater_role: "admin", rated_at: "2026-05-23T10:00:00Z",
              comment: "wrong week", assistant_text: "Week 22 next.",
              prior_user_text: "What week are we in?",
            },
          ],
        }),
      }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    await screen.findByText("2026-W21");
    expect(screen.getByText("75%")).toBeInTheDocument();
    fireEvent.click(screen.getByText(/wrong week/));
    expect(screen.getByText(/Week 22 next/)).toBeInTheDocument();
  });

  it("shows empty state when no thumbs-down ratings", async () => {
    const fetcher = makeFetch({
      "/admin/feedback/weekly": async () => ({
        ok: true, status: 200, json: async () => ({ weeks: [] }),
      }),
      "/admin/feedback/bottom-messages": async () => ({
        ok: true, status: 200, json: async () => ({ messages: [] }),
      }),
    });
    render(<AdminCopilotFeedbackPage fetcher={fetcher} />);
    await screen.findByText(/No 👎 ratings yet/);
  });
});
```

- [ ] **Step 3: Wire nav + route.** Edit `frontend/src/pages/admin/AdminLayout.jsx` and insert after the existing Reminders entry (around line 56):

```jsx
  {
    to: "/admin/copilot-feedback",
    label: "Copilot feedback",
    roles: ["admin", "organizer"],
  },
```

Edit `frontend/src/App.jsx`. Add the import:

```jsx
import AdminCopilotFeedbackPage from "./pages/admin/AdminCopilotFeedbackPage";
```

Add a `<Route>` inside the `admin` block (after `reminders`, around line 126):

```jsx
            <Route path="copilot-feedback" element={<AdminCopilotFeedbackPage />} />
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm run test -- --run src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/AdminCopilotFeedbackPage.jsx \
        frontend/src/pages/admin/__tests__/AdminCopilotFeedbackPage.test.jsx \
        frontend/src/pages/admin/AdminLayout.jsx \
        frontend/src/App.jsx
git commit -m "$(cat <<'EOF'
feat(35-01-E): AdminCopilotFeedbackPage + admin nav + route
EOF
)"
```

### Task 20 (35-01-E-Task-04): Sub-phase 35-01-E docs

**Files:**
- Create: `docs/documentation/35-01-human-feedback/05-frontend.md`
- Create: `docs/learning/35-01-human-feedback/05-frontend.md`

- [ ] **Step 1: Documentation (≥80 lines)** — each component's contract, props, fetcher injection, accessibility notes (aria-pressed for thumbs, aria-modal for the modal, role=radiogroup for stars), the close-intercept state machine inside the drawer, why no `beforeunload` (spec decision §13c).

- [ ] **Step 2: Learning (≥80 lines)** — teaching note on "coercive vs non-coercive feedback UX" — the spec deliberately makes the session-rating modal coercive (no skip button) because response rate is a paper metric. Worked example contrasts the trade-off vs the polite-but-skippable alternative.

- [ ] **Step 3: Commit**

```bash
git add docs/documentation/35-01-human-feedback/05-frontend.md \
        docs/learning/35-01-human-feedback/05-frontend.md
git commit -m "$(cat <<'EOF'
docs(35-01-E): frontend components — documentation + learning
EOF
)"
```

---

## 35-01-F — Closeout

### Task 21 (35-01-F-Task-01): Phase SUMMARY

**Files:**
- Create: `.planning/phases/35-01-human-feedback/SUMMARY.md`

- [ ] **Step 1: Write the SUMMARY** with sections: Goal, Sub-phases shipped, Files changed (categorised), Test counts (backend + vitest), Coverage on `app.copilot.feedback`, Deferred items (per spec §9), Known follow-ups for Phase 35-02 (adversarial sweep on comment text; multi-model A/B routing using rating ground truth).

- [ ] **Step 2: Commit**

```bash
git add .planning/phases/35-01-human-feedback/SUMMARY.md
git commit -m "$(cat <<'EOF'
docs(35-01-F): phase 35-01 SUMMARY
EOF
)"
```

### Task 22 (35-01-F-Task-02): ROADMAP + STATE refresh

**Files:**
- Modify: `.planning/ROADMAP.md`
- Modify: `.planning/STATE.md`

- [ ] **Step 1: Edit ROADMAP** — mark Phase 35-01 status `Complete (2026-05-23)`.
- [ ] **Step 2: Edit STATE** — set `current_phase` to the next 35-* entry; record `last_completed: 35-01-human-feedback`.
- [ ] **Step 3: Closeout docs** — also write `docs/documentation/35-01-human-feedback/06-closeout.md` and `docs/learning/35-01-human-feedback/06-closeout.md` (≥80 lines each): retrospective on the SSE-additive change, the per-package coverage gate experience, what we'd do differently in 35-02.

- [ ] **Step 4: Commit**

```bash
git add .planning/ROADMAP.md \
        .planning/STATE.md \
        docs/documentation/35-01-human-feedback/06-closeout.md \
        docs/learning/35-01-human-feedback/06-closeout.md
git commit -m "$(cat <<'EOF'
docs(35-01-F): roadmap + state + closeout — phase 35-01 complete
EOF
)"
```

### Task 23 (35-01-F-Task-03): Hand off PR to Andy

- [ ] **Step 1:** Do NOT open the PR from inside the agent loop. Print this instruction to the user:

> Phase 35-01 is ready for review. Run `gh pr create` (or `gsd-ship`) when ready. Branch: `feature/v1.4-phase-35-01-human-feedback`. Suggested title: `Phase 35-01 — Human-feedback collection`.

- [ ] **Step 2:** No commit.

---

## Verification checklist

Before declaring Phase 35-01 done:

- [ ] `docker compose run --rm migrate` applies 0023 cleanly from a fresh DB and rolls back cleanly.
- [ ] `pytest tests/copilot --no-cov` is fully green.
- [ ] `pytest -o addopts="" --cov=app.copilot.feedback --cov-branch --cov-fail-under=95 tests/` passes (matches the new CI gate).
- [ ] `cd frontend && npm run test -- --run` is fully green.
- [ ] Manual smoke: open a session, send two assistant turns, 👍 one and 👎 the other (entering a comment), close the drawer, submit a 1–5 rating with required comment when ≤2, confirm rows in both new tables, hit `/admin/copilot-feedback` and see the current ISO week populated.
- [ ] Manual smoke: hit `/admin/copilot-feedback` as an organizer account — same view should render.

---

## Cross-reference index

| Spec section | Plan task(s) |
|---|---|
| 4 — API contract | T5, T6, T7, T8 |
| 5 — authorisation | T5, T6, T7, T8 (`_require_admin_or_organizer` + `_load_owned_session/_load_owned_message`) |
| 6 — Pydantic validators | T4 |
| 7 — frontend components | T17, T18, T19 |
| 8 — test strategy | T4, T17, T18, T19 (unit + vitest); T10, T11 (aggregator) |
| 10 — migration | T1 |
| 11 — telemetry | T5, T6 (`logger.info` lines) |
| 12 — success criteria | Verification checklist |
| 13(a) — SSE `message_persisted` | T13, T14, T15 |
| 13(c) — no `beforeunload` | T18 (drawer intercept covers in-app close only) |
| 13(d) — 👎 persists only after comment submit | T17 |
| 13(e) — modal first, then close | T18 |
| 13(f) — ISO week via `date_trunc('week', ...)` | T10 |
| 13(g) — drill-down PII | T11 (assistant text already redacted at persist) |

End of plan.
