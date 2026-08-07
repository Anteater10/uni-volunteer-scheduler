"""Fixtures for copilot agent boundary tests."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models import Event, UserRole
from tests.fixtures.helpers import make_user

def iso_monday(year: int, week: int, hour: int = 9) -> datetime:
    """UTC datetime inside ISO week ``year``-W``week``.

    K7: these fixtures used to stamp `week_number=22` on an event whose
    start_date was "tomorrow", so the week the row claimed and the week it was
    actually in had nothing to do with each other. The tools matched on
    week_number, so the tests passed while production — where week_number is
    the quarter-relative 1..11 cache — returned nothing. Anchoring start_date
    to the week the fixture names is what makes these tests mean something.
    """
    return datetime.combine(
        date.fromisocalendar(year, week, 1), time(hour, 0), tzinfo=timezone.utc
    )


@pytest.fixture(autouse=True)
def _reset_registry():
    from app.copilot.agent import confirmation
    from app.copilot.agent.tools import registry
    registry._reset_for_tests()
    confirmation._reset_for_tests()
    yield
    registry._reset_for_tests()
    confirmation._reset_for_tests()


@pytest.fixture
def seed_events(db_session):
    """Seed three events: two owned by organizer A, one by organizer B.

    Yields (uuid_a, uuid_b, [event_ids]). Transactional rollback in the
    ``db_session`` fixture cleans everything up after the test.
    """
    org_a = make_user(db_session, role=UserRole.organizer)
    org_b = make_user(db_session, role=UserRole.organizer)
    uuid_a = org_a.id
    uuid_b = org_b.id

    now = iso_monday(2026, 22)
    e1, e2, e3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db_session.add_all([
        Event(
            id=e1,
            owner_id=uuid_a,
            title="A-evt-1",
            start_date=now,
            end_date=now + timedelta(hours=2),
            year=2026,
            week_number=22,
            school="Adams Elementary",
        ),
        Event(
            id=e2,
            owner_id=uuid_a,
            title="A-evt-2",
            start_date=now,
            end_date=now + timedelta(hours=2),
            year=2026,
            week_number=22,
            school="Adams Elementary",
        ),
        Event(
            id=e3,
            owner_id=uuid_b,
            title="B-evt-1",
            start_date=now,
            end_date=now + timedelta(hours=2),
            year=2026,
            week_number=22,
            school="Brandon Middle",
        ),
    ])
    db_session.flush()
    yield uuid_a, uuid_b, [e1, e2, e3]


@pytest.fixture
def seed_full_world(db_session):
    """Richer fixture for functional happy-path scenarios.

    Seeds:
    - Two organizers (org_a, org_b) and one admin user.
    - Four events across 4 distinct ISO weeks (W19-W22, year 2026):
      * W22: A-evt-1 (org_a, Adams) — 1 signup against capacity=5 -> understaffed
      * W21: A-evt-2 (org_a, Adams) — 2 signups against capacity=4
      * W20: B-evt-1 (org_b, Brandon) — 0 signups against capacity=10 -> most understaffed
      * W19: B-evt-2 (org_b, Brandon) — 3 signups against capacity=3
    - Each event has one slot; signups are confirmed.
    - One extra volunteer not signed up to anything.

    Yields a dict with: org_a_id, org_b_id, admin_id, event_ids (dict by title),
    slot_ids (dict by event title), volunteer_ids (list).
    """
    from app.models import ShiftSignup, SignupStatus, Slot, SlotType, Volunteer
    from tests.fixtures.helpers import make_shift
    org_a = make_user(db_session, role=UserRole.organizer)
    org_b = make_user(db_session, role=UserRole.organizer)
    admin = make_user(db_session, role=UserRole.admin)

    # (title, owner_id, school, year, week, capacity, num_signups)
    spec = [
        ("A-evt-1", org_a.id, "Adams Elementary", 2026, 22, 5, 1),
        ("A-evt-2", org_a.id, "Adams Elementary", 2026, 21, 4, 2),
        ("B-evt-1", org_b.id, "Brandon Middle",   2026, 20, 10, 0),
        ("B-evt-2", org_b.id, "Brandon Middle",   2026, 19, 3, 3),
    ]

    event_ids: dict = {}
    # The session slot of each event's shift. Kept in the payload because the
    # adversarial cases address slots by id; nothing books one directly.
    slot_ids: dict = {}
    shift_ids: dict = {}
    volunteer_ids: list = []

    for title, owner_id, school, year, wk, capacity, n_signups in spec:
        # Each event sits in the ISO week its spec row names, rather than all
        # four sharing one timestamp and disagreeing about it.
        base = iso_monday(year, wk)
        eid = uuid.uuid4()
        sid = uuid.uuid4()
        event_ids[title] = eid
        slot_ids[title] = sid
        ev = Event(
            id=eid,
            owner_id=owner_id,
            title=title,
            start_date=base,
            end_date=base + timedelta(hours=2),
            year=year,
            week_number=wk,
            school=school,
        )
        db_session.add(ev)
        db_session.flush()
        # 2026-08-02 shifts: the classroom work is a shift with session slots
        # under it, and capacity lives on the shift. A bare period slot with
        # signups against it is no longer representable — nor is it what any of
        # these tools would meet in production.
        shift = make_shift(db_session, eid, name=f"{title} shift", capacity=capacity)
        shift_ids[title] = shift.id
        sl = Slot(
            id=sid,
            event_id=eid,
            shift_id=shift.id,
            sort_order=0,
            start_time=base,
            end_time=base + timedelta(hours=2),
            capacity=capacity,
            current_count=0,
            slot_type=SlotType.PERIOD,
            date=base.date(),
        )
        db_session.add(sl)
        db_session.flush()
        for _ in range(n_signups):
            vol = Volunteer(
                id=uuid.uuid4(),
                email=f"v-{uuid.uuid4().hex[:8]}@example.com",
                first_name="V",
                last_name="X",
            )
            db_session.add(vol)
            db_session.flush()
            db_session.add(
                ShiftSignup(
                    id=uuid.uuid4(),
                    volunteer_id=vol.id,
                    shift_id=shift.id,
                    status=SignupStatus.confirmed,
                )
            )
            shift.current_count += 1
            sl.current_count += 1
            db_session.flush()
            volunteer_ids.append(vol.id)

    # Extra unsigned volunteer
    extra = Volunteer(
        id=uuid.uuid4(),
        email=f"extra-{uuid.uuid4().hex[:8]}@example.com",
        first_name="E",
        last_name="X",
    )
    db_session.add(extra)
    db_session.flush()

    yield {
        "org_a_id": org_a.id,
        "org_b_id": org_b.id,
        "admin_id": admin.id,
        "event_ids": event_ids,
        "slot_ids": slot_ids,
        "shift_ids": shift_ids,
        "volunteer_ids": volunteer_ids,
        "extra_volunteer_id": extra.id,
    }
