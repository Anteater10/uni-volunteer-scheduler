"""Organizer CRUD for shifts and their sessions — `/api/v1/shifts`.

2026-08-05: the shifts feature landed with ~3900 production lines against test
coverage that only checked the migration. These are the router-level tests the
spec asked for: create/read/update/delete, both orderings, and the three rules
that protect a live commitment — you cannot dismantle a shift somebody holds a
seat in, you cannot shrink capacity below the people already in it, and a shift
always keeps at least one session.
"""
import uuid
from datetime import timedelta

import pytest

from app import models
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_shift,
    make_user,
)
from tests.fixtures.factories import EventFactory, VolunteerFactory

BASE = "/api/v1/shifts"


@pytest.fixture
def event(db_session):
    """A three-day event owned by an organizer, so sessions have room to move.

    The router validates every session against the event's date range, so a
    one-day window would make "reschedule this session to tomorrow" fail for a
    reason unrelated to what the test is checking.
    """
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.organizer)
    from datetime import datetime, timezone

    start = datetime.now(timezone.utc) + timedelta(days=2)
    ev = EventFactory(
        owner=owner,
        start_date=start,
        end_date=start + timedelta(days=3),
        visibility="public",
    )
    db_session.flush()
    return ev


@pytest.fixture
def staff_headers(client, event, db_session):
    return auth_headers(client, event.owner)


def _session_payload(event, *, day_offset=0, **extra):
    """A two-hour session `day_offset` days into the event.

    Anchored on the event's own start rather than a wall-clock hour, so the
    session is inside the event range whatever time of day the suite runs at.
    """
    start = event.start_date + timedelta(days=day_offset, hours=1)
    payload = {
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=2)).isoformat(),
    }
    payload.update(extra)
    return payload


def _shift_payload(event, *, name="Tue morning", capacity=4, n_sessions=1, sort_order=0):
    return {
        "name": name,
        "capacity": capacity,
        "sort_order": sort_order,
        "sessions": [_session_payload(event, day_offset=i) for i in range(n_sessions)],
    }


