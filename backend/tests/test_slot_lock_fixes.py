"""Review round 1 fixes to the slot lock (FIXES.md B1-B10).

B1  locks re-read rows already loaded in the session (populate_existing)
B2  one lock order: slot(s) first, then bookings; re-check after the lock
B3  a closed orientation slot takes no new seat; closed sessions list only
    the people who were expected there
B6  a cancelled commitment's open check-ins are deleted
B7  reopen stamps a check-in time when there was none
B8  revoking a credit hands it to another attended orientation of the family
B9  copilot mark_attendance reports lookup / HTTP failures as errors
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event as sa_event, text

from app import models
from app.models import (
    OrientationCredit,
    SessionAttendance,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    UserRole,
)
from app.services import attendance_facts, waitlist_service
from app.services import check_in_service as cis
from app.services.check_in_service import (
    InvalidTransitionError,
    SlotClosedError,
    check_in_session,
    check_in_signup,
    clear_open_check_ins,
    close_slot,
    ensure_accepts_seat,
    lock_shift_signup_with_shift,
    lock_signup_with_slot,
    reopen_slot,
)
from app.services.swap_service import swap_shift_signup, swap_signup
from tests.fixtures.helpers import auth_headers, make_user
from tests.test_slot_lock import (  # noqa: F401  (owner is a fixture)
    NOW,
    _active_credits,
    _audits,
    _commit,
    _event,
    _orientation,
    _row,
    _shift,
    _signup,
    _volunteer,
    owner,
)


def _core(db, sql, **params):
    """Change a row behind the ORM's back, so objects the session already
    holds go stale — the situation populate_existing exists for."""
    db.connection().execute(text(sql), params)


# ------------------------------------------------------------------- B1


class TestLocksRereadStaleRows:
    def test_tap_sees_a_cancel_the_session_never_saw(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.confirmed)
        _core(db_session, "UPDATE signups SET status='cancelled' WHERE id=:id", id=s.id)
        assert s.status == SignupStatus.confirmed  # stale in the session

        with pytest.raises(InvalidTransitionError):
            check_in_signup(db_session, s.id, owner.id)
        assert s.status == SignupStatus.cancelled

    def test_tap_sees_a_close_the_session_never_saw(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot)
        _core(db_session, "UPDATE slots SET closed_at=now() WHERE id=:id", id=slot.id)
        assert slot.closed_at is None

        with pytest.raises(SlotClosedError):
            check_in_signup(db_session, s.id, owner.id)

    def test_close_sees_a_check_in_the_session_never_saw(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.confirmed)
        _core(
            db_session,
            "UPDATE signups SET status='checked_in', checked_in_at=now() WHERE id=:id",
            id=s.id,
        )

        close_slot(db_session, slot.id, owner.id, [], [])
        assert s.status == SignupStatus.attended

    def test_close_twice_with_a_stale_open_slot_still_refuses(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        _core(db_session, "UPDATE slots SET closed_at=now() WHERE id=:id", id=slot.id)
        with pytest.raises(SlotClosedError):
            close_slot(db_session, slot.id, owner.id, [], [])

    def test_session_close_sees_a_fresh_attendance_row(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)
        _core(db_session, "DELETE FROM session_attendance WHERE slot_id=:s", s=tue.id)

        close_slot(db_session, tue.id, owner.id, [], [])
        assert _row(db_session, c, tue).status == SignupStatus.no_show

    def test_swap_sees_a_close_the_session_never_saw(self, db_session, owner):
        event = _event(db_session, owner)
        a = _orientation(db_session, event, hours_from_now=5)
        b = _orientation(db_session, event, hours_from_now=6)
        s = _signup(db_session, a)
        _core(db_session, "UPDATE slots SET closed_at=now() WHERE id=:id", id=b.id)

        with pytest.raises(HTTPException) as exc:
            swap_signup(db_session, signup_id=s.id, target_slot_id=b.id)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SLOT_CLOSED"


# ------------------------------------------------------------------- B2


class TestLockOrderRecheck:
    def test_a_signup_moved_between_read_and_lock_is_lookup(
        self, db_session, owner, monkeypatch
    ):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other = _orientation(db_session, event, hours_from_now=-5)
        s = _signup(db_session, slot)
        real = cis._lock_slot

        def moving(db, slot_id, *, exclusive):
            locked = real(db, slot_id, exclusive=exclusive)
            _core(db, "UPDATE signups SET slot_id=:o WHERE id=:id", o=other.id, id=s.id)
            return locked

        monkeypatch.setattr(cis, "_lock_slot", moving)
        with pytest.raises(LookupError):
            check_in_signup(db_session, s.id, owner.id)

    def test_an_unknown_signup_is_lookup(self, db_session, owner):
        with pytest.raises(LookupError):
            lock_signup_with_slot(db_session, uuid.uuid4())

    def test_a_commitment_moved_between_read_and_lock_is_lookup(
        self, db_session, owner, monkeypatch
    ):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        other, _ = _shift(db_session, event, [-3], name="Other")
        c = _commit(db_session, shift)
        real = cis._lock_slot

        def moving(db, slot_id, *, exclusive):
            locked = real(db, slot_id, exclusive=exclusive)
            _core(db, "UPDATE shift_signups SET shift_id=:o WHERE id=:id", o=other.id, id=c.id)
            return locked

        monkeypatch.setattr(cis, "_lock_slot", moving)
        with pytest.raises(LookupError):
            check_in_session(db_session, c.id, tue.id, owner.id)

    def test_shift_lock_helper_order_and_lookups(self, db_session, owner, monkeypatch):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        other, _ = _shift(db_session, event, [-3], name="Other")
        c = _commit(db_session, shift)

        got, locked_shift = lock_shift_signup_with_shift(db_session, c.id, sessions=True)
        assert (got, locked_shift) == (c, shift)

        with pytest.raises(LookupError):
            lock_shift_signup_with_shift(db_session, uuid.uuid4())

        real = cis.lock_shift_sessions

        def moving(db, shift_id):
            rows = real(db, shift_id)
            _core(db, "UPDATE shift_signups SET shift_id=:o WHERE id=:id", o=other.id, id=c.id)
            return rows

        monkeypatch.setattr(cis, "lock_shift_sessions", moving)
        with pytest.raises(LookupError):
            lock_shift_signup_with_shift(db_session, c.id, sessions=True)

    def test_swap_refuses_a_signup_that_changed_under_it(self, db_session, owner, monkeypatch):
        from app.services import swap_service

        event = _event(db_session, owner)
        a = _orientation(db_session, event, hours_from_now=5)
        b = _orientation(db_session, event, hours_from_now=6)
        s = _signup(db_session, a)
        real = swap_service._lock_slots_in_order

        def cancelling(db, x, y):
            out = real(db, x, y)
            _core(db, "UPDATE signups SET status='cancelled' WHERE id=:id", id=s.id)
            return out

        monkeypatch.setattr(swap_service, "_lock_slots_in_order", cancelling)
        with pytest.raises(HTTPException) as exc:
            swap_signup(db_session, signup_id=s.id, target_slot_id=b.id)
        assert exc.value.status_code == 422  # re-checked after the lock

        def moving(db, x, y):
            out = real(db, x, y)
            _core(db, "UPDATE signups SET slot_id=:b, status='confirmed' WHERE id=:id",
                  b=b.id, id=s.id)
            return out

        _core(db_session, "UPDATE signups SET status='confirmed' WHERE id=:id", id=s.id)
        db_session.expire_all()
        monkeypatch.setattr(swap_service, "_lock_slots_in_order", moving)
        with pytest.raises(HTTPException) as exc:
            swap_signup(db_session, signup_id=s.id, target_slot_id=b.id)
        assert exc.value.status_code == 409

    def test_shift_swap_refuses_a_commitment_cancelled_under_it(
        self, db_session, owner, monkeypatch
    ):
        from app.services import swap_service

        event = _event(db_session, owner)
        a, _ = _shift(db_session, event, [30])
        b, _ = _shift(db_session, event, [31], name="B")
        c = _commit(db_session, a)
        real = swap_service._lock_shifts_in_order

        def cancelling(db, x, y):
            out = real(db, x, y)
            _core(db, "UPDATE shift_signups SET status='cancelled' WHERE id=:id", id=c.id)
            return out

        monkeypatch.setattr(swap_service, "_lock_shifts_in_order", cancelling)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 409

    def test_event_slots_lock_in_id_order_but_close_in_time_order(self, db_session, owner):
        event = _event(db_session, owner)
        slots = [_orientation(db_session, event, hours_from_now=-h) for h in (2, 9, 5)]
        assert cis._event_slots(db_session, event.id) == sorted(
            slots, key=lambda s: (s.start_time, s.id)
        )

    def test_staff_cancel_endpoints_lock_slot_first(self, client, db_session, owner):
        """Smoke: both cancel routes run through the slot-first helper and
        404 on an unknown signup."""
        db_session.commit()
        headers = auth_headers(client, owner)
        for url in (
            f"/api/v1/signups/{uuid.uuid4()}/cancel",
            f"/api/v1/admin/signups/{uuid.uuid4()}/cancel",
            f"/api/v1/admin/signups/{uuid.uuid4()}/uncancel",
            f"/api/v1/admin/signups/{uuid.uuid4()}/promote",
            f"/api/v1/admin/shift-signups/{uuid.uuid4()}/cancel",
            f"/api/v1/admin/shift-signups/{uuid.uuid4()}/uncancel",
            f"/api/v1/admin/shift-signups/{uuid.uuid4()}/promote",
        ):
            assert client.post(url, headers=headers).status_code == 404, url


# ------------------------------------------------------------------- B3


@pytest.fixture
def admin_user(db_session):
    return make_user(db_session, role=UserRole.admin)


class TestNoSeatOnAClosedOrientation:
    def _closed(self, db_session, owner, hours=5):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=hours)
        slot.closed_at = NOW()
        db_session.flush()
        return event, slot

    def test_ensure_accepts_seat(self, db_session, owner):
        event, slot = self._closed(db_session, owner)
        with pytest.raises(HTTPException) as exc:
            ensure_accepts_seat(slot)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SLOT_CLOSED"
        slot.closed_at = None
        ensure_accepts_seat(slot)

    def test_public_signup_is_409(self, client, db_session, owner, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay", lambda *a, **k: None
        )
        event, slot = self._closed(db_session, owner)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json={
                "first_name": "Late", "last_name": "Comer",
                "email": "late@example.com", "phone": "8055551234",
                "slot_ids": [str(slot.id)],
            },
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "SLOT_CLOSED"
        assert db_session.query(Signup).filter(Signup.slot_id == slot.id).count() == 0

    def test_public_signup_rechecks_under_the_lock(self, db_session, owner, monkeypatch):
        """The pre-flight read can be stale; the locked read decides."""
        from app.services import public_signup_service as pss

        event, slot = self._closed(db_session, owner)
        monkeypatch.setattr(pss, "_ensure_units_not_ended", lambda *a, **k: None)
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay", lambda *a, **k: None
        )
        from app.schemas import PublicSignupCreate

        payload = PublicSignupCreate(
            first_name="Late", last_name="Comer", email="late2@example.com",
            phone="8055551234", slot_ids=[slot.id],
        )
        with pytest.raises(HTTPException) as exc:
            pss.create_public_signup(db_session, payload)
        assert exc.value.detail["code"] == "SLOT_CLOSED"

    def test_admin_uncancel_add_and_move_are_409(
        self, client, db_session, owner, admin_user, monkeypatch
    ):
        monkeypatch.setattr("app.celery_app.send_email_notification.delay", lambda **k: None)
        event, closed = self._closed(db_session, owner)
        open_slot = _orientation(db_session, event, hours_from_now=7)
        gone = _signup(db_session, closed, SignupStatus.cancelled)
        mover = _signup(db_session, open_slot)
        stuck = _signup(db_session, closed, SignupStatus.attended)
        db_session.commit()
        headers = auth_headers(client, admin_user)

        resp = client.post(f"/api/v1/admin/signups/{gone.id}/uncancel", headers=headers)
        assert (resp.status_code, resp.json()["code"]) == (409, "SLOT_CLOSED")

        resp = client.post(
            f"/api/v1/admin/events/{event.id}/add-volunteer",
            json={
                "first_name": "M", "last_name": "L", "email": "ml@example.com",
                "shift_ids": [], "slot_ids": [str(closed.id)],
            },
            headers=headers,
        )
        assert (resp.status_code, resp.json()["code"]) == (409, "SLOT_CLOSED")

        for signup, target in ((mover, closed), (stuck, open_slot)):
            resp = client.post(
                f"/api/v1/admin/signups/{signup.id}/move",
                json={"target_slot_id": str(target.id)},
                headers=headers,
            )
            assert (resp.status_code, resp.json()["code"]) == (409, "SLOT_CLOSED")

        db_session.expire_all()
        assert gone.status == SignupStatus.cancelled
        assert mover.slot_id == open_slot.id
        assert stuck.slot_id == closed.id

    def test_promotion_treats_a_closed_slot_as_ended(
        self, client, db_session, owner, admin_user
    ):
        event, closed = self._closed(db_session, owner)
        wl = _signup(db_session, closed, SignupStatus.waitlisted)
        wl2 = _signup(db_session, closed, SignupStatus.waitlisted)
        db_session.commit()

        resp = client.post(
            f"/api/v1/admin/signups/{wl.id}/promote",
            headers=auth_headers(client, admin_user),
        )
        assert (resp.status_code, resp.json()["code"]) == (422, "SLOT_ENDED")
        resp = client.post(
            f"/api/v1/organizer/events/{event.id}/signups/{wl2.id}/promote",
            headers=auth_headers(client, owner),
        )
        assert (resp.status_code, resp.json()["code"]) == (422, "SLOT_ENDED")

    def test_slot_and_shift_has_ended(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=5)
        shift, (tue, thu) = _shift(db_session, event, [-3, 40])
        assert not waitlist_service.slot_has_ended(slot)
        slot.closed_at = NOW()
        assert waitlist_service.slot_has_ended(slot)

        assert not waitlist_service.shift_has_ended(shift)
        tue.closed_at = NOW()
        assert not waitlist_service.shift_has_ended(shift)  # Thursday still open
        thu.closed_at = NOW()
        assert waitlist_service.shift_has_ended(shift)

    def test_a_naive_end_time_still_compares(self):
        class Bare:
            closed_at = None
            end_time = datetime(2000, 1, 1)

        assert waitlist_service.slot_has_ended(Bare())


class TestShiftSeatsWithClosedSessions:
    def test_late_joiner_is_left_off_the_closed_session(
        self, client, db_session, owner
    ):
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-3, 40])
        early = _commit(db_session, shift)
        close_slot(db_session, tue.id, owner.id, [], [])
        late = _commit(db_session, shift)  # joined after Tuesday closed
        db_session.commit()

        resp = client.get(
            f"/api/v1/events/{event.id}/roster", headers=auth_headers(client, owner)
        )
        rows = {(r["shift_signup_id"], r["slot_id"]) for r in resp.json()["rows"]}
        assert (str(early.id), str(tue.id)) in rows
        assert (str(late.id), str(tue.id)) not in rows
        assert (str(late.id), str(thu.id)) in rows

        facts = attendance_facts.facts()
        got = {
            (r.booking_id, r.slot_id)
            for r in db_session.execute(
                facts.select().where(facts.c.event_id == event.id)
            )
        }
        assert (late.id, tue.id) not in got
        assert (late.id, thu.id) in got
        assert (early.id, tue.id) in got

    def test_public_signup_refuses_a_shift_with_every_session_closed(
        self, client, db_session, owner, monkeypatch
    ):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay", lambda *a, **k: None
        )
        event = _event(db_session, owner)
        shift, sessions = _shift(db_session, event, [30, 40])
        for s in sessions:
            s.closed_at = NOW()
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json={
                "first_name": "A", "last_name": "B", "email": "ab@example.com",
                "phone": "8055551234", "slot_ids": [], "shift_ids": [str(shift.id)],
            },
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SESSION_ENDED"

    def test_reinstating_onto_a_part_closed_shift_is_allowed(
        self, client, db_session, owner, admin_user, monkeypatch
    ):
        monkeypatch.setattr("app.celery_app.send_email_notification.delay", lambda **k: None)
        event = _event(db_session, owner)
        shift, (tue, _thu) = _shift(db_session, event, [-3, 40])
        c = _commit(db_session, shift, SignupStatus.cancelled)
        tue.closed_at = NOW()
        db_session.commit()

        resp = client.post(
            f"/api/v1/admin/shift-signups/{c.id}/uncancel",
            headers=auth_headers(client, admin_user),
        )
        assert resp.status_code == 200, resp.text


# ------------------------------------------------------------------- B6


class TestCancelledCommitmentCheckIns:
    def test_admin_cancel_deletes_open_check_ins(
        self, client, db_session, owner, admin_user, monkeypatch
    ):
        monkeypatch.setattr("app.celery_app.send_email_notification.delay", lambda **k: None)
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-3, 0])
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)
        check_in_session(db_session, c.id, thu.id, owner.id)
        db_session.commit()

        resp = client.post(
            f"/api/v1/admin/shift-signups/{c.id}/cancel",
            headers=auth_headers(client, admin_user),
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert _row(db_session, c, tue) is None and _row(db_session, c, thu) is None
        assert len(_audits(db_session, entity_id=c.id, via="admin_shift_signup_cancel")) == 2

    def test_clear_open_check_ins_skips_closed_sessions(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue, thu) = _shift(db_session, event, [-3, 0])
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)
        check_in_session(db_session, c.id, thu.id, owner.id)
        # A closed session can only hold a check-in through a stray write.
        tue.closed_at = NOW()
        db_session.flush()

        assert clear_open_check_ins(db_session, c, owner.id, "t") == 1
        assert _row(db_session, c, tue).status == SignupStatus.checked_in
        assert _row(db_session, c, thu) is None

    @pytest.mark.parametrize("status", ["cancelled", "waitlisted"])
    def test_close_deletes_check_ins_of_unseated_commitments(
        self, db_session, owner, status
    ):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)
        _core(db_session, f"UPDATE shift_signups SET status='{status}' WHERE id=:id", id=c.id)

        close_slot(db_session, tue.id, owner.id, [], [])

        assert _row(db_session, c, tue) is None
        assert len(_audits(db_session, entity_id=c.id, via="close_slot")) == 1


# ------------------------------------------------------------------- B7


class TestReopenStampsMissingCheckInTime:
    def test_orientation_walk_in(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        walk = _signup(db_session, slot, SignupStatus.confirmed)
        close_slot(db_session, slot.id, owner.id, [walk.id], [])
        assert walk.checked_in_at is None

        reopen_slot(db_session, slot.id, owner.id)
        assert walk.status == SignupStatus.checked_in
        assert walk.checked_in_at is not None

    def test_session_walk_in(self, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        c = _commit(db_session, shift)
        close_slot(db_session, tue.id, owner.id, [c.id], [])
        assert _row(db_session, c, tue).checked_in_at is None

        reopen_slot(db_session, tue.id, owner.id)
        row = _row(db_session, c, tue)
        assert row.status == SignupStatus.checked_in and row.checked_in_at is not None


# ------------------------------------------------------------------- B8


class TestCreditMovesToAnotherAttendedOrientation:
    def test_revoking_the_first_hands_credit_to_the_second(self, db_session, owner):
        vol = _volunteer(db_session)
        first_event = _event(db_session, owner)
        first = _orientation(db_session, first_event, hours_from_now=-30)
        second_event = _event(db_session, owner)
        second = _orientation(db_session, second_event, hours_from_now=-3)
        s1 = _signup(db_session, first, SignupStatus.checked_in, volunteer=vol)
        s2 = _signup(db_session, second, SignupStatus.checked_in, volunteer=vol)
        close_slot(db_session, first.id, owner.id, [], [])
        close_slot(db_session, second.id, owner.id, [], [])
        # Deduped: only the first close granted.
        (credit,) = _active_credits(db_session, vol.email)
        assert credit.source_signup_id == s1.id

        reopen_slot(db_session, first.id, owner.id)
        close_slot(db_session, first.id, owner.id, [], [s1.id])

        (moved,) = _active_credits(db_session, vol.email)
        assert moved.source_signup_id == s2.id
        assert moved.quarter_id == second_event.quarter_id
        grants = _audits(db_session, entity_id=moved.id, action="orientation_credit_grant")
        assert grants[0].extra["signup_id"] == str(s2.id)

    def test_nothing_to_hand_to_when_no_other_closed_attendance(self, db_session, owner):
        vol = _volunteer(db_session)
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other_family_event = _event(db_session, owner, module=False)
        elsewhere = _orientation(db_session, other_family_event, hours_from_now=-9)
        open_one = _orientation(db_session, event, hours_from_now=-6)
        s = _signup(db_session, slot, SignupStatus.checked_in, volunteer=vol)
        # Attended, but on a module-less event (another "family"), and an
        # attended row on a still-open slot (a stray) — neither qualifies.
        _signup(db_session, elsewhere, SignupStatus.attended, volunteer=vol)
        elsewhere.closed_at = NOW()
        _signup(db_session, open_one, SignupStatus.attended, volunteer=vol)
        close_slot(db_session, slot.id, owner.id, [], [])

        reopen_slot(db_session, slot.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [s.id])

        assert _active_credits(db_session, vol.email) == []


# ------------------------------------------------------------------- B9


class TestCopilotMarkAttendanceErrors:
    @pytest.fixture
    def run(self, db_session, owner):
        from app.copilot.agent.boundary.role_scope import scope_for
        from app.copilot.agent.tools.operations import _attendance_handler

        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot)
        db_session.commit()
        args = {
            "participant_id": str(s.volunteer_id),
            "slot_id": str(slot.id),
            "outcome": "attended",
        }
        return lambda: _attendance_handler(
            db_session, scope_for(role="admin", caller_id=owner.id), args
        )

    def test_lookup_error_is_an_error(self, run, monkeypatch):
        def gone(*a, **k):
            raise LookupError("Signup moved")

        monkeypatch.setattr(cis, "mark_present", gone)
        assert run() == {"error": "Signup moved"}

    def test_http_exception_goes_through_service_error(self, run, monkeypatch):
        def refused(*a, **k):
            raise HTTPException(status_code=422, detail={"code": "X", "message": "no"})

        monkeypatch.setattr(cis, "mark_present", refused)
        out = run()
        assert "error" in out


# ------------------------------------------------- copilot move_participant


class TestMoveParticipantAndClosedSlots:
    def _setup(self, db_session, owner):
        vol = _volunteer(db_session)
        src_event = _event(db_session, owner)
        src = _orientation(db_session, src_event, hours_from_now=10)
        dst_event = _event(db_session, owner)
        return vol, src_event, src, dst_event

    def test_a_closed_destination_is_never_picked(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_signup

        vol, src_event, src, dst_event = self._setup(db_session, owner)
        closed = _orientation(db_session, dst_event, hours_from_now=11)
        closed.closed_at = NOW()
        open_one = _orientation(db_session, dst_event, hours_from_now=12)
        s = _signup(db_session, src, volunteer=vol)

        out = _move_signup(db_session, vol.id, src_event.id, dst_event.id, s.id)
        assert out["status"] == "confirmed"
        assert s.slot_id == open_one.id

    def test_only_closed_destinations_means_no_slot(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_signup

        vol, src_event, src, dst_event = self._setup(db_session, owner)
        closed = _orientation(db_session, dst_event, hours_from_now=11)
        closed.closed_at = NOW()
        s = _signup(db_session, src, volunteer=vol)

        out = _move_signup(db_session, vol.id, src_event.id, dst_event.id, s.id)
        assert out == {"error": "no slots available on to_module"}

    def test_a_closed_source_does_not_move(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_signup

        vol, src_event, src, dst_event = self._setup(db_session, owner)
        _orientation(db_session, dst_event, hours_from_now=11)
        s = _signup(db_session, src, SignupStatus.attended, volunteer=vol)
        src.closed_at = NOW()
        db_session.flush()

        out = _move_signup(db_session, vol.id, src_event.id, dst_event.id, s.id)
        assert "reopen it on the roster page" in out["error"]
        assert s.slot_id == src.id

    def test_a_signup_changed_under_the_lock(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_signup

        vol, src_event, src, dst_event = self._setup(db_session, owner)
        _orientation(db_session, dst_event, hours_from_now=11)
        other = _orientation(db_session, src_event, hours_from_now=13)
        s = _signup(db_session, src, volunteer=vol)
        fired = []

        def on_execute(state):
            # The first locking select is the slot / shift pair-lock.
            if not fired and state.is_select and (
                state.statement._for_update_arg is not None
            ):
                fired.append(True)
                state.session.connection().execute(
                    text("UPDATE signups SET slot_id=:o WHERE id=:id"),
                    {"o": other.id, "id": s.id},
                )

        sa_event.listen(db_session, "do_orm_execute", on_execute)
        try:
            out = _move_signup(db_session, vol.id, src_event.id, dst_event.id, s.id)
        finally:
            sa_event.remove(db_session, "do_orm_execute", on_execute)
        assert out == {"error": "that signup changed while it was being moved — try again"}

    def test_shift_move_same_shift_and_changed_commitment(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_shift_signup

        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [30])
        c = _commit(db_session, shift)
        out = _move_shift_signup(db_session, c.volunteer_id, event.id, event.id, c.id)
        assert out["status"] == "confirmed"

        dst_event = _event(db_session, owner)
        _shift(db_session, dst_event, [31], name="Dest")
        other, _ = _shift(db_session, event, [32], name="Other")
        fired = []

        def on_execute(state):
            # The first locking select is the slot / shift pair-lock.
            if not fired and state.is_select and (
                state.statement._for_update_arg is not None
            ):
                fired.append(True)
                state.session.connection().execute(
                    text("UPDATE shift_signups SET shift_id=:o WHERE id=:id"),
                    {"o": other.id, "id": c.id},
                )

        sa_event.listen(db_session, "do_orm_execute", on_execute)
        try:
            out = _move_shift_signup(
                db_session, c.volunteer_id, event.id, dst_event.id, c.id
            )
        finally:
            sa_event.remove(db_session, "do_orm_execute", on_execute)
        assert out == {"error": "that signup changed while it was being moved — try again"}

    def test_precheck_asks_for_a_different_destination(self, db_session):
        from app.copilot.agent.boundary.role_scope import scope_for
        from app.copilot.agent.tools.move_participant import _precheck

        same = str(uuid.uuid4())
        out = _precheck(
            db_session,
            scope_for(role="admin", caller_id=None),
            {"participant_id": str(uuid.uuid4()), "from_module": same, "to_module": same},
        )
        assert "different" in " ".join(out["needs_answers"])


# --------------------------------------------- waitlist_service shift helpers


class TestShiftWaitlistHelpers:
    def test_position_and_full_refusal(self, db_session, owner):
        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [30])
        a = _commit(db_session, shift, SignupStatus.waitlisted)
        b = _commit(db_session, shift, SignupStatus.waitlisted)
        a.timestamp = NOW() - timedelta(minutes=5)
        b.timestamp = NOW()
        db_session.flush()

        assert waitlist_service.compute_shift_waitlist_position(db_session, shift.id, b.id) == 2
        assert waitlist_service.compute_shift_waitlist_position(
            db_session, shift.id, uuid.uuid4()
        ) is None

        shift.capacity = 1
        shift.current_count = 1
        with pytest.raises(ValueError, match="shift is full"):
            waitlist_service.manual_promote_shift(db_session, a, shift)


class TestWaitlistServiceEdges:
    def test_no_end_time_is_not_ended(self):
        class Bare:
            closed_at = None
            end_time = None

        assert not waitlist_service.slot_has_ended(Bare())

    def test_only_waitlisted_commitments_promote(self, db_session, owner):
        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [30])
        c = _commit(db_session, shift)
        with pytest.raises(ValueError, match="only waitlisted"):
            waitlist_service.manual_promote_shift(db_session, c, shift)


# ------------------------------------- organizer routes touched by the lock order


class TestOrganizerRoutes:
    @pytest.fixture
    def world(self, db_session, owner):
        event = _event(db_session, owner)
        other = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=10)
        foreign_slot = _orientation(db_session, other, hours_from_now=10)
        shift, _ = _shift(db_session, event, [30])
        foreign_shift, _ = _shift(db_session, other, [30], name="Foreign")
        return {
            "event": event,
            "slot": slot,
            "foreign_signup": _signup(db_session, foreign_slot, SignupStatus.waitlisted),
            "foreign_commit": _commit(db_session, foreign_shift, SignupStatus.waitlisted),
            "shift": shift,
        }

    def _post(self, client, owner, url):
        return client.post(f"/api/v1/organizer{url}", headers=auth_headers(client, owner))

    def test_grant_orientation_guards(self, client, db_session, owner, world):
        moduleless = _event(db_session, owner, module=False)
        bare_slot = _orientation(db_session, moduleless, hours_from_now=3)
        bare = _signup(db_session, bare_slot)
        db_session.commit()
        ev = world["event"].id
        for url, code in (
            (f"/events/{uuid.uuid4()}/signups/{uuid.uuid4()}/grant-orientation", 404),
            (f"/events/{ev}/signups/{uuid.uuid4()}/grant-orientation", 404),
            (f"/events/{ev}/signups/{world['foreign_signup'].id}/grant-orientation", 400),
            (f"/events/{moduleless.id}/signups/{bare.id}/grant-orientation", 400),
            (f"/events/{uuid.uuid4()}/shift-signups/{uuid.uuid4()}/grant-orientation", 404),
            (f"/events/{ev}/shift-signups/{uuid.uuid4()}/grant-orientation", 404),
        ):
            assert self._post(client, owner, url).status_code == code, url

    def test_append_form_field(self, client, db_session, owner, world):
        db_session.commit()
        headers = auth_headers(client, owner)
        resp = client.post(
            f"/api/v1/organizer/events/{world['event'].id}/form-fields",
            json={"id": "tshirt", "label": "T-shirt size", "type": "text", "required": False},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert any(f["id"] == "tshirt" for f in resp.json()["schema"])
        resp = client.post(
            f"/api/v1/organizer/events/{uuid.uuid4()}/form-fields",
            json={"id": "x", "label": "X", "type": "text"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_promote_guards(self, client, db_session, owner, world):
        ev = world["event"].id
        confirmed = _commit(db_session, world["shift"])
        full_wl = _commit(db_session, world["shift"], SignupStatus.waitlisted)
        world["shift"].capacity = 1
        world["shift"].current_count = 1
        done_shift, done_sessions = _shift(db_session, world["event"], [40], name="Done")
        done_sessions[0].closed_at = NOW()  # closed counts as ended
        done_wl = _commit(db_session, done_shift, SignupStatus.waitlisted)
        db_session.commit()
        for url, code in (
            (f"/events/{uuid.uuid4()}/signups/{uuid.uuid4()}/promote", 404),
            (f"/events/{ev}/signups/{uuid.uuid4()}/promote", 404),
            (f"/events/{ev}/signups/{world['foreign_signup'].id}/promote", 400),
            (f"/events/{uuid.uuid4()}/shift-signups/{uuid.uuid4()}/promote", 404),
            (f"/events/{ev}/shift-signups/{uuid.uuid4()}/promote", 404),
            (f"/events/{ev}/shift-signups/{world['foreign_commit'].id}/promote", 400),
            (f"/events/{ev}/shift-signups/{full_wl.id}/promote", 409),
            (f"/events/{ev}/shift-signups/{confirmed.id}/promote", 400),
            (f"/events/{ev}/shift-signups/{done_wl.id}/promote", 422),
        ):
            assert self._post(client, owner, url).status_code == code, url


# ================================================================ round 2


class TestR1ReaperLocksSlotsFirst:
    def test_reap_rereads_a_stale_slot_count(self, db_session, owner, monkeypatch):
        from app import celery_app as celery_mod
        from app.models import MagicLinkPurpose, MagicLinkToken

        class _Proxy:
            def __init__(self, session):
                self._s = session

            def __getattr__(self, name):
                return getattr(self._s, name)

            def close(self):
                pass

        monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=48)
        slot.current_count = 3
        vol = _volunteer(db_session)
        s = _signup(db_session, slot, SignupStatus.pending, volunteer=vol)
        db_session.add(
            MagicLinkToken(
                token_hash=f"hash-{uuid.uuid4().hex}",
                signup_id=s.id,
                email=vol.email,
                expires_at=NOW() - timedelta(days=1),
                purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
                volunteer_id=vol.id,
            )
        )
        db_session.commit()
        # Someone else moved the count; this session still holds 3.
        _core(db_session, "UPDATE slots SET current_count=5 WHERE id=:id", id=slot.id)
        assert slot.current_count == 3

        celery_mod.expire_pending_signups.apply().get()

        db_session.expire_all()
        assert db_session.get(Slot, slot.id).current_count == 4
        assert db_session.get(Signup, s.id) is None


class TestR2CompletionLocksTheEvent:
    def test_refresh_rereads_a_stale_event(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        _signup(db_session, slot, SignupStatus.checked_in)
        stamped = NOW() - timedelta(days=3)
        _core(db_session, "UPDATE events SET completed_at=:t WHERE id=:id", t=stamped, id=event.id)
        assert event.completed_at is None  # stale

        close_slot(db_session, slot.id, owner.id, [], [])

        # The locked re-read saw the existing stamp and kept it.
        assert event.completed_at == stamped


class TestR3StaleCapacityCounts:
    def test_lock_shift_rereads_the_count(self, db_session, owner):
        from app.services import shift_service

        event = _event(db_session, owner)
        shift, _ = _shift(db_session, event, [30])
        _core(db_session, "UPDATE shifts SET current_count=7 WHERE id=:id", id=shift.id)
        assert shift.current_count == 0
        assert shift_service.lock_shift(db_session, shift.id).current_count == 7

    def test_add_volunteer_sees_the_seat_taken_meanwhile(
        self, client, db_session, owner, admin_user, monkeypatch
    ):
        monkeypatch.setattr("app.celery_app.send_email_notification.delay", lambda **k: None)
        event = _event(db_session, owner)
        slot = _orientation(db_session, event, hours_from_now=24)
        slot.capacity = 1
        slot.current_count = 0
        db_session.commit()
        _core(db_session, "UPDATE slots SET current_count=1 WHERE id=:id", id=slot.id)

        resp = client.post(
            f"/api/v1/admin/events/{event.id}/add-volunteer",
            json={
                "first_name": "M", "last_name": "L", "email": "full@example.com",
                "shift_ids": [], "slot_ids": [str(slot.id)],
            },
            headers=auth_headers(client, admin_user),
        )
        assert resp.status_code == 201, resp.text
        assert [b["status"] for b in resp.json()["bookings"]] == ["waitlisted"]


class TestR4StaffRevokeWins:
    def test_a_hand_revoked_credit_is_not_regranted_on_reclose(self, db_session, owner):
        from app.services.orientation_service import revoke_orientation_credit

        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        close_slot(db_session, slot.id, owner.id, [], [])
        (credit,) = _active_credits(db_session, s.volunteer.email)
        revoke_orientation_credit(db_session, credit.id)  # staff, by hand

        reopen_slot(db_session, slot.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [])

        assert s.status == SignupStatus.attended
        assert _active_credits(db_session, s.volunteer.email) == []

    def test_a_close_revoked_credit_still_comes_back(self, db_session, owner):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        close_slot(db_session, slot.id, owner.id, [], [])
        reopen_slot(db_session, slot.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [s.id])  # close revokes
        reopen_slot(db_session, slot.id, owner.id)
        check_in_signup(db_session, s.id, owner.id)
        close_slot(db_session, slot.id, owner.id, [], [])

        assert len(_active_credits(db_session, s.volunteer.email)) == 1

    def test_no_handover_to_a_signup_whose_credit_staff_revoked(self, db_session, owner):
        from app.models import OrientationCreditSource
        from app.services.orientation_service import (
            grant_orientation_credit,
            revoke_orientation_credit,
        )

        vol = _volunteer(db_session)
        first = _orientation(db_session, _event(db_session, owner), hours_from_now=-30)
        second = _orientation(db_session, _event(db_session, owner), hours_from_now=-3)
        s1 = _signup(db_session, first, SignupStatus.checked_in, volunteer=vol)
        s2 = _signup(db_session, second, SignupStatus.attended, volunteer=vol)
        second.closed_at = NOW()
        old = grant_orientation_credit(
            db_session, vol.email, "lockfam",
            source=OrientationCreditSource.attendance, source_signup_id=s2.id,
        )
        revoke_orientation_credit(db_session, old.id)
        close_slot(db_session, first.id, owner.id, [], [])  # s1 earns credit
        assert len(_active_credits(db_session, vol.email)) == 1

        reopen_slot(db_session, first.id, owner.id)
        close_slot(db_session, first.id, owner.id, [], [s1.id])

        assert _active_credits(db_session, vol.email) == []


class TestR5TapOnAMovedSignupIs404:
    @pytest.mark.parametrize("verb", ["check-in", "undo-check-in"])
    def test_moved_mid_request(self, client, db_session, owner, monkeypatch, verb):
        event = _event(db_session, owner)
        slot = _orientation(db_session, event)
        other = _orientation(db_session, event, hours_from_now=-5)
        s = _signup(db_session, slot, SignupStatus.checked_in)
        db_session.commit()
        headers = auth_headers(client, owner)
        real = cis._lock_slot

        def moving(db, slot_id, *, exclusive):
            locked = real(db, slot_id, exclusive=exclusive)
            _core(db, "UPDATE signups SET slot_id=:o WHERE id=:id", o=other.id, id=s.id)
            return locked

        monkeypatch.setattr(cis, "_lock_slot", moving)
        resp = client.post(f"/api/v1/signups/{s.id}/{verb}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Signup not found"


class TestR6ClosedSessionKeepsCancelledAndWaitlisted:
    def test_roster_and_facts(self, client, db_session, owner):
        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [-3])
        cxl = _commit(db_session, shift, SignupStatus.cancelled)
        wl = _commit(db_session, shift, SignupStatus.waitlisted)
        close_slot(db_session, tue.id, owner.id, [], [])
        late = _commit(db_session, shift)
        db_session.commit()

        resp = client.get(
            f"/api/v1/events/{event.id}/roster", headers=auth_headers(client, owner)
        )
        rows = {r["shift_signup_id"]: r["status"] for r in resp.json()["rows"]}
        assert rows == {str(cxl.id): "cancelled", str(wl.id): "waitlisted"}
        assert str(late.id) not in rows

        facts = attendance_facts.facts()
        got = {
            r.booking_id: r.status
            for r in db_session.execute(facts.select().where(facts.c.slot_id == tue.id))
        }
        assert got == {cxl.id: SignupStatus.cancelled, wl.id: SignupStatus.waitlisted}


class TestR7ShiftSwapRechecksAttendance:
    def test_a_check_in_landing_before_the_lock_blocks_the_move(
        self, db_session, owner, monkeypatch
    ):
        from app.services import swap_service

        event = _event(db_session, owner)
        a, (a_tue,) = _shift(db_session, event, [0])
        b, _ = _shift(db_session, event, [31], name="B")
        c = _commit(db_session, a)
        real = swap_service._lock_shifts_in_order

        def checking_in(db, x, y):
            out = real(db, x, y)
            _core(
                db,
                "INSERT INTO session_attendance (id, shift_signup_id, slot_id, status, "
                "checked_in_at) VALUES (:id, :c, :s, 'checked_in', now())",
                id=uuid.uuid4(), c=c.id, s=a_tue.id,
            )
            return out

        monkeypatch.setattr(swap_service, "_lock_shifts_in_order", checking_in)
        with pytest.raises(HTTPException) as exc:
            swap_shift_signup(db_session, shift_signup_id=c.id, target_shift_id=b.id)
        assert exc.value.status_code == 422
        assert "Attendance has already been recorded" in exc.value.detail["message"]
        assert c.shift_id == a.id


class TestR8CopilotShiftMoveRefusesRecordedAttendance:
    def test_a_checked_in_commitment_does_not_move(self, db_session, owner):
        from app.copilot.agent.tools.move_participant import _move_shift_signup

        event = _event(db_session, owner)
        shift, (tue,) = _shift(db_session, event, [0])
        dst = _event(db_session, owner)
        _shift(db_session, dst, [31], name="Dest")
        c = _commit(db_session, shift)
        check_in_session(db_session, c.id, tue.id, owner.id)

        out = _move_shift_signup(db_session, c.volunteer_id, event.id, dst.id, c.id)

        assert out == {
            "error": (
                "Attendance has already been recorded for this shift. "
                "Correct the attendance first, or cancel and re-book."
            )
        }
        assert c.shift_id == shift.id
