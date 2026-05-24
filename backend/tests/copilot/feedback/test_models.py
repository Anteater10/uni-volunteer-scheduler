"""Phase 35-01-A: ORM model round-trip tests for the rating tables."""
import uuid

from app import models
from tests.fixtures.helpers import make_user


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


def test_copilot_message_rating_round_trip(db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _seed_session(db_session, admin)
    msg = _seed_message(db_session, sess)

    r = models.CopilotMessageRating(
        message_id=msg.id, user_id=admin.id, value="up"
    )
    db_session.add(r)
    db_session.commit()

    fetched = (
        db_session.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=admin.id)
        .one()
    )
    assert fetched.value == "up"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.comment is None


def test_copilot_message_rating_with_comment(db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _seed_session(db_session, admin)
    msg = _seed_message(db_session, sess)

    r = models.CopilotMessageRating(
        message_id=msg.id,
        user_id=admin.id,
        value="down",
        comment="hallucinated the slot id",
    )
    db_session.add(r)
    db_session.commit()

    fetched = (
        db_session.query(models.CopilotMessageRating)
        .filter_by(message_id=msg.id, user_id=admin.id)
        .one()
    )
    assert fetched.value == "down"
    assert fetched.comment == "hallucinated the slot id"


def test_copilot_session_rating_round_trip(db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _seed_session(db_session, admin)

    r = models.CopilotSessionRating(
        session_id=sess.id, user_id=admin.id, value=4, comment=None
    )
    db_session.add(r)
    db_session.commit()

    fetched = (
        db_session.query(models.CopilotSessionRating)
        .filter_by(session_id=sess.id, user_id=admin.id)
        .one()
    )
    assert fetched.value == 4
    assert fetched.created_at is not None


def test_copilot_session_rating_with_comment(db_session):
    admin = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _seed_session(db_session, admin)

    r = models.CopilotSessionRating(
        session_id=sess.id,
        user_id=admin.id,
        value=2,
        comment="confusing UX on the chat drawer",
    )
    db_session.add(r)
    db_session.commit()

    fetched = (
        db_session.query(models.CopilotSessionRating)
        .filter_by(session_id=sess.id, user_id=admin.id)
        .one()
    )
    assert fetched.value == 2
    assert fetched.comment == "confusing UX on the chat drawer"