def _create(client, event, headers, **kw):
    resp = client.post(
        f"{BASE}/", params={"event_id": str(event.id)},
        json=_shift_payload(event, **kw), headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestCreate:
    def test_create_returns_shift_with_its_sessions(self, client, event, staff_headers):
        body = _create(client, event, staff_headers, n_sessions=2, capacity=6)

        assert body["name"] == "Tue morning"
        assert body["capacity"] == 6
        assert body["current_count"] == 0
        assert len(body["sessions"]) == 2
        # Sessions are PERIOD slots inside the shift — that is the only slot
        # type a shift can hold, and the only shape the membership CHECK allows.
        assert {s["slot_type"] for s in body["sessions"]} == {"period"}
        assert all(s["shift_id"] == body["id"] for s in body["sessions"])

    def test_session_sort_order_falls_back_to_payload_order(
        self, client, event, staff_headers
    ):
        """A freshly built list from the UI sends all zeros; the order the
        organizer arranged them in is the order they meant."""
        body = _create(client, event, staff_headers, n_sessions=3)
        by_start = sorted(body["sessions"], key=lambda s: s["start_time"])
        assert [s["sort_order"] for s in by_start] == [0, 1, 2]

    def test_explicit_sort_order_is_kept(self, client, event, staff_headers):
        payload = _shift_payload(event, n_sessions=2)
        payload["sessions"][0]["sort_order"] = 5
        payload["sessions"][1]["sort_order"] = 1
        resp = client.post(
            f"{BASE}/", params={"event_id": str(event.id)}, json=payload,
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text
        by_start = sorted(resp.json()["sessions"], key=lambda s: s["start_time"])
        assert [s["sort_order"] for s in by_start] == [5, 1]

    def test_shift_with_no_sessions_is_refused(self, client, event, staff_headers):
        payload = _shift_payload(event)
        payload["sessions"] = []
        resp = client.post(
            f"{BASE}/", params={"event_id": str(event.id)}, json=payload,
            headers=staff_headers,
        )
        assert resp.status_code == 422

    def test_session_outside_the_event_range_is_refused(
        self, client, event, staff_headers
    ):
        payload = _shift_payload(event)
        payload["sessions"][0] = _session_payload(event, day_offset=30)
        resp = client.post(
            f"{BASE}/", params={"event_id": str(event.id)}, json=payload,
            headers=staff_headers,
        )
        assert resp.status_code == 400
        assert "within event" in resp.json()["detail"]

    def test_end_before_start_is_refused(self, client, event, staff_headers):
        payload = _shift_payload(event)
        s = payload["sessions"][0]
        s["start_time"], s["end_time"] = s["end_time"], s["start_time"]
        resp = client.post(
            f"{BASE}/", params={"event_id": str(event.id)}, json=payload,
            headers=staff_headers,
        )
        assert resp.status_code == 400

    def test_participant_cannot_create(self, client, event, db_session):
        participant = make_user(db_session, role=models.UserRole.participant)
        resp = client.post(
            f"{BASE}/", params={"event_id": str(event.id)},
            json=_shift_payload(event),
            headers=auth_headers(client, participant),
        )
        assert resp.status_code == 403

    def test_unknown_event_is_404(self, client, event, staff_headers):
        resp = client.post(
            f"{BASE}/", params={"event_id": str(uuid.uuid4())},
            json=_shift_payload(event), headers=staff_headers,
        )
        assert resp.status_code == 404


class TestList:
    def test_list_is_in_display_order(self, client, event, staff_headers, db_session):
        make_shift(db_session, event.id, name="Second", sort_order=1)
        make_shift(db_session, event.id, name="First", sort_order=0)
        db_session.commit()

        resp = client.get(BASE + "/", params={"event_id": str(event.id)},
                          headers=staff_headers)
        assert resp.status_code == 200
        assert [s["name"] for s in resp.json()] == ["First", "Second"]

    def test_anonymous_reads_a_public_event(self, client, event, db_session):
        make_shift(db_session, event.id, name="Open to all")
        db_session.commit()

        resp = client.get(BASE + "/", params={"event_id": str(event.id)})
        assert resp.status_code == 200
        assert [s["name"] for s in resp.json()] == ["Open to all"]

    def test_private_event_is_404_not_403_for_anonymous(
        self, client, event, db_session
    ):
        """Same contract as slots: a 403 would confirm the event exists."""
        event.visibility = "private"
        make_shift(db_session, event.id)
        db_session.commit()

        resp = client.get(BASE + "/", params={"event_id": str(event.id)})
        assert resp.status_code == 404

        missing = client.get(BASE + "/", params={"event_id": str(uuid.uuid4())})
        assert missing.status_code == 404
        assert missing.json()["detail"] == resp.json()["detail"]

    def test_staff_reads_a_private_event(self, client, event, staff_headers, db_session):
        event.visibility = "private"
        make_shift(db_session, event.id, name="Staff only")
        db_session.commit()

        resp = client.get(BASE + "/", params={"event_id": str(event.id)},
                          headers=staff_headers)
        assert resp.status_code == 200
        assert [s["name"] for s in resp.json()] == ["Staff only"]


class TestUpdate:
    def test_rename_and_raise_capacity(self, client, event, staff_headers, db_session):
        shift = _create(client, event, staff_headers)
        resp = client.patch(
            f"{BASE}/{shift['id']}",
            json={"name": "  Wed afternoon  ", "capacity": 12},
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Wed afternoon"
        assert resp.json()["capacity"] == 12

    def test_capacity_below_the_filled_count_is_refused(
        self, client, event, staff_headers, db_session
    ):
        shift = make_shift(db_session, event.id, capacity=5)
        shift.current_count = 3
        db_session.commit()

        resp = client.patch(f"{BASE}/{shift.id}", json={"capacity": 2},
                            headers=staff_headers)
        assert resp.status_code == 400
        assert "below the 3" in resp.json()["detail"]

        db_session.expire_all()
        assert db_session.get(models.Shift, shift.id).capacity == 5

    def test_capacity_equal_to_the_filled_count_is_allowed(
        self, client, event, staff_headers, db_session
    ):
        """Closing a shift to further signups is a normal thing to do."""
        shift = make_shift(db_session, event.id, capacity=5)
        shift.current_count = 3
        db_session.commit()

        resp = client.patch(f"{BASE}/{shift.id}", json={"capacity": 3},
                            headers=staff_headers)
        assert resp.status_code == 200

    def test_raising_capacity_promotes_nobody(
        self, client, event, staff_headers, db_session
    ):
        """Automatic promotion was removed by the read-only-signups spec —
        staff promote by hand, so a waitlisted volunteer stays waitlisted."""
        _bind_factories(db_session)
        shift = make_shift(db_session, event.id, capacity=1)
        shift.current_count = 1
        waiting = book_shift(
            db_session, shift, VolunteerFactory(),
            status=models.SignupStatus.waitlisted,
        )
        db_session.commit()

        resp = client.patch(f"{BASE}/{shift.id}", json={"capacity": 9},
                            headers=staff_headers)
        assert resp.status_code == 200

        db_session.expire_all()
        assert (
            db_session.get(models.ShiftSignup, waiting.id).status
            == models.SignupStatus.waitlisted
        )
        assert db_session.get(models.Shift, shift.id).current_count == 1

    def test_unknown_shift_is_404(self, client, staff_headers):
        resp = client.patch(f"{BASE}/{uuid.uuid4()}", json={"name": "x"},
                            headers=staff_headers)
        assert resp.status_code == 404


class TestDelete:
    def test_delete_takes_its_sessions_with_it(
        self, client, event, staff_headers, db_session
    ):
        shift = _create(client, event, staff_headers, n_sessions=2)
        session_ids = [s["id"] for s in shift["sessions"]]

        resp = client.delete(f"{BASE}/{shift['id']}", headers=staff_headers)
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.get(models.Shift, uuid.UUID(shift["id"])) is None
        for sid in session_ids:
            assert db_session.get(models.Slot, uuid.UUID(sid)) is None

    @pytest.mark.parametrize(
        "status",
        [
            models.SignupStatus.pending,
            models.SignupStatus.confirmed,
            models.SignupStatus.waitlisted,
        ],
    )
    def test_a_live_commitment_blocks_deletion(
        self, client, event, staff_headers, db_session, status
    ):
        """Waitlisted counts too: they are waiting for *this* shift, and
        deleting it out from under them loses their place with no notice."""
        _bind_factories(db_session)
        shift = make_shift(db_session, event.id)
        book_shift(db_session, shift, VolunteerFactory(), status=status)
        db_session.commit()

        resp = client.delete(f"{BASE}/{shift.id}", headers=staff_headers)
        assert resp.status_code == 400
        assert "Cancel or move" in resp.json()["detail"]

        db_session.expire_all()
        assert db_session.get(models.Shift, shift.id) is not None

    def test_a_cancelled_commitment_does_not_block_deletion(
        self, client, event, staff_headers, db_session
    ):
        _bind_factories(db_session)
        shift = make_shift(db_session, event.id)
        book_shift(db_session, shift, VolunteerFactory(),
                   status=models.SignupStatus.cancelled)
        db_session.commit()

        resp = client.delete(f"{BASE}/{shift.id}", headers=staff_headers)
        assert resp.status_code == 204


class TestReorderShifts:
    def _three(self, db_session, event):
        return [
            make_shift(db_session, event.id, name=n, sort_order=i)
            for i, n in enumerate(("A", "B", "C"))
        ]

    def test_full_list_applies_the_order(
        self, client, event, staff_headers, db_session
    ):
        a, b, c = self._three(db_session, event)
        db_session.commit()

        resp = client.post(
            f"{BASE}/reorder", params={"event_id": str(event.id)},
            json={"shift_ids": [str(c.id), str(a.id), str(b.id)]},
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text
        assert [s["name"] for s in resp.json()] == ["C", "A", "B"]

        db_session.expire_all()
        assert [db_session.get(models.Shift, s.id).sort_order for s in (a, b, c)] == [1, 2, 0]

    def test_partial_list_is_refused(self, client, event, staff_headers, db_session):
        """A stale client that has only seen two of three shifts would
        otherwise silently renumber the one it forgot."""
        a, b, c = self._three(db_session, event)
        db_session.commit()

        resp = client.post(
            f"{BASE}/reorder", params={"event_id": str(event.id)},
            json={"shift_ids": [str(b.id), str(a.id)]}, headers=staff_headers,
        )
        assert resp.status_code == 400
        db_session.expire_all()
        assert [db_session.get(models.Shift, s.id).sort_order for s in (a, b, c)] == [0, 1, 2]

    def test_duplicate_ids_are_refused(self, client, event, staff_headers, db_session):
        a, b, c = self._three(db_session, event)
        db_session.commit()

        resp = client.post(
            f"{BASE}/reorder", params={"event_id": str(event.id)},
            json={"shift_ids": [str(a.id), str(a.id), str(b.id), str(c.id)]},
            headers=staff_headers,
        )
        assert resp.status_code == 400
        assert "duplicates" in resp.json()["detail"]

    def test_a_shift_from_another_event_is_refused(
        self, client, event, staff_headers, db_session
    ):
        a, b, c = self._three(db_session, event)
        other_event = EventFactory(owner=event.owner)
        db_session.flush()
        stranger = make_shift(db_session, other_event.id, name="Elsewhere")
        db_session.commit()

        resp = client.post(
            f"{BASE}/reorder", params={"event_id": str(event.id)},
            json={"shift_ids": [str(a.id), str(b.id), str(c.id), str(stranger.id)]},
            headers=staff_headers,
        )
        assert resp.status_code == 400


class TestSessions:
    def test_add_session_appends_to_the_shift(
        self, client, event, staff_headers, db_session
    ):
        shift = _create(client, event, staff_headers, n_sessions=1)
        resp = client.post(
            f"{BASE}/{shift['id']}/sessions",
            json=_session_payload(event, day_offset=1, name="Day two"),
            headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text
        sessions = sorted(resp.json()["sessions"], key=lambda s: s["sort_order"])
        assert [s["name"] for s in sessions][-1] == "Day two"
        assert [s["sort_order"] for s in sessions] == [0, 1]

    def test_add_session_is_refused_once_anyone_holds_a_seat(
        self, client, event, staff_headers, db_session
    ):
        """Adding a session enlarges the commitment people already agreed to."""
        _bind_factories(db_session)
        shift = make_shift(db_session, event.id)
        db_session.add(
            models.Slot(
                event_id=event.id, shift_id=shift.id, sort_order=0,
                slot_type=models.SlotType.PERIOD, capacity=1, current_count=0,
                start_time=event.start_date, end_time=event.start_date + timedelta(hours=2),
                date=event.start_date.date(),
            )
        )
        book_shift(db_session, shift, VolunteerFactory(),
                   status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.post(
            f"{BASE}/{shift.id}/sessions",
            json=_session_payload(event, day_offset=1), headers=staff_headers,
        )
        assert resp.status_code == 400
        assert "add a session to" in resp.json()["detail"]

    def test_add_session_outside_the_event_range_is_refused(
        self, client, event, staff_headers
    ):
        shift = _create(client, event, staff_headers)
        resp = client.post(
            f"{BASE}/{shift['id']}/sessions",
            json=_session_payload(event, day_offset=99), headers=staff_headers,
        )
        assert resp.status_code == 400

    def test_moving_a_session_keeps_its_date_truthful(
        self, client, event, staff_headers, db_session
    ):
        """Check-in windows and the roster group by `date`, so a session moved
        to another day and left with yesterday's date disappears from both."""
        shift = _create(client, event, staff_headers)
        session = shift["sessions"][0]
        moved = _session_payload(event, day_offset=2)

        resp = client.patch(f"{BASE}/sessions/{session['id']}", json=moved,
                            headers=staff_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["date"] == moved["start_time"][:10]

    def test_rescheduling_reopens_reminders_and_mails_the_holders(
        self, client, event, staff_headers, db_session, monkeypatch
    ):
        """The denormalized reminder columns are only half of it: the real gate
        is the session-scoped dedup marker, so a reschedule that cleared only
        the columns would produce no reminder at all for the new time."""
        sent = []
        monkeypatch.setattr(
            "app.routers.shifts.send_email_notification.delay",
            lambda **kw: sent.append(kw),
        )
        _bind_factories(db_session)
        shift = _create(client, event, staff_headers)
        session = shift["sessions"][0]
        shift_row = db_session.get(models.Shift, uuid.UUID(shift["id"]))
        commitment = book_shift(db_session, shift_row, VolunteerFactory(),
                                status=models.SignupStatus.confirmed)
        commitment.reminder_24h_sent_at = event.start_date
        marker = models.SentNotification(
            shift_signup_id=commitment.id, kind="reminder_24h_s0"
        )
        db_session.add(marker)
        db_session.commit()
        marker_id, commitment_id = marker.id, commitment.id

        resp = client.patch(
            f"{BASE}/sessions/{session['id']}",
            json=_session_payload(event, day_offset=2), headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text

        db_session.expunge_all()
        assert db_session.get(models.ShiftSignup, commitment_id).reminder_24h_sent_at is None
        assert db_session.get(models.SentNotification, marker_id) is None
        assert sent == [
            {
                "shift_signup_id": str(commitment_id),
                "kind": "reschedule",
                "dedup_kind": "reschedule_s0",
                "session_slot_id": session["id"],
            }
        ]

    def test_renaming_a_session_mails_nobody(
        self, client, event, staff_headers, db_session, monkeypatch
    ):
        sent = []
        monkeypatch.setattr(
            "app.routers.shifts.send_email_notification.delay",
            lambda **kw: sent.append(kw),
        )
        _bind_factories(db_session)
        shift = _create(client, event, staff_headers)
        shift_row = db_session.get(models.Shift, uuid.UUID(shift["id"]))
        book_shift(db_session, shift_row, VolunteerFactory(),
                   status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.patch(
            f"{BASE}/sessions/{shift['sessions'][0]['id']}",
            json={"name": "  Room 4  "}, headers=staff_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Room 4"
        assert sent == []

    def test_an_orientation_slot_is_not_a_session(
        self, client, event, staff_headers, db_session
    ):
        """`/shifts/sessions/{id}` only addresses slots inside a shift — an
        orientation slot is edited through `/slots/{id}`."""
        orient = models.Slot(
            event_id=event.id, slot_type=models.SlotType.ORIENTATION,
            capacity=5, current_count=0, start_time=event.start_date,
            end_time=event.start_date + timedelta(hours=1),
            date=event.start_date.date(),
        )
        db_session.add(orient)
        db_session.commit()

        resp = client.patch(f"{BASE}/sessions/{orient.id}", json={"name": "x"},
                            headers=staff_headers)
        assert resp.status_code == 404

        gone = client.delete(f"{BASE}/sessions/{orient.id}", headers=staff_headers)
        assert gone.status_code == 404

    def test_delete_session_leaves_the_rest(
        self, client, event, staff_headers, db_session
    ):
        shift = _create(client, event, staff_headers, n_sessions=2)
        doomed = shift["sessions"][0]["id"]

        resp = client.delete(f"{BASE}/sessions/{doomed}", headers=staff_headers)
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.get(models.Slot, uuid.UUID(doomed)) is None
        remaining = (
            db_session.query(models.Slot)
            .filter(models.Slot.shift_id == uuid.UUID(shift["id"]))
            .count()
        )
        assert remaining == 1

    def test_the_last_session_cannot_be_deleted(
        self, client, event, staff_headers
    ):
        """An empty shift is not bookable and cannot be checked in to."""
        shift = _create(client, event, staff_headers, n_sessions=1)
        resp = client.delete(
            f"{BASE}/sessions/{shift['sessions'][0]['id']}", headers=staff_headers
        )
        assert resp.status_code == 400
        assert "at least one session" in resp.json()["detail"]

    def test_delete_session_is_refused_once_anyone_holds_a_seat(
        self, client, event, staff_headers, db_session
    ):
        _bind_factories(db_session)
        shift = _create(client, event, staff_headers, n_sessions=2)
        shift_row = db_session.get(models.Shift, uuid.UUID(shift["id"]))
        book_shift(db_session, shift_row, VolunteerFactory(),
                   status=models.SignupStatus.confirmed)
        db_session.commit()

        resp = client.delete(
            f"{BASE}/sessions/{shift['sessions'][0]['id']}", headers=staff_headers
        )
        assert resp.status_code == 400
        assert "remove a session from" in resp.json()["detail"]

    def test_reorder_sessions_applies_the_order(
        self, client, event, staff_headers, db_session
    ):
        shift = _create(client, event, staff_headers, n_sessions=3)
        ids = [s["id"] for s in sorted(shift["sessions"], key=lambda s: s["sort_order"])]

        resp = client.post(
            f"{BASE}/{shift['id']}/sessions/reorder",
            json={"session_ids": [ids[2], ids[0], ids[1]]}, headers=staff_headers,
        )
        assert resp.status_code == 200, resp.text
        order = {s["id"]: s["sort_order"] for s in resp.json()["sessions"]}
        assert [order[i] for i in ids] == [1, 2, 0]

    def test_reorder_sessions_rejects_a_partial_list(
        self, client, event, staff_headers
    ):
        shift = _create(client, event, staff_headers, n_sessions=3)
        ids = [s["id"] for s in shift["sessions"]]

        resp = client.post(
            f"{BASE}/{shift['id']}/sessions/reorder",
            json={"session_ids": ids[:2]}, headers=staff_headers,
        )
        assert resp.status_code == 400
        assert "exactly once" in resp.json()["detail"]

    def test_reorder_sessions_rejects_another_shifts_session(
        self, client, event, staff_headers, db_session
    ):
        mine = _create(client, event, staff_headers, n_sessions=1)
        theirs = _create(client, event, staff_headers, name="Other", n_sessions=1)

        resp = client.post(
            f"{BASE}/{mine['id']}/sessions/reorder",
            json={"session_ids": [theirs["sessions"][0]["id"]]},
            headers=staff_headers,
        )
        assert resp.status_code == 400
