"""Phase 35-02-D: human-rating join against 35-01's feedback tables.

Seeds the existing tables (copilot_message_ratings + copilot_session_ratings
+ copilot_sessions) with rows tied to a known model_id, then asserts the
join aggregator returns the right per-model rollup.
"""
from __future__ import annotations

import uuid

import pytest

from app import models
from app.config import settings


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


def _seed_session(db_session, user, model_id):
    sess = models.CopilotSession(
        id=uuid.uuid4(), user_id=user.id, model_id=model_id,
        system_prompt_hash="h" * 64, system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def _seed_assistant_msg(db_session, sess):
    msg = models.CopilotMessage(
        id=uuid.uuid4(), session_id=sess.id,
        role=models.CopilotMessageRole.assistant, content="x",
    )
    db_session.add(msg)
    db_session.commit()
    return msg


def test_per_model_thumbs_up_rate(db_session):
    from tests.fixtures.helpers import make_user
    from app.eval.metrics.human import per_model_rollup

    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess_a = _seed_session(db_session, user, "model-A:free")
    msg_a1 = _seed_assistant_msg(db_session, sess_a)
    msg_a2 = _seed_assistant_msg(db_session, sess_a)
    db_session.add(models.CopilotMessageRating(
        message_id=msg_a1.id, user_id=user.id, value="up",
    ))
    db_session.add(models.CopilotMessageRating(
        message_id=msg_a2.id, user_id=user.id, value="down", comment="x",
    ))
    sess_b = _seed_session(db_session, user, "model-B:free")
    msg_b1 = _seed_assistant_msg(db_session, sess_b)
    db_session.add(models.CopilotMessageRating(
        message_id=msg_b1.id, user_id=user.id, value="up",
    ))
    db_session.commit()

    out = per_model_rollup(db_session)
    by_model = {row["model_id"]: row for row in out}
    assert by_model["model-A:free"]["thumbs_up_rate"] == 0.5
    assert by_model["model-A:free"]["n_message_ratings"] == 2
    assert by_model["model-B:free"]["thumbs_up_rate"] == 1.0
    assert by_model["model-B:free"]["n_message_ratings"] == 1


def test_per_model_session_rating_avg_and_low_n_flag(db_session):
    from tests.fixtures.helpers import make_user
    from app.eval.metrics.human import per_model_rollup

    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    for v in (5, 4):
        sess = _seed_session(db_session, user, "model-A:free")
        _seed_assistant_msg(db_session, sess)
        db_session.add(models.CopilotSessionRating(
            session_id=sess.id, user_id=user.id, value=v,
        ))
    db_session.commit()

    out = per_model_rollup(db_session)
    a = next(row for row in out if row["model_id"] == "model-A:free")
    assert abs(a["session_rating_avg"] - 4.5) < 0.01
    assert a["n_session_ratings"] == 2
    assert a["insufficient_sample"] is True  # n < 10 cutoff (spec §6.3)


def test_per_model_bottom_quartile_count(db_session):
    from tests.fixtures.helpers import make_user
    from app.eval.metrics.human import per_model_rollup

    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _seed_session(db_session, user, "model-C:free")
    for _ in range(3):
        msg = _seed_assistant_msg(db_session, sess)
        db_session.add(models.CopilotMessageRating(
            message_id=msg.id, user_id=user.id, value="down", comment="x",
        ))
    db_session.commit()
    out = per_model_rollup(db_session)
    c = next(row for row in out if row["model_id"] == "model-C:free")
    assert c["n_thumbs_down"] == 3
