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
from app.copilot.feedback.aggregates import bottom_messages, weekly_rollup
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


# ---------------------------------------------------------------------------
# bottom_messages
# ---------------------------------------------------------------------------


def test_bottom_messages_only_returns_downs(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    _seed_msg_rating(db_session, admin_user, sess, "up")
    _seed_msg_rating(db_session, admin_user, sess, "down", comment="bad week")
    out = bottom_messages(db_session, limit=10)
    assert len(out) == 1
    assert out[0]["comment"] == "bad week"
    # ensure all required keys present
    expected_keys = {
        "message_id",
        "session_id",
        "model_id",
        "rater_role",
        "rated_at",
        "comment",
        "assistant_text",
        "prior_user_text",
    }
    assert expected_keys.issubset(out[0].keys())


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
        id=uuid.uuid4(),
        session_id=sess.id,
        role=models.CopilotMessageRole.user,
        content="prior question",
    )
    db_session.add(user_msg)
    db_session.flush()
    assistant_msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content="reply",
    )
    db_session.add(assistant_msg)
    db_session.flush()
    db_session.add(
        models.CopilotMessageRating(
            message_id=assistant_msg.id,
            user_id=admin_user.id,
            value="down",
            comment="bad",
        )
    )
    db_session.commit()
    out = bottom_messages(db_session, limit=10)
    assert out[0]["prior_user_text"] == "prior question"
    assert out[0]["assistant_text"] == "reply"


def test_bottom_messages_limit_caps_results(db_session, admin_user):
    sess = _seed_sess(db_session, admin_user)
    for i in range(5):
        _seed_msg_rating(
            db_session, admin_user, sess, "down", comment=f"c{i}"
        )
    out = bottom_messages(db_session, limit=3)
    assert len(out) == 3


def test_bottom_messages_no_prior_user_yields_none(db_session, admin_user):
    """If the down-rated assistant message has no preceding user turn,
    prior_user_text is None."""
    sess = _seed_sess(db_session, admin_user)
    _seed_msg_rating(db_session, admin_user, sess, "down", comment="orphan")
    out = bottom_messages(db_session, limit=10)
    assert out[0]["prior_user_text"] is None


def test_bottom_messages_does_not_re_scrub_pii(db_session, admin_user):
    """The aggregator returns persisted text verbatim — it must NOT re-run
    the redactor. Phase 33 scrubbed on persist; double-scrubbing would
    indicate a layering regression.

    We seed text that *looks* like an email (and would be scrubbed by the
    Phase 33 redactor) and assert it round-trips byte-for-byte. If a future
    refactor were to introduce a redact() call in this code path, this would
    catch it.
    """
    sess = _seed_sess(db_session, admin_user)
    # Pretend the persisted assistant text already contains an email-shaped
    # string (in real life Phase 33 would have rejected/redacted on persist;
    # here we are asserting NO further scrubbing happens at the aggregator).
    looks_like_email = "see foo@example.com for context"
    msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content=looks_like_email,
    )
    db_session.add(msg)
    db_session.flush()
    db_session.add(
        models.CopilotMessageRating(
            message_id=msg.id,
            user_id=admin_user.id,
            value="down",
            comment="raw",
        )
    )
    db_session.commit()
    out = bottom_messages(db_session, limit=10)
    assert out[0]["assistant_text"] == looks_like_email
