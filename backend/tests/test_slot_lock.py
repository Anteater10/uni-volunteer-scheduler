"""The attendance lock lives on the slot (Kim's report, 2026-10-13).

Andy's rules, each pinned by a test class below:

1. Nothing is permanently locked: any orientation slot or shift session can be
   closed and reopened, any number of times.
2. Closing happens only when a person presses the button (close_slot /
   close_event) — never on a timer, never because everyone has been marked.
3. attended / no_show exist only on a closed slot. While a slot is open a
   person is "not checked in" or "checked in".
4. pending and confirmed are the same everywhere (both "not checked in", both
   closed out).
5. The no-show flag counts only closed, started slots (test_no_show_flag.py).
6. "End event" never closes a session that has not started.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import models
from app.models import (
    AuditLog,
    Event,
    Module,
    OrientationCredit,
    OrientationCreditSource,
    SessionAttendance,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    UserRole,
    Volunteer,
)
from app.services import check_in_service as cis
from app.services.check_in_service import (
    CheckInWindowError,
    InvalidTransitionError,
    SlotClosedError,
    SlotNotStartedError,
    check_in_selected,
    check_in_session,
    check_in_signup,
    close_event,
    close_slot,
    event_check_in_by_email,
    lookup_check_in_options,
    mark_present,
    refresh_event_completion,
    reopen_event,
    reopen_slot,
    self_check_in,
    undo_check_in,
    undo_session_check_in,
    window_state,
)
from app.services.orientation_service import grant_orientation_credit
from tests.fixtures.factories import AcademicQuarterFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_shift,
    make_user,
)

NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


# ---------------------------------------------------------------- builders


@pytest.fixture
def owner(db_session):
    _bind_factories(db_session)
    user = make_user(db_session, role=UserRole.organizer)
    db_session.add(
        Module(
            slug=f"lock-{uuid.uuid4().hex[:8]}",
            name="Lock Module",
            default_capacity=20,
            duration_minutes=60,
            session_count=1,
            family_key="lockfam",
        )
    )
    db_session.flush()
    return user


def _event(db, owner, *, module=True, venue_code="2468"):
    slug = (
        db.query(Module.slug).filter(Module.family_key == "lockfam").scalar()
        if module
        else None
    )
    start = NOW() - timedelta(days=1)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Lock Event",
        start_date=start,
        end_date=start + timedelta(days=4),
        module_slug=slug,
        venue_code=venue_code,
    )
    db.add(event)
    db.flush()
    return event


def _orientation(db, event, *, hours_from_now=-2):
    start = NOW() + timedelta(hours=hours_from_now)
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        capacity=30,
        slot_type=SlotType.ORIENTATION,
        date=start.date(),
    )
    db.add(slot)
    db.flush()
    return slot


def _volunteer(db, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"lock-{uuid.uuid4().hex[:10]}@example.com",
        first_name="Lock",
        last_name="Vol",
    )
    db.add(v)
    db.flush()
    return v


def _signup(db, slot, status=SignupStatus.confirmed, *, checked_in_at=None, volunteer=None):
    vol = volunteer or _volunteer(db)
    if status == SignupStatus.checked_in and checked_in_at is None:
        checked_in_at = NOW() - timedelta(minutes=30)
    s = Signup(
        id=uuid.uuid4(),
        volunteer_id=vol.id,
        slot_id=slot.id,
        status=status,
        checked_in_at=checked_in_at,
    )
    db.add(s)
    db.flush()
    return s


def _shift(db, event, offsets_hours, *, name="Shift 1"):
    shift = make_shift(db, event.id, name=name, capacity=10)
    sessions = []
    for i, off in enumerate(offsets_hours):
        start = NOW() + timedelta(hours=off)
        s = Slot(
            event_id=event.id,
            shift_id=shift.id,
            sort_order=i,
            name=f"Day {i + 1}",
            slot_type=SlotType.PERIOD,
            capacity=10,
            current_count=0,
            start_time=start,
            end_time=start + timedelta(hours=1),
            date=start.date(),
        )
        db.add(s)
        sessions.append(s)
    db.flush()
    return shift, sessions


def _commit(db, shift, status=SignupStatus.confirmed, volunteer=None):
    return book_shift(db, shift, volunteer or VolunteerFactory(), status=status)


def _row(db, shift_signup, session):
    return (
        db.query(SessionAttendance)
        .filter(
            SessionAttendance.shift_signup_id == shift_signup.id,
            SessionAttendance.slot_id == session.id,
        )
        .one_or_none()
    )


def _audits(db, *, entity_id=None, action=None, via=None):
    q = db.query(AuditLog)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == str(entity_id))
    if action is not None:
        q = q.filter(AuditLog.action == action)
    rows = q.all()
    if via is not None:
        rows = [r for r in rows if (r.extra or {}).get("via") == via]
    return rows


def _active_credits(db, email):
    return (
        db.query(OrientationCredit)
        .filter(
            OrientationCredit.volunteer_email == email,
            OrientationCredit.revoked_at.is_(None),
        )
        .all()
    )


# ------------------------------------------------------- closing: orientation


class TestCloseOrientation:
    def test_default_decisions_cover_every_seated_booking(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        pending = _signup(db_session, slot, SignupStatus.pending)
        confirmed = _signup(db_session, slot, SignupStatus.confirmed)
        here = _signup(db_session, slot, SignupStatus.checked_in)
        waitlisted = _signup(db_session, slot, SignupStatus.waitlisted)
        cancelled = _signup(db_session, slot, SignupStatus.cancelled)
        here_at = here.checked_in_at

        result = close_slot(db_session, slot.id, owner.id, [], [])

        assert result is slot
        assert slot.closed_at is not None
        assert slot.closed_by == owner.id
        assert pending.status == SignupStatus.no_show
        assert confirmed.status == SignupStatus.no_show
        assert here.status == SignupStatus.attended
        assert here.checked_in_at == here_at
        # No seat, so no result: never touched.
        assert waitlisted.status == SignupStatus.waitlisted
        assert cancelled.status == SignupStatus.cancelled
        assert len(_audits(db_session, entity_id=slot.id, action="slot_close")) == 1
        # pending -> no_show directly: no autoconfirm step on the way down.
        assert _audits(db_session, entity_id=pending.id, via="close_slot_autoconfirm") == []

    @pytest.mark.parametrize("status", [SignupStatus.pending, SignupStatus.confirmed])
    def test_pending_and_confirmed_close_out_identically(self, db_session, owner, status):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        named = _signup(db_session, slot, status)
        default = _signup(db_session, slot, status)

        close_slot(db_session, slot.id, owner.id, [named.id], [])

        assert named.status == SignupStatus.attended
        assert default.status == SignupStatus.no_show
        autoconfirms = _audits(db_session, entity_id=named.id, via="close_slot_autoconfirm")
        assert len(autoconfirms) == (1 if status == SignupStatus.pending else 0)

    def test_explicit_decisions_win_over_check_in_state(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        walk_in = _signup(db_session, slot, SignupStatus.confirmed)
        left_early = _signup(db_session, slot, SignupStatus.checked_in)
        both = _signup(db_session, slot, SignupStatus.confirmed)

        close_slot(
            db_session, slot.id, owner.id,
            [walk_in.id, both.id], [left_early.id, both.id],
        )

        assert walk_in.status == SignupStatus.attended
        assert walk_in.checked_in_at is None
        assert left_early.status == SignupStatus.no_show
        # The check-in time is kept on the record; reopen clears it.
        assert left_early.checked_in_at is not None
        # Named in both lists: attended wins.
        assert both.status == SignupStatus.attended

    def test_a_stray_no_show_on_an_open_slot_stays_without_a_transition(
        self, db_session, owner
    ):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        stray = _signup(db_session, slot, SignupStatus.no_show)

        close_slot(db_session, slot.id, owner.id, [], [])

        assert stray.status == SignupStatus.no_show
        assert _audits(db_session, entity_id=stray.id, action="transition") == []

    def test_an_empty_slot_closes_and_never_completes_the_event(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        _signup(db_session, slot, SignupStatus.waitlisted)

        close_slot(db_session, slot.id, owner.id, [], [])

        assert slot.closed_at is not None
        assert event.completed_at is None

    def test_closing_twice_raises(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        close_slot(db_session, slot.id, owner.id, [], [])
        first_closed_at = slot.closed_at

        with pytest.raises(SlotClosedError) as exc:
            close_slot(db_session, slot.id, owner.id, [], [s.id])

        assert exc.value.slot_id == slot.id
        assert s.status == SignupStatus.attended
        assert slot.closed_at == first_closed_at

    @pytest.mark.parametrize(
        "which", ["other_slot", "waitlisted", "cancelled", "unknown"]
    )
    def test_an_id_not_seated_on_the_slot_raises_lookup(self, db_session, owner, which):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other = _orientation(db_session, event, hours_from_now=-5)
        _signup(db_session, slot, SignupStatus.confirmed)
        bad = {
            "other_slot": lambda: _signup(db_session, other).id,
            "waitlisted": lambda: _signup(db_session, slot, SignupStatus.waitlisted).id,
            "cancelled": lambda: _signup(db_session, slot, SignupStatus.cancelled).id,
            "unknown": uuid.uuid4,
        }[which]()

        with pytest.raises(LookupError):
            close_slot(db_session, slot.id, owner.id, [], [bad])

    def test_unknown_slot_raises_lookup(self, db_session, owner):
        with pytest.raises(LookupError):
            close_slot(db_session, uuid.uuid4(), owner.id, [], [])
        with pytest.raises(LookupError):
            reopen_slot(db_session, uuid.uuid4(), owner.id)

    def test_archived_quarter_refuses_close_and_reopen(self, db_session, owner):
        _bind_factories(db_session)
        AcademicQuarterFactory._meta.sqlalchemy_session = db_session
        quarter = AcademicQuarterFactory(
            season=models.Quarter.WINTER, year=2023,
            start_date=date(2023, 1, 9), end_date=date(2023, 3, 17),
        )
        quarter.archived_at = NOW()
        event = _event(db_session, owner)
        event.quarter_id = quarter.id
        slot = _orientation(db_session, event)
        db_session.flush()
        db_session.expire(event, ["academic_quarter"])

        for call in (
            lambda: close_slot(db_session, slot.id, owner.id, [], []),
            lambda: reopen_slot(db_session, slot.id, owner.id),
            lambda: close_event(db_session, event.id, owner.id, [], []),
            lambda: reopen_event(db_session, event.id, owner.id),
        ):
            with pytest.raises(HTTPException) as exc:
                call()
            assert exc.value.status_code == 422
            assert exc.value.detail["code"] == "QUARTER_READONLY"
            assert "archived" in exc.value.detail["message"]
        assert slot.closed_at is None

    def test_an_ended_but_not_archived_quarter_still_closes(self, db_session, owner):
        AcademicQuarterFactory._meta.sqlalchemy_session = db_session
        quarter = AcademicQuarterFactory(
            season=models.Quarter.FALL, year=2022,
            start_date=date(2022, 9, 19), end_date=date(2022, 12, 9),
        )
        event = _event(db_session, owner)
        event.quarter_id = quarter.id
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        db_session.flush()

        close_slot(db_session, slot.id, owner.id, [], [])
        assert s.status == SignupStatus.attended
        # And the credit records the quarter it was earned in.
        (credit,) = _active_credits(db_session, s.volunteer.email)
        assert credit.quarter_id == quarter.id


# ---------------------------------------------------------- closing: sessions


class TestCloseSession:
    def test_default_decisions_from_the_attendance_rows(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        here = _commit(db_session, shift)
        absent = _commit(db_session, shift)
        pending = _commit(db_session, shift, SignupStatus.pending)
        waitlisted = _commit(db_session, shift, SignupStatus.waitlisted)
        cancelled = _commit(db_session, shift, SignupStatus.cancelled)
        check_in_session(db_session, here.id, tue.id, owner.id)
        here_at = _row(db_session, here, tue).checked_in_at

        close_slot(db_session, tue.id, owner.id, [], [])

        assert _row(db_session, here, tue).status == SignupStatus.attended
        assert _row(db_session, here, tue).checked_in_at == here_at
        assert _row(db_session, absent, tue).status == SignupStatus.no_show
        assert _row(db_session, pending, tue).status == SignupStatus.no_show
        # pending -> no_show leaves the commitment itself pending.
        assert pending.status == SignupStatus.pending
        assert _row(db_session, waitlisted, tue) is None
        assert _row(db_session, cancelled, tue) is None
        assert tue.closed_at is not None

    def test_pending_marked_attended_is_autoconfirmed(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        pending = _commit(db_session, shift, SignupStatus.pending)

        close_slot(db_session, tue.id, owner.id, [pending.id], [])

        assert pending.status == SignupStatus.confirmed
        assert _row(db_session, pending, tue).status == SignupStatus.attended
        assert len(_audits(db_session, entity_id=pending.id, via="close_slot_autoconfirm")) == 1

    def test_a_shift_signup_from_another_shift_is_lookup(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        other_shift, _ = _shift(db_session, event, [-3], name="Shift 2")
        stranger = _commit(db_session, other_shift)

        with pytest.raises(LookupError):
            close_slot(db_session, tue.id, owner.id, [stranger.id], [])

    def test_closing_one_session_leaves_the_other_open(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-3, 40])
        c = _commit(db_session, shift)

        close_slot(db_session, tue.id, owner.id, [], [])

        assert tue.closed_at is not None and thu.closed_at is None
        assert _row(db_session, c, thu) is None
        assert event.completed_at is None


# ------------------------------------------------------------------- taps


class TestTapsOnOpenSlots:
    def test_undo_on_pending_or_confirmed_is_a_no_op(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        for status in (SignupStatus.pending, SignupStatus.confirmed):
            s = _signup(db_session, slot, status)
            assert undo_check_in(db_session, s.id, owner.id).status == status
            assert _audits(db_session, entity_id=s.id, action="transition") == []

    def test_check_in_then_undo_round_trips(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.pending)

        check_in_signup(db_session, s.id, owner.id)
        assert s.status == SignupStatus.checked_in and s.checked_in_at is not None
        undo_check_in(db_session, s.id, owner.id)
        assert s.status == SignupStatus.confirmed and s.checked_in_at is None

    @pytest.mark.parametrize("status", [SignupStatus.waitlisted, SignupStatus.cancelled])
    def test_no_seat_no_check_in(self, db_session, owner, status):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, status)
        with pytest.raises(InvalidTransitionError):
            check_in_signup(db_session, s.id, owner.id)

    def test_unknown_signup_is_lookup(self, db_session, owner):
        with pytest.raises(LookupError):
            check_in_signup(db_session, uuid.uuid4(), owner.id)

    def test_session_tap_on_a_stray_attended_row_refuses(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        db_session.add(
            SessionAttendance(shift_signup_id=c.id, slot_id=tue.id, status=SignupStatus.attended)
        )
        db_session.flush()

        with pytest.raises(InvalidTransitionError) as exc:
            check_in_session(db_session, c.id, tue.id, owner.id)
        assert exc.value.from_status == SignupStatus.attended

    def test_session_tap_on_a_stray_no_show_checks_in(self, db_session, owner):
        """Issue #189: the QR tells a volunteer with a stray no-show to ask
        staff, so the staff tap has to fix it."""
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        row = SessionAttendance(
            shift_signup_id=c.id, slot_id=tue.id, status=SignupStatus.no_show
        )
        db_session.add(row)
        db_session.flush()

        check_in_session(db_session, c.id, tue.id, owner.id)

        assert row.status == SignupStatus.checked_in
        assert row.checked_in_at is not None
        assert [
            (a.extra["from"], a.extra["to"])
            for a in _audits(db_session, entity_id=c.id, action="transition")
        ] == [("no_show", "checked_in")]

    def test_session_check_in_is_idempotent_and_undo_deletes(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift, SignupStatus.pending)

        check_in_session(db_session, c.id, tue.id, owner.id)
        check_in_session(db_session, c.id, tue.id, owner.id)
        assert c.status == SignupStatus.confirmed
        assert len(_audits(db_session, entity_id=c.id, via="organizer")) == 1

        undo_session_check_in(db_session, c.id, tue.id, owner.id)
        undo_session_check_in(db_session, c.id, tue.id, owner.id)
        assert _row(db_session, c, tue) is None
        assert len(_audits(db_session, entity_id=c.id, via="organizer_undo")) == 1

    def test_a_session_of_another_shift_is_lookup(self, db_session, owner):
        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [-3])
        _, (elsewhere,) = _shift(db_session, event, [-3], name="Other")
        c = _commit(db_session, shift)
        with pytest.raises(LookupError):
            check_in_session(db_session, c.id, elsewhere.id, owner.id)
        with pytest.raises(LookupError):
            check_in_session(db_session, uuid.uuid4(), elsewhere.id, owner.id)


class TestTapsOnClosedSlots:
    def test_service_taps_raise_slot_closed(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.confirmed)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        close_slot(db_session, slot.id, owner.id, [], [])
        close_slot(db_session, tue.id, owner.id, [], [])

        for call in (
            lambda: check_in_signup(db_session, s.id, owner.id),
            lambda: undo_check_in(db_session, s.id, owner.id),
            lambda: check_in_session(db_session, c.id, tue.id, owner.id),
            lambda: undo_session_check_in(db_session, c.id, tue.id, owner.id),
        ):
            with pytest.raises(SlotClosedError):
                call()
        assert s.status == SignupStatus.no_show
        assert _row(db_session, c, tue).status == SignupStatus.no_show

    def test_http_taps_answer_409_slot_closed(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [])
        close_slot(db_session, tue.id, owner.id, [], [])
        db_session.commit()
        headers = auth_headers(client, owner)

        for url in (
            f"/api/v1/signups/{s.id}/check-in",
            f"/api/v1/signups/{s.id}/undo-check-in",
            f"/api/v1/shift-signups/{c.id}/sessions/{tue.id}/check-in",
            f"/api/v1/shift-signups/{c.id}/sessions/{tue.id}/undo-check-in",
        ):
            resp = client.post(url, headers=headers)
            assert resp.status_code == 409, (url, resp.text)
            body = resp.json()
            assert body["code"] == "SLOT_CLOSED"
            assert body["detail"] == "This slot is closed. Reopen it to change attendance."

        db_session.expire_all()
        assert s.status == SignupStatus.attended
        assert _row(db_session, c, tue).status == SignupStatus.attended


# ----------------------------------------------------------------- reopen


class TestReopen:
    def test_orientation_reopen_converts_back_and_keeps_check_in_time(
        self, db_session, owner
    ):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        here = _signup(db_session, slot, SignupStatus.checked_in)
        left = _signup(db_session, slot, SignupStatus.checked_in)
        absent = _signup(db_session, slot, SignupStatus.pending)
        here_at = here.checked_in_at
        close_slot(db_session, slot.id, owner.id, [], [left.id])

        reopen_slot(db_session, slot.id, owner.id)

        assert slot.closed_at is None and slot.closed_by is None
        assert here.status == SignupStatus.checked_in
        assert here.checked_in_at == here_at
        assert left.status == SignupStatus.confirmed
        assert left.checked_in_at is None
        # pending was closed out as no_show; it comes back as plain confirmed.
        assert absent.status == SignupStatus.confirmed
        assert len(_audits(db_session, entity_id=slot.id, action="slot_reopen")) == 1
        assert len(_audits(db_session, entity_id=here.id, via="reopen_slot")) == 1

    def test_session_reopen_converts_back_and_deletes_no_shows(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        here = _commit(db_session, shift)
        absent = _commit(db_session, shift)
        check_in_session(db_session, here.id, tue.id, owner.id)
        here_at = _row(db_session, here, tue).checked_in_at
        close_slot(db_session, tue.id, owner.id, [], [])

        reopen_slot(db_session, tue.id, owner.id)

        row = _row(db_session, here, tue)
        assert row.status == SignupStatus.checked_in
        assert row.checked_in_at == here_at
        assert _row(db_session, absent, tue) is None
        assert tue.closed_at is None
        vias = [a.extra for a in _audits(db_session, via="reopen_slot", action="transition")]
        assert {(e["from"], e["to"]) for e in vias} == {
            ("attended", "checked_in"), ("no_show", None),
        }

    def test_reopen_on_an_open_slot_is_a_no_op(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        _signup(db_session, slot, SignupStatus.checked_in)

        assert reopen_slot(db_session, slot.id, owner.id) is slot
        assert _audits(db_session, action="slot_reopen") == []

    def test_reopen_tap_reclose_turns_a_no_show_into_attended(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        late = _signup(db_session, slot, SignupStatus.confirmed)
        close_slot(db_session, slot.id, owner.id, [], [])
        assert late.status == SignupStatus.no_show

        reopen_slot(db_session, slot.id, owner.id)
        check_in_signup(db_session, late.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [])

        assert late.status == SignupStatus.attended
        assert len(_active_credits(db_session, late.volunteer.email)) == 1

    def test_session_reopen_tap_reclose(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        late = _commit(db_session, shift)
        close_slot(db_session, tue.id, owner.id, [], [])

        reopen_slot(db_session, tue.id, owner.id)
        check_in_session(db_session, late.id, tue.id, owner.id)
        close_slot(db_session, tue.id, owner.id, [], [])

        assert _row(db_session, late, tue).status == SignupStatus.attended

    def test_repeated_close_reopen_cycles_stay_consistent(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        flip = _signup(db_session, slot, SignupStatus.checked_in)
        steady = _signup(db_session, slot, SignupStatus.checked_in)

        for i in range(4):
            no_show = [flip.id] if i % 2 else []
            close_slot(db_session, slot.id, owner.id, [], no_show)
            assert flip.status == (SignupStatus.no_show if i % 2 else SignupStatus.attended)
            assert steady.status == SignupStatus.attended
            assert event.completed_at is not None
            assert len(_active_credits(db_session, steady.volunteer.email)) == 1
            assert len(_active_credits(db_session, flip.volunteer.email)) == (0 if i % 2 else 1)
            reopen_slot(db_session, slot.id, owner.id)
            assert event.completed_at is None
            assert steady.status == SignupStatus.checked_in
            if i % 2:
                check_in_signup(db_session, flip.id, owner.id)

        assert len(_audits(db_session, entity_id=slot.id, action="slot_close")) == 4
        assert len(_audits(db_session, entity_id=slot.id, action="slot_reopen")) == 4
        # One grant for the steady attendee across four closes.
        assert db_session.query(OrientationCredit).filter(
            OrientationCredit.source_signup_id == steady.id
        ).count() == 1


# ---------------------------------------------------------------- credits


class TestOrientationCredit:
    def test_close_grants_with_its_source_signup(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)

        close_slot(db_session, slot.id, owner.id, [], [])

        (credit,) = _active_credits(db_session, s.volunteer.email)
        assert credit.source == OrientationCreditSource.attendance
        assert credit.source_signup_id == s.id
        assert credit.family_key == "lockfam"
        assert credit.granted_by_user_id == owner.id
        assert credit.notes == "auto-granted on close_slot"
        grants = _audits(db_session, entity_id=credit.id, action="orientation_credit_grant")
        assert grants[0].extra["signup_id"] == str(s.id)

    def test_reclosing_as_no_show_revokes_only_that_signups_credit(
        self, db_session, owner
    ):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        wrong = _signup(db_session, slot, SignupStatus.checked_in)
        right = _signup(db_session, slot, SignupStatus.checked_in)
        close_slot(db_session, slot.id, owner.id, [], [])

        reopen_slot(db_session, slot.id, owner.id)
        # Reopen leaves credit alone until the next close.
        assert len(_active_credits(db_session, wrong.volunteer.email)) == 1
        close_slot(db_session, slot.id, owner.id, [], [wrong.id])

        assert _active_credits(db_session, wrong.volunteer.email) == []
        assert len(_active_credits(db_session, right.volunteer.email)) == 1
        (revoked,) = (
            db_session.query(OrientationCredit)
            .filter(OrientationCredit.source_signup_id == wrong.id)
            .all()
        )
        assert revoked.revoked_at is not None
        assert len(_audits(db_session, entity_id=revoked.id, action="orientation_credit_revoke")) == 1

    def test_a_hand_granted_credit_is_never_auto_revoked(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        vol = _volunteer(db_session)
        hand = grant_orientation_credit(db_session, vol.email, "lockfam", granted_by_user_id=owner.id)
        s = _signup(db_session, slot, SignupStatus.checked_in, volunteer=vol)

        close_slot(db_session, slot.id, owner.id, [], [])
        # Deduped: they already had credit, so no attendance row.
        assert _active_credits(db_session, vol.email) == [hand]

        reopen_slot(db_session, slot.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [s.id])

        assert _active_credits(db_session, vol.email) == [hand]
        assert hand.source_signup_id is None

    def test_a_no_show_with_no_credit_revokes_nothing(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.confirmed)

        close_slot(db_session, slot.id, owner.id, [], [])

        assert _audits(db_session, action="orientation_credit_revoke") == []
        assert _active_credits(db_session, s.volunteer.email) == []

    def test_moduleless_event_closes_without_credit(self, db_session, owner):
        event = _event(db_session, owner, module=False)
        slot = _orientation(db_session, event)
        _signup(db_session, slot, SignupStatus.checked_in)

        close_slot(db_session, slot.id, owner.id, [], [])

        assert db_session.query(OrientationCredit).count() == 0


# -------------------------------------------------------------- end event


class TestCloseAndReopenEvent:
    def test_close_event_skips_future_and_already_closed_slots(self, db_session, owner):
        event = _event(db_session, owner)
        done = _orientation(db_session, event, hours_from_now=-30)
        past = _orientation(db_session, event, hours_from_now=-2)
        future = _orientation(db_session, event, hours_from_now=30)
        shift, (tue, thu) = _shift(db_session, event, [-3, 40])
        d = _signup(db_session, done, SignupStatus.checked_in)
        p = _signup(db_session, past, SignupStatus.confirmed)
        f = _signup(db_session, future, SignupStatus.confirmed)
        c = _commit(db_session, shift)
        close_slot(db_session, done.id, owner.id, [], [d.id])
        done_closed_at = done.closed_at

        closed = close_event(db_session, event.id, owner.id, [p.id, c.id], [])

        assert {s.id for s in closed} == {past.id, tue.id}
        assert done.closed_at == done_closed_at
        assert d.status == SignupStatus.no_show
        assert p.status == SignupStatus.attended
        assert f.status == SignupStatus.confirmed and future.closed_at is None
        # A shift id applies to the session being closed, not the future one.
        assert _row(db_session, c, tue).status == SignupStatus.attended
        assert _row(db_session, c, thu) is None and thu.closed_at is None
        assert event.completed_at is None
        vias = {a.extra["via"] for a in _audits(db_session, action="slot_close")}
        assert vias == {"close_slot", "close_event"}

    def test_close_event_with_an_id_only_on_a_future_slot_is_lookup(
        self, db_session, owner
    ):
        event = _event(db_session, owner)
        future = _orientation(db_session, event, hours_from_now=30)
        f = _signup(db_session, future)
        with pytest.raises(LookupError):
            close_event(db_session, event.id, owner.id, [], [f.id])

    def test_close_event_honours_an_explicit_now(self, db_session, owner):
        event = _event(db_session, owner)
        future = _orientation(db_session, event, hours_from_now=30)
        _signup(db_session, future)

        closed = close_event(
            db_session, event.id, owner.id, [], [], now=NOW() + timedelta(days=2)
        )
        assert closed == [future]

    def test_unknown_event_is_lookup(self, db_session, owner):
        with pytest.raises(LookupError):
            close_event(db_session, uuid.uuid4(), owner.id, [], [])
        with pytest.raises(LookupError):
            reopen_event(db_session, uuid.uuid4(), owner.id)

    def test_reopen_event_works_without_full_completion(self, db_session, owner):
        event = _event(db_session, owner)
        a = _orientation(db_session, event, hours_from_now=-5)
        b = _orientation(db_session, event, hours_from_now=-2)
        sa = _signup(db_session, a, SignupStatus.checked_in)
        _signup(db_session, b)
        close_slot(db_session, a.id, owner.id, [], [])
        assert event.completed_at is None

        reopened = reopen_event(db_session, event.id, owner.id)

        assert reopened == [a]
        assert a.closed_at is None
        assert sa.status == SignupStatus.checked_in
        assert len(_audits(db_session, entity_id=sa.id, via="reopen_event")) == 1

    def test_completed_at_tracks_the_closed_switches(self, db_session, owner):
        event = _event(db_session, owner)
        a = _orientation(db_session, event, hours_from_now=-5)
        _orientation(db_session, event, hours_from_now=-4)  # nobody booked
        waitlist_only = _orientation(db_session, event, hours_from_now=-3)
        _signup(db_session, waitlist_only, SignupStatus.waitlisted)
        shift, (tue,) = _shift(db_session, event, [-2])
        _commit(db_session, shift)
        _signup(db_session, a, SignupStatus.checked_in)

        close_slot(db_session, a.id, owner.id, [], [])
        assert event.completed_at is None  # the session is still open

        close_slot(db_session, tue.id, owner.id, [], [])
        stamped = event.completed_at
        assert stamped is not None

        # Refreshing a completed event keeps the first stamp.
        refresh_event_completion(db_session, event.id)
        close_event(db_session, event.id, owner.id, [], [])
        assert event.completed_at == stamped

        reopen_slot(db_session, tue.id, owner.id)
        assert event.completed_at is None

    def test_an_event_with_no_seated_booking_never_completes(self, db_session, owner):
        event = _event(db_session, owner)
        _orientation(db_session, event)
        close_event(db_session, event.id, owner.id, [], [])
        assert event.completed_at is None


# --------------------------------------------------------- volunteer QR flow


class TestQrSelfCheckInOnClosedSlot:
    def _closed_slot_in_window(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=0)
        vol = _volunteer(db_session)
        s = _signup(db_session, slot, SignupStatus.confirmed, volunteer=vol)
        slot.closed_at = NOW()
        db_session.flush()
        return event, slot, vol, s

    def test_window_state_is_closed_whatever_the_clock_says(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=0)
        assert window_state(slot, NOW())[0] == "open"
        slot.closed_at = NOW()
        assert window_state(slot, NOW())[0] == "closed"
        assert window_state(slot, NOW() - timedelta(hours=3))[0] == "closed"

    def test_lookup_reports_closed_and_every_check_in_path_refuses(
        self, db_session, owner
    ):
        event, slot, vol, s = self._closed_slot_in_window(db_session, owner)

        _, options = lookup_check_in_options(db_session, event.id, vol.email, "2468")
        assert [o.window_state for o in options] == ["closed"]

        with pytest.raises(SlotClosedError):
            check_in_selected(db_session, event.id, vol.email, "2468", [s.id])
        with pytest.raises(CheckInWindowError):
            event_check_in_by_email(db_session, event.id, vol.email, "2468")
        with pytest.raises(CheckInWindowError):
            self_check_in(db_session, event.id, s.id, "2468", None, now=slot.start_time)
        assert s.status == SignupStatus.confirmed

    def test_the_qr_lookup_endpoint_says_closed(self, client, db_session, owner):
        event, slot, vol, s = self._closed_slot_in_window(db_session, owner)
        db_session.commit()

        resp = client.post(
            f"/api/v1/events/{event.id}/check-in-lookup",
            json={"email": vol.email, "venue_code": "2468"},
        )
        assert resp.status_code == 200, resp.text
        assert "closed" in resp.text

    def test_the_public_slot_list_carries_closed_at(self, client, db_session, owner):
        # The QR page's pre-lookup schedule reads it so a staff-closed slot
        # doesn't say "Open now".
        event, slot, _vol, _s = self._closed_slot_in_window(db_session, owner)
        event.visibility = "public"
        open_slot = _orientation(db_session, event, hours_from_now=1)
        db_session.commit()

        resp = client.get(f"/api/v1/slots/?event_id={event.id}")
        assert resp.status_code == 200, resp.text
        by_id = {row["id"]: row for row in resp.json()}
        assert by_id[str(slot.id)]["closed_at"] is not None
        assert by_id[str(open_slot.id)]["closed_at"] is None


# ------------------------------------------------------------ mark_present


class TestMarkPresent:
    def test_orientation_present_and_absent(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.pending)

        mark_present(db_session, slot.id, s.id, True, owner.id, "copilot")
        assert s.status == SignupStatus.checked_in
        mark_present(db_session, slot.id, s.id, False, owner.id, "copilot")
        assert s.status == SignupStatus.confirmed
        assert db_session.query(OrientationCredit).count() == 0

    def test_session_present_and_absent(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)

        mark_present(db_session, tue.id, c.id, True, owner.id, "copilot")
        assert _row(db_session, c, tue).status == SignupStatus.checked_in
        mark_present(db_session, tue.id, c.id, False, owner.id, "copilot")
        assert _row(db_session, c, tue) is None

    def test_closed_slot_raises(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot)
        close_slot(db_session, slot.id, owner.id, [], [])
        with pytest.raises(SlotClosedError):
            mark_present(db_session, slot.id, s.id, True, owner.id, "copilot")

    def test_unknown_slot_and_foreign_signup_are_lookup(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other = _orientation(db_session, event, hours_from_now=-6)
        foreign = _signup(db_session, other)
        with pytest.raises(LookupError):
            mark_present(db_session, uuid.uuid4(), foreign.id, True, owner.id, "x")
        with pytest.raises(LookupError):
            mark_present(db_session, slot.id, foreign.id, True, owner.id, "x")
        with pytest.raises(LookupError):
            mark_present(db_session, slot.id, uuid.uuid4(), True, owner.id, "x")


# ------------------------------------------------- closing before the start


class TestCloseBeforeStart:
    """No-shows only exist for a session that has begun: Kim's bug started
    with Thursday's sessions being closed on Tuesday."""

    def test_a_future_slot_cannot_be_closed(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=24)
        signup = _signup(db_session, slot, SignupStatus.confirmed)

        with pytest.raises(SlotNotStartedError) as exc:
            close_slot(db_session, slot.id, owner.id, [], [])
        assert exc.value.slot_id == slot.id

        db_session.refresh(slot)
        db_session.refresh(signup)
        assert slot.closed_at is None
        assert signup.status == SignupStatus.confirmed

    def test_a_future_session_cannot_be_closed(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-2, 48])
        _commit(db_session, shift)

        close_slot(db_session, tue.id, owner.id, [], [])
        with pytest.raises(SlotNotStartedError):
            close_slot(db_session, thu.id, owner.id, [], [])
        db_session.refresh(thu)
        assert thu.closed_at is None

    def test_a_closed_future_slot_reports_closed_first(self, db_session, owner):
        # Can only arise from old data; SLOT_CLOSED is the more useful answer.
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=24)
        slot.closed_at = NOW()
        db_session.flush()
        with pytest.raises(SlotClosedError):
            close_slot(db_session, slot.id, owner.id, [], [])

    def test_http_answers_409_slot_not_started(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=24)
        _signup(db_session, slot, SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [], "no_show": []},
            headers=auth_headers(client, owner),
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        # The global handler flattens the detail dict.
        assert body["code"] == "SLOT_NOT_STARTED"
        assert body["detail"] == (
            "This session hasn't started yet — you can close it once it starts."
        )
        db_session.expire_all()
        assert db_session.get(Slot, slot.id).closed_at is None


