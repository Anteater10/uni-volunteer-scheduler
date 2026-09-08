"""K26 — the two mail tools reported sends that never happened, to an
audience nobody had bounded.

``_dispatch`` returned ``True`` and sent nothing. Both handlers counted
those Trues, so a confirmed send came back ``sent_count: 47`` and the model
told the admin 47 people had been reminded. Nobody had. The gap did not read
as a gap, because it reported itself as filled — the only way to find out
was 47 no-shows.

And ``nudge_understaffed_module`` built its recipients as "any volunteer
with any non-cancelled booking in the caller's scope". For an admin that is
the whole volunteer table. Harmless only for as long as ``_dispatch`` was a
no-op; the day a transport is bound, one model deciding a sentence means
"nudge people" mails everyone who has ever signed up for anything.
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
    RECENCY_WINDOW_DAYS,
)
from app.copilot.agent.tools.send_reminder_email import SEND_REMINDER_EMAIL_TOOL
from app.models import Event, Signup, SignupStatus, Slot, SlotType, Volunteer

ADMIN = "app.copilot.agent.tools.nudge_understaffed_module._dispatch"
REMINDER = "app.copilot.agent.tools.send_reminder_email._dispatch"


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
    """``count`` volunteers with a confirmed orientation signup on ``event``."""
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
        email=f"k26_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.admin,
    )
    db_session.flush()
    return u


@pytest.fixture
def admin_scope():
    return scope_for(role="admin", caller_id=None)


# ---------------------------------------------------------------------------
# 1. The stub must not report success
# ---------------------------------------------------------------------------


class TestTheStubNoLongerLies:
    def test_the_reminder_tool_refuses_instead_of_counting(
        self, db_session, admin, admin_scope
    ):
        """The exact K26 symptom: a full sent_count for a send that did not
        happen. The tool must raise, not return numbers."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [v] = _booked(db_session, ev, count=1)

        with pytest.raises(_outbound.OutboundNotWired):
            SEND_REMINDER_EMAIL_TOOL.handler(
                db_session,
                admin_scope,
                {"participant_ids": [str(v.id)], "template": "reminder"},
            )

    def test_the_nudge_tool_refuses_instead_of_counting(
        self, db_session, admin, admin_scope
    ):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)
        other = _event(db_session, admin.id, title="Other", start_date=soon)
        _booked(db_session, other, count=1)

        with pytest.raises(_outbound.OutboundNotWired):
            NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
                db_session, admin_scope, {"module_id": str(target.id)}
            )

    def test_turning_the_flag_on_reaches_a_real_transport(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        """A flag that enabled a no-op would recreate the bug exactly.

        Until the transport was bound this asserted the opposite — that the
        flag alone still refused — because an unwired flag that reported
        success was the whole of K26. The transport exists now, so the
        guarantee is restated rather than dropped: turning the flag on must
        put a real message on the broker. If this ever passes while nothing
        is enqueued, the no-op is back.
        """
        monkeypatch.setattr(settings, "copilot_outbound_email_enabled", True)
        queued = []
        monkeypatch.setattr(_outbound, "_enqueue", lambda **kw: queued.append(kw))
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [v] = _booked(db_session, ev, count=1)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(v.id)], "template": "reminder"},
        )

        assert out["queued_count"] == 1
        assert [m["to_email"] for m in queued] == [v.email]

    def test_the_refusal_reaches_the_user_as_a_failed_call(
        self, db_session, admin, admin_scope
    ):
        """The loop audits an exception as ``errored`` and hands the reason
        back to the model (K28), so nothing in the chain claims success."""
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


# ---------------------------------------------------------------------------
# 2. The mass-mail hazard
# ---------------------------------------------------------------------------


