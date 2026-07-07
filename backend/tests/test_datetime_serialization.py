"""Staff event/slot payloads must serialize timezone-aware UTC datetimes.

Every datetime column is timestamptz, but the EventRead/SlotRead schemas
inherited the strip-to-naive input validators from their Base classes, so
/events payloads went out with no UTC offset and `new Date()` in the browser
read them as *local* time — the organizer dashboard wrong-clock bug.
"""
import re

from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import UserRole

AWARE_RE = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class TestEventDatetimesAreUtcAware:
    def test_event_detail_datetimes_carry_offset(self, client, db_session):
        admin = make_user(db_session, role=UserRole.admin)
        event, _slot = make_event_with_slot(db_session, owner=admin)
        db_session.commit()

        resp = client.get(
            f"/api/v1/events/{event.id}", headers=auth_headers(client, admin)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert AWARE_RE.search(data["start_date"]), (
            f"start_date serialized naive: {data['start_date']}"
        )
        assert AWARE_RE.search(data["end_date"])
        assert data["slots"], "expected the embedded slot"
        assert AWARE_RE.search(data["slots"][0]["start_time"]), (
            f"slot start_time serialized naive: {data['slots'][0]['start_time']}"
        )
        assert AWARE_RE.search(data["slots"][0]["end_time"])

    def test_event_list_datetimes_carry_offset(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        make_event_with_slot(db_session, owner=organizer)
        db_session.commit()

        resp = client.get("/api/v1/events/", headers=auth_headers(client, organizer))
        assert resp.status_code == 200
        events = resp.json()
        assert events
        assert AWARE_RE.search(events[0]["start_date"]), events[0]["start_date"]

    def test_read_schemas_keep_tzinfo(self, db_session):
        """Unit level: model validation must not strip tzinfo on Read."""
        from app.schemas import EventRead

        admin = make_user(db_session, role=UserRole.admin)
        event, _slot = make_event_with_slot(db_session, owner=admin)
        db_session.flush()

        read = EventRead.model_validate(event)
        assert read.start_date.tzinfo is not None
        assert read.slots[0].start_time.tzinfo is not None
