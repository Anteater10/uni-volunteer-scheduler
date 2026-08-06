"""Event completion stamping + reopen undo (fix/ux-quarter-batch).

"Ended" used to exist only as a frontend derivation over signup statuses,
so the events list had nothing to show and nothing could be undone. These
tests pin the new backend contract:

- resolving the last expected signup of an event stamps events.completed_at
  (surfaced on EventRead so the list can badge completed events);
- partial resolution leaves the stamp null;
- POST /events/{id}/reopen is the undo: attended -> checked_in when a
  check-in timestamp exists (kept), otherwise -> confirmed; no_show ->
  confirmed; completed_at clears; the event can then be re-ended.
  Orientation credits are deliberately NOT auto-revoked (permanent per
  (email, family) by design — issue #30); corrections go through the
  credits admin page.
- GET /events/ accepts an optional quarter_id filter.
"""
# 2026-08-05 shifts: the slots below are ORIENTATION, not PERIOD.
#
# ck_slots_shift_membership_matches_type makes a shift-less period slot
# unrepresentable, and a period slot now belongs to a shift — capacity, the
# waitlist and the commitment all sit one level up on the Shift, reached
# through the shift-level services. What this file exercises is the Signup
# path, and an orientation slot is exactly the slot that is still booked
# directly, so orientation keeps these tests pointed at the code they were
# written for instead of retargeting them at a different service.

import uuid
from datetime import date, datetime, time, timedelta, timezone

