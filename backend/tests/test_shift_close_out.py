"""Closing out a shift: per-session attendance.

2026-08-05 shifts: a commitment's outcome no longer lives on its status row —
`ck_shift_signups_status_is_lifecycle` keeps ShiftSignup.status to
pending/confirmed/waitlisted/cancelled, and attended/no_show land in
`session_attendance`, keyed on (commitment, session). Volunteer hours are
summed from those records, so this is the path that has to be right.

Two shapes of close-out:
  * `POST /slots/{session_id}/resolve` — end Tuesday, leave Wednesday open.
  * `POST /events/{id}/resolve` — settle every session in the shift at once.
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


@pytest.fixture
def two_day_shift(db_session):
    """An event with one two-session shift and one confirmed commitment.

    Both sessions are in the past — closing out is something staff do after
    the fact — and the returned tuple is what every test here steers with.
    """
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.organizer)
    start = datetime.now(timezone.utc) - timedelta(days=3)
    event = EventFactory(
        owner=owner, start_date=start, end_date=start + timedelta(days=2)
    )
    db_session.flush()
    shift = make_shift(db_session, event.id, name="Tue+Wed", capacity=5)
    shift.current_count = 1
    sessions = []
    for i in range(2):
        session = models.Slot(
            event_id=event.id, shift_id=shift.id, sort_order=i,
            name=f"Period {i + 1}", slot_type=models.SlotType.PERIOD,
            capacity=1, current_count=0,
            start_time=start + timedelta(days=i),
            end_time=start + timedelta(days=i, hours=2),
            date=(start + timedelta(days=i)).date(),
        )
        db_session.add(session)
        sessions.append(session)
    commitment = book_shift(
        db_session, shift, VolunteerFactory(),
        status=models.SignupStatus.confirmed,
    )
    db_session.commit()
    return event, shift, sessions, commitment


def _attendance(db_session, commitment_id):
    return {
        r.slot_id: r.status
        for r in db_session.query(models.SessionAttendance).filter(
            models.SessionAttendance.shift_signup_id == commitment_id
        )
    }


class TestPerSessionCloseOut:
    def test_ending_one_session_leaves_the_other_open(
        self, client, db_session, two_day_shift
    ):
        event, shift, sessions, commitment = two_day_shift

        resp = client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        recorded = _attendance(db_session, commitment.id)
        assert recorded == {sessions[0].id: models.SignupStatus.attended}
        # The commitment's own status stays lifecycle-only; the outcome is the
        # attendance row, not the status.
        assert (
            db_session.get(models.ShiftSignup, commitment.id).status
            == models.SignupStatus.confirmed
        )

    def test_the_two_days_can_disagree(self, client, db_session, two_day_shift):
        """Showing up Tuesday and not Wednesday is the ordinary case, and the
        event-wide resolve cannot express it — which is why per-session exists."""
        event, shift, sessions, commitment = two_day_shift
        headers = auth_headers(client, event.owner)

        client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []}, headers=headers,
        )
        client.post(
            f"/api/v1/slots/{sessions[1].id}/resolve",
            json={"attended": [], "no_show": [str(commitment.id)]}, headers=headers,
        )

        db_session.expire_all()
        assert _attendance(db_session, commitment.id) == {
            sessions[0].id: models.SignupStatus.attended,
            sessions[1].id: models.SignupStatus.no_show,
        }

    def test_a_pending_commitment_is_autoconfirmed_on_close_out(
        self, client, db_session, two_day_shift
    ):
        """The organizer marking someone attended is stronger evidence they
        were there than a missing email click."""
        event, shift, sessions, commitment = two_day_shift
        commitment.status = models.SignupStatus.pending
        db_session.commit()

        resp = client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert (
            db_session.get(models.ShiftSignup, commitment.id).status
            == models.SignupStatus.confirmed
        )

    def test_closing_a_session_twice_keeps_the_first_answer(
        self, client, db_session, two_day_shift
    ):
        """Re-running a close-out must not silently rewrite what was recorded,
        and must not 409 either — staff re-open the event to change an answer."""
        event, shift, sessions, commitment = two_day_shift
        headers = auth_headers(client, event.owner)

        client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []}, headers=headers,
        )
        again = client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [], "no_show": [str(commitment.id)]}, headers=headers,
        )
        assert again.status_code == 200, again.text

        db_session.expire_all()
        assert _attendance(db_session, commitment.id) == {
            sessions[0].id: models.SignupStatus.attended
        }

    def test_a_session_grants_no_orientation_credit(
        self, client, db_session, two_day_shift
    ):
        """Only orientation grants credit. If classroom work granted it too,
        the gate would let anyone through after their first shift."""
        event, shift, sessions, commitment = two_day_shift

        client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []},
            headers=auth_headers(client, event.owner),
        )

        db_session.expire_all()
        assert db_session.query(models.OrientationCredit).count() == 0

    def test_an_id_from_another_shift_is_404(
        self, client, db_session, two_day_shift
    ):
        """A typo must not be silently ignored — the attendance it would have
        written is somebody's hours."""
        event, shift, sessions, commitment = two_day_shift
        other = make_shift(db_session, event.id, name="Elsewhere", capacity=5)
        db_session.add(
            models.Slot(
                event_id=event.id, shift_id=other.id, sort_order=0,
                slot_type=models.SlotType.PERIOD, capacity=1, current_count=0,
                start_time=event.start_date,
                end_time=event.start_date + timedelta(hours=2),
                date=event.start_date.date(),
            )
        )
        stranger = book_shift(db_session, other, VolunteerFactory(),
                              status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [str(stranger.id)], "no_show": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 404

        db_session.expire_all()
        assert _attendance(db_session, stranger.id) == {}


class TestEventWideCloseOut:
    def test_ending_the_event_settles_every_session(
        self, client, db_session, two_day_shift
    ):
        """"End event" on an all-or-nothing bundle means all of it — leaving a
        session unrecorded would keep the event permanently incomplete."""
        event, shift, sessions, commitment = two_day_shift

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert _attendance(db_session, commitment.id) == {
            sessions[0].id: models.SignupStatus.attended,
            sessions[1].id: models.SignupStatus.attended,
        }

    def test_ending_the_event_after_a_per_session_close_out_is_a_no_op(
        self, client, db_session, two_day_shift
    ):
        """The realistic order of operations: Tuesday gets closed out at the
        door, then the event is ended later. Tuesday's answer must survive."""
        event, shift, sessions, commitment = two_day_shift
        headers = auth_headers(client, event.owner)

        client.post(
            f"/api/v1/slots/{sessions[0].id}/resolve",
            json={"attended": [], "no_show": [str(commitment.id)]}, headers=headers,
        )
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []}, headers=headers,
        )
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        assert _attendance(db_session, commitment.id) == {
            sessions[0].id: models.SignupStatus.no_show,
            sessions[1].id: models.SignupStatus.attended,
        }

    def test_an_unknown_id_is_404_and_writes_nothing(
        self, client, db_session, two_day_shift
    ):
        event, shift, sessions, commitment = two_day_shift

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(commitment.id), str(uuid.uuid4())], "no_show": []},
            headers=auth_headers(client, event.owner),
        )
        assert resp.status_code == 404

        db_session.expire_all()
        # Atomic: the good id in the same batch is rolled back too.
        assert _attendance(db_session, commitment.id) == {}

    def test_a_participant_cannot_close_out(self, client, db_session, two_day_shift):
        event, shift, sessions, commitment = two_day_shift
        participant = make_user(db_session, role=models.UserRole.participant)
        db_session.commit()

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(commitment.id)], "no_show": []},
            headers=auth_headers(client, participant),
        )
        assert resp.status_code == 403
