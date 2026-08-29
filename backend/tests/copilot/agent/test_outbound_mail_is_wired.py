"""K26 follow-up — the transport is now bound.

``test_outbound_mail_is_honest`` pinned the gap: the seam refused, because
refusing is the only honest thing a stub can do. This file pins what
replaces it. The honesty requirement does not relax now that mail can
actually leave; it moves. Three things must stay true:

- The flag alone still governs. Off means nothing leaves, and says so.
- A queued message is reported as queued, never as sent. The broker is
  durable and retries, but at the moment the tool returns, delivery has
  not happened. Calling that ``sent_count`` is the K26 shape again.
- A volunteer who opted out of reminder email is not mailed by an agent
  that picked them out of a model's reading of a sentence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.config import settings
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools import _outbound
from app.copilot.agent.tools.nudge_understaffed_module import (
    NUDGE_UNDERSTAFFED_MODULE_TOOL,
)
from app.copilot.agent.tools.send_reminder_email import SEND_REMINDER_EMAIL_TOOL
from app.models import Event, Signup, SignupStatus, Slot, SlotType, Volunteer


def _event(db_session, owner_id, *, title, start_date):
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=start_date,
        end_date=start_date + timedelta(hours=2),
        year=start_date.year,
        week_number=1,
        school="Adams",
    )
    db_session.add(ev)
    db_session.flush()
    return ev


def _booked(db_session, event, *, count):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        sort_order=0,
        name="P1",
        start_time=event.start_date,
        end_time=event.start_date + timedelta(hours=1),
        capacity=max(count, 1),
        current_count=count,
        slot_type=SlotType.ORIENTATION,
    )
    db_session.add(slot)
    db_session.flush()
    out = []
    for _ in range(count):
        v = Volunteer(
            id=uuid.uuid4(),
            email=f"v{uuid.uuid4().hex[:10]}@example.com",
            first_name="V",
            last_name="X",
        )
        db_session.add(v)
        db_session.flush()
        db_session.add(
            Signup(
                id=uuid.uuid4(),
                slot_id=slot.id,
                volunteer_id=v.id,
                status=SignupStatus.confirmed,
            )
        )
        out.append(v)
    db_session.flush()
    return out


@pytest.fixture
def admin(db_session):
    from tests.fixtures.helpers import make_user

    u = make_user(
        db_session,
        email=f"k26w_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.admin,
    )
    db_session.flush()
    return u


@pytest.fixture
def admin_scope():
    return scope_for(role="admin", caller_id=None)


@pytest.fixture
def wired(monkeypatch):
    """Flag on, and a recorder standing in for the broker."""
    monkeypatch.setattr(settings, "copilot_outbound_email_enabled", True)
    queued = []
    monkeypatch.setattr(
        _outbound, "_enqueue", lambda **kw: queued.append(kw)
    )
    return queued


def _opt_out(db_session, email):
    db_session.add(
        models.VolunteerPreference(
            volunteer_email=email.strip().lower(),
            email_reminders_enabled=False,
            sms_opt_in=False,
        )
    )
    db_session.flush()


class TestTheFlagStillGoverns:
    def test_off_means_nothing_leaves(self, db_session, admin, admin_scope):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [v] = _booked(db_session, ev, count=1)

        with pytest.raises(_outbound.OutboundNotWired) as exc:
            SEND_REMINDER_EMAIL_TOOL.handler(
                db_session,
                admin_scope,
                {"participant_ids": [str(v.id)], "template": "reminder"},
            )
        assert "nothing was sent" in str(exc.value)

    def test_on_hands_a_real_message_to_the_broker(
        self, db_session, admin, admin_scope, wired
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [v] = _booked(db_session, ev, count=1)

        SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(v.id)], "template": "reminder"},
        )

        assert len(wired) == 1
        assert wired[0]["to_email"] == v.email
        assert wired[0]["subject"]
        assert wired[0]["text_body"]


class TestQueuedIsNotSent:
    def test_the_reminder_tool_reports_queued_not_sent(
        self, db_session, admin, admin_scope, wired
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        vols = _booked(db_session, ev, count=2)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(v.id) for v in vols], "template": "reminder"},
        )

        assert out["queued_count"] == 2
        assert "sent_count" not in out

    def test_the_nudge_tool_reports_queued_not_notified(
        self, db_session, admin, admin_scope, wired
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)
        other = _event(db_session, admin.id, title="Other", start_date=soon)
        _booked(db_session, other, count=2)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session, admin_scope, {"module_id": str(target.id)}
        )

        assert out["queued_count"] == 2
        assert "notified_count" not in out


class TestOptOutsHold:
    def test_an_opted_out_volunteer_is_skipped_not_mailed(
        self, db_session, admin, admin_scope, wired
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        a, b = _booked(db_session, ev, count=2)
        _opt_out(db_session, a.email)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(a.id), str(b.id)], "template": "reminder"},
        )

        assert out["queued_count"] == 1
        assert out["skipped_count"] == 1
        assert [m["to_email"] for m in wired] == [b.email]

    def test_an_opt_out_is_not_counted_as_a_failure(
        self, db_session, admin, admin_scope, wired
    ):
        """A skip is a respected choice; a failure is something gone wrong.
        Folding them together hides both."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [a] = _booked(db_session, ev, count=1)
        _opt_out(db_session, a.email)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(a.id)], "template": "reminder"},
        )

        assert out == {"queued_count": 0, "failed_count": 0, "skipped_count": 1}

    def test_the_nudge_tool_respects_opt_outs_too(
        self, db_session, admin, admin_scope, wired
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)
        other = _event(db_session, admin.id, title="Other", start_date=soon)
        a, b = _booked(db_session, other, count=2)
        _opt_out(db_session, a.email)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session, admin_scope, {"module_id": str(target.id)}
        )

        assert out["queued_count"] == 1
        assert out["skipped_count"] == 1