from tests.fixtures.factories import (
    AcademicQuarterFactory,
    EventFactory,
    SignupFactory,
    SlotFactory,
    UserFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import auth_headers, make_user
from app import models
from app.models import Signup, SignupStatus, SlotType, UserRole, Volunteer


def _bind(db_session):
    for f in (
        UserFactory,
        EventFactory,
        SlotFactory,
        VolunteerFactory,
        SignupFactory,
        AcademicQuarterFactory,
    ):
        f._meta.sqlalchemy_session = db_session


def _make_volunteer(db_session, email=None):
    v = Volunteer(
        id=uuid.uuid4(),
        email=email or f"vol-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="Vol",
    )
    db_session.add(v)
    db_session.flush()
    return v


def _event_with_slots(db_session, *, owner, slot_count=1):
    _bind(db_session)
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    event = EventFactory(
        owner=owner, start_date=start, end_date=start + timedelta(days=1)
    )
    slots = [
        SlotFactory(
            event=event,
            start_time=start + timedelta(hours=i),
            end_time=start + timedelta(hours=i + 1),
            slot_type=SlotType.ORIENTATION,
            capacity=5,
            current_count=0,
        )
        for i in range(slot_count)
    ]
    db_session.flush()
    return event, slots


def _signup(db_session, slot, status=SignupStatus.confirmed, checked_in_at=None):
    v = _make_volunteer(db_session)
    s = Signup(
        volunteer_id=v.id,
        slot_id=slot.id,
        status=status,
        checked_in_at=checked_in_at,
    )
    db_session.add(s)
    db_session.flush()
    return s


class TestCompletedAtStamp:
    def test_full_resolve_stamps_completed_at(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot,) = _event_with_slots(db_session, owner=organizer)
        a = _signup(db_session, slot)
        b = _signup(db_session, slot)

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": [str(b.id)]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is not None

    def test_partial_resolve_leaves_completed_at_null(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot1, slot2) = _event_with_slots(db_session, owner=organizer, slot_count=2)
        a = _signup(db_session, slot1)
        b = _signup(db_session, slot2)

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/slots/{slot1.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is None

        # Ending the second (last open) slot completes the event.
        resp = client.post(
            f"/api/v1/slots/{slot2.id}/resolve",
            json={"attended": [], "no_show": [str(b.id)]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is not None

    def test_event_with_no_signups_never_completes(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, _slots = _event_with_slots(db_session, owner=organizer)

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is None

    def test_cancelled_and_waitlisted_do_not_block_completion(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot,) = _event_with_slots(db_session, owner=organizer)
        a = _signup(db_session, slot)
        _signup(db_session, slot, status=SignupStatus.cancelled)
        _signup(db_session, slot, status=SignupStatus.waitlisted)

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is not None


class TestReopenEvent:
    def test_reopen_restores_roster_and_clears_stamp(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot,) = _event_with_slots(db_session, owner=organizer)
        checked_in_time = datetime.now(timezone.utc) - timedelta(hours=1)
        was_checked_in = _signup(
            db_session, slot, status=SignupStatus.checked_in, checked_in_at=checked_in_time
        )
        walk_in = _signup(db_session, slot)  # confirmed, no check-in timestamp
        absent = _signup(db_session, slot)

        headers = auth_headers(client, organizer)
        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={
                "attended": [str(was_checked_in.id), str(walk_in.id)],
                "no_show": [str(absent.id)],
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(f"/api/v1/events/{event.id}/reopen", headers=headers)
        assert resp.status_code == 200, resp.text

        db_session.expire_all()
        # Real check-in kept: attended -> checked_in, timestamp intact.
        assert was_checked_in.status == SignupStatus.checked_in
        assert was_checked_in.checked_in_at is not None
        # Walk-in never checked in: attended -> confirmed.
        assert walk_in.status == SignupStatus.confirmed
        assert walk_in.checked_in_at is None
        # No-show returns to the expected roster.
        assert absent.status == SignupStatus.confirmed

        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is None

    def test_reopen_then_re_end(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot,) = _event_with_slots(db_session, owner=organizer)
        a = _signup(db_session, slot)

        headers = auth_headers(client, organizer)
        client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=headers,
        )
        client.post(f"/api/v1/events/{event.id}/reopen", headers=headers)

        resp = client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [], "no_show": [str(a.id)]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        assert a.status == SignupStatus.no_show
        detail = client.get(f"/api/v1/events/{event.id}", headers=headers).json()
        assert detail["completed_at"] is not None

    def test_reopen_writes_audit_transitions(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, (slot,) = _event_with_slots(db_session, owner=organizer)
        a = _signup(db_session, slot)

        headers = auth_headers(client, organizer)
        client.post(
            f"/api/v1/events/{event.id}/resolve",
            json={"attended": [str(a.id)], "no_show": []},
            headers=headers,
        )
        client.post(f"/api/v1/events/{event.id}/reopen", headers=headers)

        rows = (
            db_session.query(models.AuditLog)
            .filter(
                models.AuditLog.entity_id == str(a.id),
                models.AuditLog.action == "transition",
            )
            .all()
        )
        vias = {r.extra.get("via") for r in rows}
        assert "reopen_event" in vias

    def test_reopen_requires_staff(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, _ = _event_with_slots(db_session, owner=organizer)

        resp = client.post(f"/api/v1/events/{event.id}/reopen")
        assert resp.status_code == 401

    def test_reopen_unknown_event_404s(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        headers = auth_headers(client, organizer)
        resp = client.post(f"/api/v1/events/{uuid.uuid4()}/reopen", headers=headers)
        assert resp.status_code == 404


class TestEventsListQuarterFilter:
    def test_quarter_id_filters_the_staff_list(self, client, db_session):
        _bind(db_session)
        organizer = make_user(db_session, role=UserRole.organizer)
        q_old = AcademicQuarterFactory(
            season=models.Quarter.WINTER,
            year=2026,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 3, 20),
        )
        q_new = AcademicQuarterFactory(
            season=models.Quarter.SPRING,
            year=2026,
            start_date=date(2026, 3, 30),
            end_date=date(2026, 6, 15),
        )
        db_session.flush()

        def _event_in(q, title):
            start = datetime.combine(
                q.start_date + timedelta(days=7), time(9), tzinfo=timezone.utc
            )
            e = EventFactory(
                owner=organizer,
                title=title,
                start_date=start,
                end_date=start + timedelta(hours=8),
            )
            e.quarter_id = q.id
            return e

        _event_in(q_old, "Winter event")
        _event_in(q_new, "Spring event")
        db_session.flush()

        headers = auth_headers(client, organizer)
        resp = client.get(
            "/api/v1/events/", params={"quarter_id": str(q_old.id)}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        titles = [e["title"] for e in resp.json()]
        assert "Winter event" in titles
        assert "Spring event" not in titles

        # No param keeps the old everything behavior.
        resp = client.get("/api/v1/events/", headers=headers)
        titles = [e["title"] for e in resp.json()]
        assert "Winter event" in titles and "Spring event" in titles
