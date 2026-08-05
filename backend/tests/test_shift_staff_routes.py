"""Staff overrides on a shift commitment.

2026-08-05: every staff override that could move a slot booking got a shift
twin in `81ee6a0` / `64ac08b` — promote (admin and organizer), cancel, waitlist
reorder, grant-orientation — and none of them had a test. These are the ones
the spec asked for.

The shift twins are deliberately identical in contract to their slot versions
(see `test_waitlist_service.py`), so what is checked here is mostly the part
that is *not* identical: capacity lives on the shift, a commitment's outcome
lives in `session_attendance`, and "has it ended" is judged on the shift's last
session rather than its first.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import EventFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_shift,
    make_user,
)


@pytest.fixture(autouse=True)
def promotion_emails(monkeypatch):
    """Captures the promotion mail instead of queueing it. Autouse because a
    promote on any of these routes enqueues one."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    return sent


def _event(db_session, *, module_slug=None, days_from_now=1):
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.organizer)
    start = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    event = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(days=2),
        module_slug=module_slug,
    )
    db_session.flush()
    return event


def _shift_with_sessions(db_session, event, *, capacity=1, n_sessions=1, ended=False):
    """A shift and its sessions. `ended` puts every session in the past, which
    is the only state that makes a promotion pointless."""
    shift = make_shift(db_session, event.id, capacity=capacity)
    base = (
        datetime.now(timezone.utc) - timedelta(days=3)
        if ended
        else datetime.now(timezone.utc) + timedelta(days=1)
    )
    for i in range(n_sessions):
        db_session.add(
            models.Slot(
                event_id=event.id,
                shift_id=shift.id,
                sort_order=i,
                slot_type=models.SlotType.PERIOD,
                capacity=1,
                current_count=0,
                start_time=base + timedelta(days=i),
                end_time=base + timedelta(days=i, hours=2),
                date=(base + timedelta(days=i)).date(),
            )
        )
    db_session.flush()
    return shift


def _waitlisted(db_session, shift, *, email=None, when=None):
    volunteer = VolunteerFactory(
        email=email or f"wl-{uuid.uuid4().hex[:8]}@example.com"
    )
    return book_shift(
        db_session, shift, volunteer,
        status=models.SignupStatus.waitlisted, when=when,
    )


