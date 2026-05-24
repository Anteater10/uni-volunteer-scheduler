"""Phase 35-01-C — aggregates (weekly_rollup + bottom_messages).

These tests exercise the SQL aggregators directly against the real
Postgres test database. ``admin_user`` is created locally via
``make_user`` since the codebase does not provide an ``admin_user``
fixture — see the plan's plan-vs-reality preamble.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.copilot.feedback.aggregates import weekly_rollup
from tests.fixtures.helpers import make_user


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db_session):
    """Local fixture — the codebase does not ship a shared admin_user."""
    admin = make_user(
        db_session,
        role=models.UserRole.admin,
        email=f"agg-admin-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.commit()
    return admin


def _seed_sess(db_session, user):
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


def _seed_msg_rating(
    db_session, user, sess, value, comment=None, created_at=None, *, role=None
):
    msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=sess.id,
        role=role or models.CopilotMessageRole.assistant,
        content="assistant reply",
    )
    db_session.add(msg)
    db_session.flush()
    r = models.CopilotMessageRating(
        message_id=msg.id, user_id=user.id, value=value, comment=comment
    )
    if created_at is not None:
        r.created_at = created_at
        r.updated_at = created_at
    db_session.add(r)
    db_session.commit()
    return msg, r


# ---------------------------------------------------------------------------
# weekly_rollup
# ---------------------------------------------------------------------------


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
    assert current["thumbs_up_rate"] == pytest.approx(2 / 3)
    other = next(r for r in rows_with_data if r["n_messages"] == 1)
    assert other["thumbs_up_rate"] == 1.0


def test_weekly_rollup_session_rating_avg(db_session, admin_user):
    now = datetime.now(timezone.utc)
    for v in (5, 5, 3):
        sess = _seed_sess(db_session, admin_user)
        r = models.CopilotSessionRating(
            session_id=sess.id, user_id=admin_user.id, value=v
        )
        r.created_at = now
        db_session.add(r)
        db_session.commit()
    rows = weekly_rollup(db_session, weeks=4)
    current = next(r for r in rows if r["n_sessions"] > 0)
    assert current["n_sessions"] == 3
    assert abs(current["session_rating_avg"] - (13 / 3)) < 0.01


def test_weekly_rollup_returns_weeks_oldest_first(db_session):
    rows = weekly_rollup(db_session, weeks=3)
    assert len(rows) == 3
    labels = [r["iso_week"] for r in rows]
    # oldest first → labels sorted ascending lexicographically (YYYY-Www)
    assert labels == sorted(labels)


def test_weekly_rollup_excludes_outside_window(db_session, admin_user):
    """A rating older than the window is not counted."""
    sess = _seed_sess(db_session, admin_user)
    very_old = datetime.now(timezone.utc) - timedelta(weeks=20)
    _seed_msg_rating(db_session, admin_user, sess, "up", created_at=very_old)
    rows = weekly_rollup(db_session, weeks=4)
    assert all(r["n_messages"] == 0 for r in rows)
