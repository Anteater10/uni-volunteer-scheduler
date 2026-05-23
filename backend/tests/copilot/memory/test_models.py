import uuid
from datetime import datetime, timezone

from app import models


def test_copilot_user_profile_round_trip(db_session, test_user):
    p = models.CopilotUserProfile(
        user_id=test_user.id,
        profile_text="prefers concise replies",
        version=1,
    )
    db_session.add(p)
    db_session.commit()
    fetched = (
        db_session.query(models.CopilotUserProfile)
        .filter_by(user_id=test_user.id)
        .one()
    )
    assert fetched.profile_text == "prefers concise replies"
    assert fetched.version == 1
    assert fetched.updated_at is not None


def test_copilot_session_has_new_memory_columns(db_session, test_user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=test_user.id,
        model_id="openrouter/auto",
        system_prompt_hash="x" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    assert sess.closed_at is None
    assert sess.profile_extracted_at is None
    assert sess.last_message_at is not None