# -------------------------------------------------------------------- HTTP


class TestHttp:
    def test_close_then_reopen_slot_endpoints(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        here = _signup(db_session, slot, SignupStatus.checked_in)
        pending = _signup(db_session, slot, SignupStatus.pending)
        db_session.commit()
        headers = auth_headers(client, owner)

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [], "no_show": []}, headers=headers,
        )
        assert resp.status_code == 200, resp.text
        rows = {r["signup_id"]: r for r in resp.json()["rows"]}
        assert rows[str(here.id)]["status"] == "attended"
        assert rows[str(pending.id)]["status"] == "no_show"
        assert all(r["slot_closed_at"] for r in rows.values())

        again = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [], "no_show": []}, headers=headers,
        )
        assert again.status_code == 409
        assert again.json()["code"] == "SLOT_CLOSED"

        resp = client.post(f"/api/v1/slots/{slot.id}/reopen", headers=headers)
        assert resp.status_code == 200, resp.text
        rows = {r["signup_id"]: r for r in resp.json()["rows"]}
        assert rows[str(here.id)]["status"] == "checked_in"
        assert rows[str(pending.id)]["status"] == "confirmed"
        assert all(r["slot_closed_at"] is None for r in rows.values())

        # Idempotent.
        assert client.post(f"/api/v1/slots/{slot.id}/reopen", headers=headers).status_code == 200

    def test_close_with_a_foreign_id_is_404_and_rolls_back(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other = _orientation(db_session, event, hours_from_now=-6)
        mine = _signup(db_session, slot, SignupStatus.checked_in)
        foreign = _signup(db_session, other)
        db_session.commit()

        resp = client.post(
            f"/api/v1/slots/{slot.id}/resolve",
            json={"attended": [str(mine.id)], "no_show": [str(foreign.id)]},
            headers=auth_headers(client, owner),
        )
        assert resp.status_code == 404
        db_session.expire_all()
        assert mine.status == SignupStatus.checked_in
        assert slot.closed_at is None

    def test_reopen_unknown_slot_404_and_participant_403(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        participant = make_user(db_session, role=UserRole.participant)
        db_session.commit()

        resp = client.post(
            f"/api/v1/slots/{uuid.uuid4()}/reopen", headers=auth_headers(client, owner)
        )
        assert resp.status_code == 404
        resp = client.post(
            f"/api/v1/slots/{slot.id}/reopen", headers=auth_headers(client, participant)
        )
        assert resp.status_code == 403

    def test_session_rows_carry_slot_closed_at(self, client, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-3, 40])
        _commit(db_session, shift)
        close_slot(db_session, tue.id, owner.id, [], [])
        db_session.commit()

        resp = client.get(
            f"/api/v1/events/{event.id}/roster", headers=auth_headers(client, owner)
        )
        assert resp.status_code == 200
        by_slot = {r["slot_id"]: r for r in resp.json()["rows"]}
        assert by_slot[str(tue.id)]["slot_closed_at"] is not None
        assert by_slot[str(tue.id)]["status"] == "no_show"
        assert by_slot[str(thu.id)]["slot_closed_at"] is None
        assert by_slot[str(thu.id)]["status"] == "confirmed"


def test_lock_helpers_are_the_only_writers_of_final_statuses():
    """Rule 3 as a table check: no whitelist edge reaches attended/no_show."""
    for src, targets in cis.ALLOWED_TRANSITIONS.items():
        assert SignupStatus.attended not in targets, src
        assert SignupStatus.no_show not in targets, src


# ------------------------------------------- edges around the tap endpoints


class TestTapEndpointEdges:
    def test_session_check_in_and_undo_happy_paths(self, client, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift, SignupStatus.pending)
        db_session.commit()
        headers = auth_headers(client, owner)
        base = f"/api/v1/shift-signups/{c.id}/sessions/{tue.id}"

        resp = client.post(f"{base}/check-in", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "confirmed"
        db_session.expire_all()
        assert _row(db_session, c, tue).status == SignupStatus.checked_in

        resp = client.post(f"{base}/undo-check-in", headers=headers)
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert _row(db_session, c, tue) is None

    def test_session_endpoints_404_and_409(self, client, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        _, (elsewhere,) = _shift(db_session, event, [-3], name="Other")
        c = _commit(db_session, shift)
        wl = _commit(db_session, shift, SignupStatus.waitlisted)
        db_session.commit()
        headers = auth_headers(client, owner)

        for verb in ("check-in", "undo-check-in"):
            resp = client.post(
                f"/api/v1/shift-signups/{uuid.uuid4()}/sessions/{tue.id}/{verb}",
                headers=headers,
            )
            assert resp.status_code == 404
            resp = client.post(
                f"/api/v1/shift-signups/{c.id}/sessions/{elsewhere.id}/{verb}",
                headers=headers,
            )
            assert resp.status_code == 404

        resp = client.post(
            f"/api/v1/shift-signups/{wl.id}/sessions/{tue.id}/check-in", headers=headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_TRANSITION"

    def test_self_check_in_endpoint_409_and_404(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=0)
        wl = _signup(db_session, slot, SignupStatus.waitlisted)
        db_session.commit()

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(wl.id), "venue_code": "2468"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_TRANSITION"

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(uuid.uuid4()), "venue_code": "2468"},
        )
        assert resp.status_code == 404

    def test_self_check_in_on_a_closed_slot_is_outside_the_window(
        self, client, db_session, owner
    ):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=0)
        s = _signup(db_session, slot)
        slot.closed_at = NOW()
        db_session.commit()

        resp = client.post(
            f"/api/v1/events/{event.id}/self-check-in",
            json={"signup_id": str(s.id), "venue_code": "2468"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "OUTSIDE_WINDOW"

    def test_get_signup_for_self_check_in_page(self, client, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot)
        db_session.commit()

        resp = client.get(f"/api/v1/signups/{s.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["event_id"] == str(event.id)
        assert client.get(f"/api/v1/signups/{uuid.uuid4()}").status_code == 404

    def test_resolve_and_lookup_unknown_event_404(self, client, db_session, owner):
        db_session.commit()
        headers = auth_headers(client, owner)
        resp = client.post(
            f"/api/v1/events/{uuid.uuid4()}/resolve",
            json={"attended": [], "no_show": []}, headers=headers,
        )
        assert resp.status_code == 404
        resp = client.post(
            f"/api/v1/events/{uuid.uuid4()}/check-in-lookup",
            json={"email": "nobody@example.com", "venue_code": "2468"},
        )
        assert resp.status_code == 404

    def test_get_roster_unknown_event_404(self, client, db_session, owner):
        db_session.commit()
        resp = client.get(
            f"/api/v1/events/{uuid.uuid4()}/roster", headers=auth_headers(client, owner)
        )
        assert resp.status_code == 404


# ------------------------------------------- edges in the service internals


class TestServiceEdges:
    def test_self_check_in_lookup_errors(self, db_session, owner):
        event = _event(db_session, owner)
        other = _event(db_session, owner)
        slot = _orientation(db_session, other, hours_from_now=0)
        s = _signup(db_session, slot)

        with pytest.raises(LookupError):
            self_check_in(db_session, uuid.uuid4(), s.id, "2468", None)
        with pytest.raises(LookupError):
            self_check_in(db_session, event.id, uuid.uuid4(), "2468", None)
        with pytest.raises(LookupError):
            self_check_in(db_session, event.id, s.id, "2468", None)

    def test_event_qr_skips_a_waitlisted_shift_and_a_dead_orientation(
        self, db_session, owner
    ):
        """One QR scan for the whole event: a waitlisted shift and a cancelled
        orientation in the window are skipped, the real seat is checked in."""
        event = _event(db_session, owner)
        vol = _volunteer(db_session)
        live = _orientation(db_session, event, hours_from_now=0)
        dead = _orientation(db_session, event, hours_from_now=0)
        ok = _signup(db_session, live, volunteer=vol)
        gone = _signup(db_session, dead, SignupStatus.cancelled, volunteer=vol)
        shift, (now_session,) = _shift(db_session, event, [0])
        wl = _commit(db_session, shift, SignupStatus.waitlisted, volunteer=vol)

        _, eligible, needs_staff = event_check_in_by_email(
            db_session, event.id, vol.email, "2468"
        )
        assert needs_staff == []

        assert [(o.unit_id, changed) for o, changed in eligible] == [(ok.id, True)]
        assert gone.status == SignupStatus.cancelled
        assert _row(db_session, wl, now_session) is None

    def test_selected_on_a_cancelled_orientation_changes_nothing(self, db_session, owner):
        event = _event(db_session, owner)
        vol = _volunteer(db_session)
        slot = _orientation(db_session, event, hours_from_now=0)
        gone = _signup(db_session, slot, SignupStatus.cancelled, volunteer=vol)

        _, results = check_in_selected(db_session, event.id, vol.email, "2468", [gone.id])
        assert [changed for _o, changed in results] == [False]

    def test_shift_signup_transition_guards(self, db_session, owner):
        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        with pytest.raises(ValueError):
            cis._transition_shift_signup(db_session, c, SignupStatus.attended, None, "t")
        with pytest.raises(InvalidTransitionError):
            cis._transition_shift_signup(db_session, c, SignupStatus.waitlisted, None, "t")

    def test_window_state_after_the_window_is_closed(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=-3)
        assert window_state(slot, NOW())[0] == "closed"
        assert window_state(slot, NOW() - timedelta(hours=5))[0] == "upcoming"

    def test_record_rejects_a_non_attendance_status_and_a_foreign_session(
        self, db_session, owner
    ):
        from app.services import session_attendance_service as sas

        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        _, (elsewhere,) = _shift(db_session, event, [-3], name="Other")
        c = _commit(db_session, shift)
        with pytest.raises(ValueError):
            sas.record(db_session, c, tue, SignupStatus.confirmed, None, "t")
        with pytest.raises(LookupError):
            sas.record(db_session, c, elsewhere, SignupStatus.checked_in, None, "t")
        with pytest.raises(sas.InvalidAttendanceTransitionError) as exc:
            sas.record(db_session, c, tue, SignupStatus.attended, None, "t")
        assert "no record -> attended" in str(exc.value)

    def test_no_show_counts_for_everyone(self, db_session, owner):
        from app.services import attendance_facts

        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot)
        close_slot(db_session, slot.id, owner.id, [], [])

        counts = attendance_facts.no_show_counts(db_session)
        assert counts[s.volunteer_id] == 1
