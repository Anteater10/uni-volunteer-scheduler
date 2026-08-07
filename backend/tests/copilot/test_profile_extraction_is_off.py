"""K31 — end-of-session profile extraction is off, and provably so.

The job is an unattended LLM call, one per closed session plus up to three
Celery retries, drawing on the same OpenRouter account — and therefore the
same free-tier request budget — as the chat a user is actually waiting on.
On an unfunded account that budget is roughly 50 requests a day for
everything. So a background job nobody triggered can spend the day's
allowance and leave a real question answered with a rate-limit error the
user cannot account for.

Turning it off is only worth anything if every route in is closed, so each
one is asserted here: the beat sweep, the explicit close endpoint, and the
task itself (for work already sitting in the queue when the flag flipped).
The things that must keep working when it is off — closing sessions, and
reading a profile extracted earlier — are asserted too, because a fix that
quietly breaks those is not a fix.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.tasks import extract_profile


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "copilot_profile_extraction_enabled", True)


@pytest.fixture
def enqueued(monkeypatch):
    """Record every ``extract_profile_facts.delay`` instead of queueing it."""
    calls: list[str] = []
    monkeypatch.setattr(
        extract_profile.extract_profile_facts,
        "delay",
        lambda sid: calls.append(sid),
    )
    return calls


def _idle_session(db_session, user_id, *, minutes_idle=120):
    session_id = uuid.uuid4()
    stale = datetime.now(timezone.utc) - timedelta(minutes=minutes_idle)
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version, last_message_at) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1', :t)"
        ),
        {"s": session_id, "u": user_id, "t": stale},
    )
    db_session.commit()
    return session_id


@pytest.fixture
def admin(db_session):
    from app import models
    from tests.fixtures.helpers import make_user

    u = make_user(
        db_session,
        email=f"k31_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.admin,
    )
    db_session.commit()
    return u


# ---------------------------------------------------------------------------
# The default
# ---------------------------------------------------------------------------


def test_extraction_is_off_unless_someone_turns_it_on():
    assert settings.copilot_profile_extraction_enabled is False


# ---------------------------------------------------------------------------
# Route 1 — the beat sweep
# ---------------------------------------------------------------------------


class TestTheIdleSweep:
    def test_it_closes_the_session_but_does_not_spend_a_request(
        self, db_session, admin, enqueued, monkeypatch
    ):
        monkeypatch.setattr(extract_profile, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        sid = _idle_session(db_session, admin.id)

        closed = extract_profile.sweep_idle_sessions()

        assert closed >= 1
        assert enqueued == [], "the sweep queued an LLM call while off"
        row = db_session.execute(
            text("SELECT closed_at FROM copilot_sessions WHERE id = :s"),
            {"s": sid},
        ).first()
        assert row.closed_at is not None, (
            "the session was left open — closing is free hygiene and must "
            "not have been switched off along with the extractor"
        )

    def test_it_does_enqueue_when_extraction_is_on(
        self, db_session, admin, enqueued, enabled, monkeypatch
    ):
        """The gate is a gate, not a deletion."""
        monkeypatch.setattr(extract_profile, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        sid = _idle_session(db_session, admin.id)

        extract_profile.sweep_idle_sessions()

        assert str(sid) in enqueued


# ---------------------------------------------------------------------------
# Route 2 — the explicit close endpoint
# ---------------------------------------------------------------------------


class TestTheCloseEndpoint:
    def test_closing_a_session_does_not_enqueue_extraction(
        self, client, db_session, admin, enqueued, monkeypatch
    ):
        monkeypatch.setattr(settings, "copilot_enabled", True)
        monkeypatch.setattr(
            "app.copilot.router.extract_profile_facts",
            extract_profile.extract_profile_facts,
        )
        from tests.fixtures.helpers import auth_headers

        sid = _idle_session(db_session, admin.id)
        resp = client.post(
            f"/api/v1/copilot/sessions/{sid}/close",
            headers=auth_headers(client, admin),
        )
        assert resp.status_code == 204
        assert enqueued == []

    def test_the_session_is_still_closed(
        self, client, db_session, admin, enqueued, monkeypatch
    ):
        """The caller asked for a close. They get one."""
        monkeypatch.setattr(settings, "copilot_enabled", True)
        from tests.fixtures.helpers import auth_headers

        sid = _idle_session(db_session, admin.id)
        client.post(
            f"/api/v1/copilot/sessions/{sid}/close",
            headers=auth_headers(client, admin),
        )
        row = db_session.execute(
            text("SELECT closed_at FROM copilot_sessions WHERE id = :s"),
            {"s": sid},
        ).first()
        assert row.closed_at is not None


# ---------------------------------------------------------------------------
# Route 3 — work already in the queue
# ---------------------------------------------------------------------------


class TestTheTaskItself:
    def test_a_task_queued_before_the_flag_flipped_still_does_not_run(
        self, db_session, admin, monkeypatch
    ):
        """Gating only the producers would let every backlogged task through.

        This is the case a single gate would miss: the tasks are already in
        Redis, and each one is a request off the day's budget.
        """
        built = []
        monkeypatch.setattr(
            extract_profile,
            "_build_llm",
            lambda: built.append(1),
        )
        monkeypatch.setattr(extract_profile, "SessionLocal", lambda: db_session)
        sid = _idle_session(db_session, admin.id)

        extract_profile.extract_profile_facts(str(sid))

        assert built == [], "the extractor reached the LLM while disabled"

    def test_it_does_not_stamp_the_session_as_extracted(
        self, db_session, admin, monkeypatch
    ):
        """Stamping would make the session look done, so turning extraction
        back on would silently skip every session closed while it was off."""
        monkeypatch.setattr(extract_profile, "SessionLocal", lambda: db_session)
        sid = _idle_session(db_session, admin.id)

        extract_profile.extract_profile_facts(str(sid))

        row = db_session.execute(
            text(
                "SELECT profile_extracted_at FROM copilot_sessions "
                "WHERE id = :s"
            ),
            {"s": sid},
        ).first()
        assert row.profile_extracted_at is None


# ---------------------------------------------------------------------------
# What must keep working
# ---------------------------------------------------------------------------


class TestReadsAreUnaffected:
    def test_an_existing_profile_is_still_served(
        self, client, db_session, admin, monkeypatch
    ):
        """Extraction stopping is not the same as forgetting. Whatever was
        extracted before the flag went off still belongs to the user."""
        monkeypatch.setattr(settings, "copilot_enabled", True)
        from tests.fixtures.helpers import auth_headers

        db_session.execute(
            text(
                "INSERT INTO copilot_user_profiles (user_id, profile_text, "
                "version) VALUES (:u, :t, 1)"
            ),
            {"u": admin.id, "t": "Prefers short answers."},
        )
        db_session.commit()

        resp = client.get(
            "/api/v1/copilot/profile", headers=auth_headers(client, admin)
        )
        assert resp.status_code == 200
        assert resp.json()["profile_text"] == "Prefers short answers."