class TestTheNudgeAudienceIsBounded:
    def test_an_admin_nudge_is_not_the_whole_volunteer_table(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        """The headline hazard. A volunteer whose only activity was years
        away from this module used to be a recipient."""
        seen: list[str] = []
        monkeypatch.setattr(ADMIN, lambda email, name: seen.append(email) or True)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)

        nearby = _event(
            db_session, admin.id, title="Nearby", start_date=soon + timedelta(days=14)
        )
        _booked(db_session, nearby, count=2)

        ancient = _event(
            db_session,
            admin.id,
            title="Ancient",
            start_date=soon - timedelta(days=RECENCY_WINDOW_DAYS + 30),
        )
        long_gone = _booked(db_session, ancient, count=3)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session, admin_scope, {"module_id": str(target.id)}
        )
        assert out["queued_count"] == 2
        for v in long_gone:
            assert v.email not in seen

    def test_people_already_on_the_module_are_not_asked_to_join_it(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        seen: list[str] = []
        monkeypatch.setattr(ADMIN, lambda email, name: seen.append(email) or True)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)
        already = _booked(db_session, target, count=2)
        nearby = _event(db_session, admin.id, title="Nearby", start_date=soon)
        _booked(db_session, nearby, count=1)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session, admin_scope, {"module_id": str(target.id)}
        )
        assert out["queued_count"] == 1
        for v in already:
            assert v.email not in seen

    def test_an_oversized_audience_is_refused_not_truncated(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        """Mailing the first N and reporting N is a blast plus an
        understatement of one."""
        sent: list[str] = []
        monkeypatch.setattr(ADMIN, lambda email, name: sent.append(email) or True)
        monkeypatch.setattr(settings, "copilot_max_outbound_recipients", 2)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Target", start_date=soon)
        nearby = _event(db_session, admin.id, title="Nearby", start_date=soon)
        _booked(db_session, nearby, count=3)

        with pytest.raises(_outbound.RecipientLimitExceeded) as exc:
            NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
                db_session, admin_scope, {"module_id": str(target.id)}
            )
        assert exc.value.requested == 3
        assert sent == [], "refused, but some mail had already gone out"

    def test_an_organizer_still_only_reaches_their_own(
        self, db_session, admin, monkeypatch
    ):
        seen: list[str] = []
        monkeypatch.setattr(ADMIN, lambda email, name: seen.append(email) or True)

        from tests.fixtures.helpers import make_user

        org = make_user(
            db_session,
            email=f"k26org_{uuid.uuid4().hex[:8]}@example.com",
            role=models.UserRole.organizer,
        )
        db_session.flush()

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, org.id, title="Target", start_date=soon)
        mine = _event(db_session, org.id, title="Mine", start_date=soon)
        _booked(db_session, mine, count=1)
        theirs = _event(db_session, admin.id, title="Theirs", start_date=soon)
        others = _booked(db_session, theirs, count=4)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session,
            scope_for(role="organizer", caller_id=org.id),
            {"module_id": str(target.id)},
        )
        assert out["queued_count"] == 1
        for v in others:
            assert v.email not in seen


class TestTheRecipientQueriesDegradeQuietly:
    """The empty cases, which are the ones that reach production first."""

    def test_no_events_means_nobody_is_booked(self, db_session):
        from app.copilot.agent.tools import _bookings

        assert _bookings.volunteer_ids_on_events(db_session, []) == set()

    def test_an_empty_window_yields_no_recipients(self, db_session, admin):
        from app.copilot.agent.tools import _bookings

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        _booked(db_session, ev, count=2)

        assert (
            _bookings.volunteers_active_between(
                db_session,
                start=soon + timedelta(days=365),
                end=soon + timedelta(days=400),
            )
            == []
        )

    def test_a_module_nobody_can_be_asked_about_notifies_nobody(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        monkeypatch.setattr(ADMIN, lambda email, name: True)
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        target = _event(db_session, admin.id, title="Alone", start_date=soon)

        out = NUDGE_UNDERSTAFFED_MODULE_TOOL.handler(
            db_session, admin_scope, {"module_id": str(target.id)}
        )
        assert out["queued_count"] == 0


class TestTheReminderListIsBounded:
    def test_too_many_ids_is_refused_before_anything_is_sent(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        sent: list[str] = []
        monkeypatch.setattr(REMINDER, lambda email, template: sent.append(email) or True)
        monkeypatch.setattr(settings, "copilot_max_outbound_recipients", 2)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        vols = _booked(db_session, ev, count=3)

        with pytest.raises(_outbound.RecipientLimitExceeded) as exc:
            SEND_REMINDER_EMAIL_TOOL.handler(
                db_session,
                admin_scope,
                {
                    "participant_ids": [str(v.id) for v in vols],
                    "template": "reminder",
                },
            )
        assert exc.value.limit == 2
        assert sent == []

    def test_a_list_within_the_cap_still_sends(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        sent: list[str] = []
        monkeypatch.setattr(REMINDER, lambda email, template: sent.append(email) or True)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        vols = _booked(db_session, ev, count=2)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(v.id) for v in vols], "template": "reminder"},
        )
        assert out["queued_count"] == 2
        assert len(sent) == 2

    def test_an_unknown_participant_id_is_a_failure_not_a_send(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        sent: list[str] = []
        monkeypatch.setattr(REMINDER, lambda email, template: sent.append(email) or True)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(uuid.uuid4())], "template": "reminder"},
        )
        assert out == {"queued_count": 0, "failed_count": 1, "skipped_count": 0}
        assert sent == []

    def test_a_bounced_address_is_still_only_a_failed_count(
        self, db_session, admin, admin_scope, monkeypatch
    ):
        """A False from the seam means one address failed. That must stay
        distinguishable from "no transport", which is the whole send."""
        monkeypatch.setattr(REMINDER, lambda email, template: False)

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="M", start_date=soon)
        [v] = _booked(db_session, ev, count=1)

        out = SEND_REMINDER_EMAIL_TOOL.handler(
            db_session,
            admin_scope,
            {"participant_ids": [str(v.id)], "template": "reminder"},
        )
        assert out == {"queued_count": 0, "failed_count": 1, "skipped_count": 0}
