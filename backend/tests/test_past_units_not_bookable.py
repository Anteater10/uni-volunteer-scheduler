"""K10 — work that has already happened is not bookable.

Nothing in the signup path looked at the clock. The event signup window would
have covered it, but it is optional and almost no event carries one, so a
session that finished last week still rendered a live Sign-up button and the
booking went through — putting a volunteer on the roster for a class that is
over and emailing them a confirmation for a date in the past.

Both halves are covered here: the server refusing the booking, and the payload
saying so, since a button that offers what the server refuses is the same bug
wearing a different hat.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app import models
from app.services.waitlist_service import shift_has_ended
from tests.fixtures.factories import EventFactory, SlotFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_shift, make_user


def _event(db_session, *, days_from_now=1):
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.organizer)
    start = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    event = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(days=2),
        visibility="public",
    )
    db_session.flush()
    return event


def _orientation(db_session, event, *, hours_from_now=24, capacity=5):
    start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    slot = SlotFactory(
        event=event,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
    )
    db_session.flush()
    return slot


def _shift(db_session, event, *, offsets_hours, capacity=5):
    """A shift whose sessions sit at the given offsets from now, in hours."""
    shift = make_shift(db_session, event.id, capacity=capacity)
    for i, offset in enumerate(offsets_hours):
        start = datetime.now(timezone.utc) + timedelta(hours=offset)
        db_session.add(
            models.Slot(
                id=uuid4(),
                event_id=event.id,
                shift_id=shift.id,
                sort_order=i,
                name=f"Period {i + 1}",
                slot_type=models.SlotType.PERIOD,
                start_time=start,
                end_time=start + timedelta(hours=2),
                capacity=1,
                current_count=0,
                date=start.date(),
            )
        )
    db_session.flush()
    db_session.refresh(shift)
    return shift


def _signup_body(*, slot_ids=(), shift_ids=(), email=None):
    return {
        "first_name": "Pat",
        "last_name": "Volunteer",
        "email": email or f"pat-{uuid4().hex[:8]}@example.com",
        "phone": "805-555-0142",
        "slot_ids": [str(s) for s in slot_ids],
        "shift_ids": [str(s) for s in shift_ids],
    }


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_an_orientation_session_that_has_finished_cannot_be_booked(
    client, db_session
):
    event = _event(db_session, days_from_now=-7)
    past = _orientation(db_session, event, hours_from_now=-72)
    db_session.commit()

    resp = client.post(
        "/api/v1/public/signups", json=_signup_body(slot_ids=[past.id])
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SESSION_ENDED"


def test_a_shift_whose_sessions_are_all_over_cannot_be_booked(
    client, db_session
):
    event = _event(db_session, days_from_now=-7)
    _orientation(db_session, event, hours_from_now=-96)
    finished = _shift(db_session, event, offsets_hours=[-72, -48])
    db_session.commit()

    resp = client.post(
        "/api/v1/public/signups", json=_signup_body(shift_ids=[finished.id])
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "SESSION_ENDED"


def test_the_refusal_writes_nothing(client, db_session):
    """The guard runs before any write, so a rejected booking must not leave a
    volunteer row behind to confuse the next attempt."""
    event = _event(db_session, days_from_now=-7)
    past = _orientation(db_session, event, hours_from_now=-72)
    db_session.commit()
    email = "leaves-nothing-behind@example.com"

    resp = client.post(
        "/api/v1/public/signups",
        json=_signup_body(slot_ids=[past.id], email=email),
    )
    assert resp.status_code == 422

    db_session.expire_all()
    assert (
        db_session.query(models.Volunteer)
        .filter(models.Volunteer.email == email)
        .first()
        is None
    )
    assert db_session.query(models.Signup).count() == 0


# ---------------------------------------------------------------------------
# What must still work — the guard is about the past, not about being strict
# ---------------------------------------------------------------------------


def test_a_shift_with_one_session_left_is_still_bookable(client, db_session):
    """A Tue+Wed shift on Tuesday evening still has Wednesday's classroom to
    staff. Judging the shift on its first session would retire it while there
    is real work left, and would disagree with the promotion path."""
    event = _event(db_session, days_from_now=-1)
    orientation = _orientation(db_session, event, hours_from_now=-48)
    part_done = _shift(db_session, event, offsets_hours=[-24, +24])
    db_session.commit()

    # Orientation credit first, so the refusal under test can't be the
    # orientation requirement wearing a disguise.
    email = "half-a-shift-left@example.com"
    resp = client.post(
        "/api/v1/public/signups",
        json=_signup_body(
            slot_ids=[orientation.id], shift_ids=[part_done.id], email=email
        ),
    )

    # The orientation slot is over, so the batch is refused on that — the point
    # here is the shift itself is not what fails.
    assert resp.status_code == 422
    assert "orientation session has already finished" in resp.json()["detail"]


def test_a_session_in_progress_is_still_bookable(client, db_session):
    """Judged on end_time, not start_time: arriving twenty minutes into a
    two-hour session is late, not barred. The check-in window is what decides
    whether lateness counts."""
    event = _event(db_session)
    started = _orientation(db_session, event, hours_from_now=-1)
    db_session.commit()

    resp = client.post(
        "/api/v1/public/signups", json=_signup_body(slot_ids=[started.id])
    )

    assert resp.status_code == 201, resp.text


def test_an_upcoming_session_is_unaffected(client, db_session):
    event = _event(db_session)
    upcoming = _orientation(db_session, event, hours_from_now=48)
    db_session.commit()

    resp = client.post(
        "/api/v1/public/signups", json=_signup_body(slot_ids=[upcoming.id])
    )

    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# The payload — the page has to stop offering what the server refuses
# ---------------------------------------------------------------------------


def test_the_event_payload_marks_what_has_ended(client, db_session):
    event = _event(db_session, days_from_now=-1)
    past = _orientation(db_session, event, hours_from_now=-72)
    upcoming = _orientation(db_session, event, hours_from_now=48)
    finished = _shift(db_session, event, offsets_hours=[-72, -48])
    part_done = _shift(db_session, event, offsets_hours=[-24, +24])
    db_session.commit()

    body = client.get(f"/api/v1/public/events/{event.id}").json()

    by_id = {s["id"]: s for s in body["slots"]}
    assert by_id[str(past.id)]["has_ended"] is True
    assert by_id[str(upcoming.id)]["has_ended"] is False

    shifts = {s["id"]: s for s in body["shifts"]}
    assert shifts[str(finished.id)]["has_ended"] is True
    # Half its sessions are gone, but the shift is not — and the individual
    # sessions still say which is which.
    assert shifts[str(part_done.id)]["has_ended"] is False
    session_flags = [s["has_ended"] for s in shifts[str(part_done.id)]["sessions"]]
    assert session_flags == [True, False]


# ---------------------------------------------------------------------------
# The shared helper — promotion and booking must not drift apart
# ---------------------------------------------------------------------------


def test_shift_has_ended_is_judged_on_the_last_session(db_session):
    event = _event(db_session)
    assert shift_has_ended(_shift(db_session, event, offsets_hours=[-72, -48]))
    assert not shift_has_ended(_shift(db_session, event, offsets_hours=[-24, +24]))
    assert not shift_has_ended(_shift(db_session, event, offsets_hours=[+24, +48]))


def test_a_shift_with_no_sessions_is_not_treated_as_ended(db_session):
    """Unrepresentable through the API, so this is the defensive case: fail
    toward letting a human see the shift rather than silently hiding it."""
    event = _event(db_session)
    empty = make_shift(db_session, event.id, capacity=5)
    db_session.flush()

    assert shift_has_ended(empty) is False