class TestAdminPromote:
    URL = "/api/v1/admin/shift-signups/{id}/promote"

    def test_promote_seats_the_commitment_and_mails_them(
        self, client, db_session, promotion_emails
    ):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=2, n_sessions=2)
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending"

        db_session.expire_all()
        assert (
            db_session.get(models.ShiftSignup, waiting.id).status
            == models.SignupStatus.pending
        )
        # The seat comes off the shift, not off any one session.
        assert db_session.get(models.Shift, shift.id).current_count == 1
        assert promotion_emails and promotion_emails[-1]["shift_signup_id"] == str(
            waiting.id
        )

    def test_a_full_shift_refuses_rather_than_overfilling(
        self, client, db_session
    ):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        shift.current_count = 1
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 400
        assert "full" in resp.json()["detail"]

        db_session.expire_all()
        assert (
            db_session.get(models.ShiftSignup, waiting.id).status
            == models.SignupStatus.waitlisted
        )
        assert db_session.get(models.Shift, shift.id).current_count == 1

    def test_only_a_waitlisted_commitment_can_be_promoted(
        self, client, db_session
    ):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=5)
        confirmed = book_shift(
            db_session, shift, VolunteerFactory(),
            status=models.SignupStatus.confirmed,
        )
        db_session.commit()

        resp = client.post(
            self.URL.format(id=confirmed.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 400

    def test_a_shift_whose_last_session_is_over_cannot_be_promoted(
        self, client, db_session
    ):
        event = _event(db_session, days_from_now=-5)
        shift = _shift_with_sessions(db_session, event, capacity=5, n_sessions=2,
                                     ended=True)
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "SLOT_ENDED"

    def test_a_shift_still_running_tomorrow_can_be_promoted_today(
        self, client, db_session
    ):
        """"Has it ended" is judged on the *last* session — a Tue+Wed shift is
        still worth offering on Tuesday evening."""
        event = _event(db_session, days_from_now=-1)
        shift = make_shift(db_session, event.id, capacity=5)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        for i, when in enumerate((yesterday, datetime.now(timezone.utc) + timedelta(days=1))):
            db_session.add(
                models.Slot(
                    event_id=event.id, shift_id=shift.id, sort_order=i,
                    slot_type=models.SlotType.PERIOD, capacity=1, current_count=0,
                    start_time=when, end_time=when + timedelta(hours=2),
                    date=when.date(),
                )
            )
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 200, resp.text

    def test_unknown_commitment_is_404(self, client, db_session):
        event = _event(db_session)
        db_session.commit()
        resp = client.post(
            self.URL.format(id=uuid.uuid4()), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 404

    def test_participant_is_forbidden(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=5)
        waiting = _waitlisted(db_session, shift)
        participant = make_user(db_session, role=models.UserRole.participant)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id),
            headers=auth_headers(client, participant),
        )
        assert resp.status_code == 403


class TestAdminCancel:
    URL = "/api/v1/admin/shift-signups/{id}/cancel"

    def test_cancel_frees_the_seat_but_promotes_nobody(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        shift.current_count = 1
        holder = book_shift(db_session, shift, VolunteerFactory(),
                            status=models.SignupStatus.confirmed)
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=holder.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"

        db_session.expire_all()
        assert db_session.get(models.Shift, shift.id).current_count == 0
        # The waitlist only moves by explicit staff promotion — same rule the
        # slot side settled on.
        assert (
            db_session.get(models.ShiftSignup, waiting.id).status
            == models.SignupStatus.waitlisted
        )

    def test_cancelling_a_waitlisted_commitment_leaves_the_count_alone(
        self, client, db_session
    ):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        shift.current_count = 1
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(id=waiting.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(models.Shift, shift.id).current_count == 1

    def test_cancel_is_idempotent(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=2)
        shift.current_count = 1
        holder = book_shift(db_session, shift, VolunteerFactory(),
                            status=models.SignupStatus.confirmed)
        db_session.commit()
        headers = auth_headers(client, event.owner)

        assert client.post(self.URL.format(id=holder.id), headers=headers).status_code == 200
        again = client.post(self.URL.format(id=holder.id), headers=headers)
        assert again.status_code == 200
        assert again.json()["status"] == "cancelled"

        db_session.expire_all()
        # Cancelling twice must not free the seat twice.
        assert db_session.get(models.Shift, shift.id).current_count == 0

    def test_recorded_attendance_blocks_the_cancel(self, client, db_session):
        """Hours are summed over attendance records, so cancelling a commitment
        that has any would destroy the basis for someone's credit."""
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=2, n_sessions=2)
        shift.current_count = 1
        holder = book_shift(db_session, shift, VolunteerFactory(),
                            status=models.SignupStatus.confirmed)
        session = shift.sessions[0]
        db_session.add(
            models.SessionAttendance(
                shift_signup_id=holder.id,
                slot_id=session.id,
                status=models.SignupStatus.attended,
            )
        )
        db_session.commit()

        resp = client.post(
            self.URL.format(id=holder.id), headers=auth_headers(client, event.owner)
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "SHIFT_SIGNUP_NOT_CANCELLABLE"

        db_session.expire_all()
        assert (
            db_session.get(models.ShiftSignup, holder.id).status
            == models.SignupStatus.confirmed
        )
        assert db_session.get(models.Shift, shift.id).current_count == 1


class TestAdminWaitlistOrder:
    URL = "/api/v1/admin/events/{event_id}/shifts/{shift_id}/waitlist-order"

    def _two_waiters(self, db_session, shift):
        now = datetime.now(timezone.utc)
        first = _waitlisted(db_session, shift, when=now - timedelta(minutes=30))
        second = _waitlisted(db_session, shift, when=now - timedelta(minutes=5))
        return first, second

    def test_reorder_rewrites_the_fifo_order(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        first, second = self._two_waiters(db_session, shift)
        admin = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()

        resp = client.patch(
            self.URL.format(event_id=event.id, shift_id=shift.id),
            json={"ordered_shift_signup_ids": [str(second.id), str(first.id)]},
            headers=auth_headers(client, admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["ordered_shift_signup_ids"] == [str(second.id), str(first.id)]

        from app.services.waitlist_service import list_waitlisted_for_shift

        db_session.expire_all()
        assert [r.id for r in list_waitlisted_for_shift(db_session, shift.id)] == [
            second.id, first.id
        ]

    def test_a_partial_list_is_refused(self, client, db_session):
        """Omitting someone would drop them out of the queue silently."""
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        first, second = self._two_waiters(db_session, shift)
        admin = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()

        resp = client.patch(
            self.URL.format(event_id=event.id, shift_id=shift.id),
            json={"ordered_shift_signup_ids": [str(second.id)]},
            headers=auth_headers(client, admin),
        )
        assert resp.status_code == 400

        from app.services.waitlist_service import list_waitlisted_for_shift

        db_session.expire_all()
        assert [r.id for r in list_waitlisted_for_shift(db_session, shift.id)] == [
            first.id, second.id
        ]

    def test_a_shift_from_another_event_is_404(self, client, db_session):
        event = _event(db_session)
        other = _event(db_session)
        shift = _shift_with_sessions(db_session, other, capacity=1)
        admin = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()

        resp = client.patch(
            self.URL.format(event_id=event.id, shift_id=shift.id),
            json={"ordered_shift_signup_ids": []},
            headers=auth_headers(client, admin),
        )
        assert resp.status_code == 404

    def test_a_non_list_body_is_422(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        admin = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()

        resp = client.patch(
            self.URL.format(event_id=event.id, shift_id=shift.id),
            json={"ordered_shift_signup_ids": "nope"},
            headers=auth_headers(client, admin),
        )
        assert resp.status_code == 422

    def test_an_organizer_cannot_reorder(self, client, db_session):
        """Admin-only, matching the slot version."""
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        db_session.commit()

        resp = client.patch(
            self.URL.format(event_id=event.id, shift_id=shift.id),
            json={"ordered_shift_signup_ids": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 403


class TestOrganizerPromote:
    URL = "/api/v1/organizer/events/{event_id}/shift-signups/{id}/promote"

    def test_full_shift_is_409_and_overfill_is_the_way_through(
        self, client, db_session
    ):
        """A full shift is usually *why* the person is waitlisted, so without
        the opt-in the roster's Promote button could never succeed."""
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=1)
        shift.current_count = 1
        waiting = _waitlisted(db_session, shift)
        db_session.commit()
        headers = auth_headers(client, event.owner)
        url = self.URL.format(event_id=event.id, id=waiting.id)

        refused = client.post(url, headers=headers)
        assert refused.status_code == 409

        forced = client.post(url, params={"allow_overfill": True}, headers=headers)
        assert forced.status_code == 200, forced.text
        assert forced.json()["status"] == "pending"

        db_session.expire_all()
        # Over capacity on purpose — a decision about a real room.
        assert db_session.get(models.Shift, shift.id).current_count == 2

    def test_a_commitment_from_another_event_is_refused(self, client, db_session):
        event = _event(db_session)
        other = _event(db_session)
        shift = _shift_with_sessions(db_session, other, capacity=5)
        waiting = _waitlisted(db_session, shift)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=waiting.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 400


class TestGrantOrientationForShiftSignup:
    URL = "/api/v1/organizer/events/{event_id}/shift-signups/{id}/grant-orientation"

    def _module(self, db_session, slug="bio-intro", family_key="bio"):
        module = models.Module(
            slug=slug, name=slug.title(), default_capacity=20,
            duration_minutes=120, session_count=1, family_key=family_key,
        )
        db_session.add(module)
        db_session.flush()
        return module

    def test_staff_vouch_at_the_door(self, client, db_session):
        """The roster's classroom rows are commitments now, so the slot-keyed
        grant route 404s for every one of them — without this the orientation
        gate has no override at all."""
        self._module(db_session)
        event = _event(db_session, module_slug="bio-intro")
        shift = _shift_with_sessions(db_session, event, capacity=5)
        commitment = book_shift(db_session, shift, VolunteerFactory(),
                                status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=commitment.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["family_key"] == "bio"
        assert body["source"] == "grant"
        assert body["volunteer_email"] == commitment.volunteer.email

        from app.services.orientation_service import has_orientation_credit

        db_session.expire_all()
        assert has_orientation_credit(
            db_session, commitment.volunteer.email, "bio"
        ).has_credit

    def test_a_cancelled_commitment_gets_nothing(self, client, db_session):
        self._module(db_session)
        event = _event(db_session, module_slug="bio-intro")
        shift = _shift_with_sessions(db_session, event, capacity=5)
        commitment = book_shift(db_session, shift, VolunteerFactory(),
                                status=models.SignupStatus.cancelled)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=commitment.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 409

    def test_a_commitment_from_another_event_is_refused(self, client, db_session):
        self._module(db_session)
        event = _event(db_session, module_slug="bio-intro")
        other = _event(db_session, module_slug="bio-intro")
        shift = _shift_with_sessions(db_session, other, capacity=5)
        commitment = book_shift(db_session, shift, VolunteerFactory(),
                                status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=commitment.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 400

    def test_a_moduleless_event_cannot_resolve_a_family(self, client, db_session):
        event = _event(db_session)
        shift = _shift_with_sessions(db_session, event, capacity=5)
        commitment = book_shift(db_session, shift, VolunteerFactory(),
                                status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=commitment.id),
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 400
        assert "module_slug" in resp.json()["detail"]

    def test_a_participant_cannot_grant(self, client, db_session):
        self._module(db_session)
        event = _event(db_session, module_slug="bio-intro")
        shift = _shift_with_sessions(db_session, event, capacity=5)
        commitment = book_shift(db_session, shift, VolunteerFactory(),
                                status=models.SignupStatus.confirmed)
        participant = make_user(db_session, role=models.UserRole.participant)
        db_session.commit()

        resp = client.post(
            self.URL.format(event_id=event.id, id=commitment.id),
            headers=auth_headers(client, participant),
        )
        assert resp.status_code == 403
