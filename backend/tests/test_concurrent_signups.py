"""Signups under real concurrency: many requests hitting the same seat at once.

Each thread gets its own Postgres session and transaction, exactly like two
browsers posting at the same moment, and a Barrier releases them together.
What must hold:

  * a seat is never sold twice — a 1-seat shift ends with one booking holding
    it, everyone else waitlisted, and current_count == 1 (never 2, never -1);
  * the same person double-clicking gets one booking and clean 409s, not a 500;
  * two people booking the same pair of shifts in opposite orders do not
    deadlock;
  * two staff cancelling the same booking at once free the seat once.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.services.public_signup_service import create_public_signup

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs",
)
N = 10


@pytest.fixture(scope="module")
def race_engine(engine):
    """A pool big enough for N simultaneous sessions. Depends on the shared
    ``engine`` fixture, which is what creates the schema."""
    eng = create_engine(TEST_DATABASE_URL, pool_size=N + 2, max_overflow=N)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def no_mail(monkeypatch):
    monkeypatch.setattr("app.celery_app.send_signup_confirmation_email.delay", lambda **k: None)
    monkeypatch.setattr("app.celery_app.send_admin_signup_notification_email.delay", lambda **k: None)
    monkeypatch.setattr("app.celery_app.send_email_notification.delay", lambda **k: None)


@pytest.fixture
def world(race_engine):
    """Committed event + shifts + a 1-seat orientation, visible to every
    thread; removed afterwards so nothing leaks into other tests."""
    Session = sessionmaker(bind=race_engine)
    s = Session()
    owner = models.User(
        id=uuid.uuid4(), name="Race Owner", email=f"race-{uuid.uuid4().hex[:8]}@x.com",
        hashed_password="x", role=models.UserRole.admin,
    )
    s.add(owner)
    s.flush()
    start = datetime.now(timezone.utc) + timedelta(days=3)
    event = models.Event(
        id=uuid.uuid4(), owner_id=owner.id, title="Race event",
        start_date=start, end_date=start + timedelta(days=2), visibility="public",
    )
    s.add(event)
    s.flush()
    shifts = []
    for i in range(2):
        sh = models.Shift(event_id=event.id, name=f"Shift {i}", sort_order=i, capacity=1, current_count=0)
        s.add(sh)
        s.flush()
        s.add(models.Slot(
            event_id=event.id, shift_id=sh.id, sort_order=0, slot_type=models.SlotType.PERIOD,
            start_time=start + timedelta(hours=i), end_time=start + timedelta(hours=i + 1),
            date=start.date(), capacity=1, current_count=0,
        ))
        shifts.append(sh)
    s.commit()
    data = {"owner_id": owner.id, "event_id": event.id, "shift_ids": [sh.id for sh in shifts]}
    s.close()
    yield data

    s = Session()
    vol_ids = [
        v for (v,) in s.query(models.ShiftSignup.volunteer_id)
        .filter(models.ShiftSignup.shift_id.in_(data["shift_ids"])).all()
    ] + [
        v for (v,) in s.query(models.Signup.volunteer_id)
        .join(models.Slot).filter(models.Slot.event_id == data["event_id"]).all()
    ]
    ss_ids = [i for (i,) in s.query(models.ShiftSignup.id).filter(models.ShiftSignup.shift_id.in_(data["shift_ids"]))]
    slot_ids = [i for (i,) in s.query(models.Slot.id).filter(models.Slot.event_id == data["event_id"])]
    s.query(models.MagicLinkToken).filter(models.MagicLinkToken.shift_signup_id.in_(ss_ids)).delete(synchronize_session=False)
    s.query(models.Signup).filter(models.Signup.slot_id.in_(slot_ids)).delete(synchronize_session=False)
    s.query(models.ShiftSignup).filter(models.ShiftSignup.id.in_(ss_ids)).delete(synchronize_session=False)
    s.query(models.AuditLog).filter(models.AuditLog.actor_id == data["owner_id"]).delete(synchronize_session=False)
    s.query(models.Slot).filter(models.Slot.event_id == data["event_id"]).delete(synchronize_session=False)
    s.query(models.Shift).filter(models.Shift.event_id == data["event_id"]).delete(synchronize_session=False)
    s.query(models.Event).filter(models.Event.id == data["event_id"]).delete(synchronize_session=False)
    s.query(models.Volunteer).filter(models.Volunteer.id.in_(vol_ids)).delete(synchronize_session=False)
    s.query(models.User).filter(models.User.id == data["owner_id"]).delete(synchronize_session=False)
    s.commit()
    s.close()


def _payload(email, shift_ids):
    return schemas.PublicSignupCreate(
        first_name="Race", last_name="Vol", email=email, phone="8055551234",
        slot_ids=[], shift_ids=list(shift_ids),
    )


def _race(engine, jobs):
    """Run each job(db) in its own session, all released at once. Returns a
    list of ('ok', result) / ('http', status) / ('error', exc) per job."""
    Session = sessionmaker(bind=engine)
    barrier = Barrier(len(jobs), timeout=20)

    def run(job):
        db = Session()
        try:
            barrier.wait()
            return ("ok", job(db))
        except HTTPException as exc:
            db.rollback()
            return ("http", exc.status_code)
        except Exception as exc:  # anything else is a failure of the test
            db.rollback()
            return ("error", repr(exc))
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(run, jobs))


def _shift(engine, shift_id):
    s = sessionmaker(bind=engine)()
    try:
        shift = s.get(models.Shift, shift_id)
        rows = s.query(models.ShiftSignup).filter_by(shift_id=shift_id).all()
        return shift.current_count, sorted(r.status.value for r in rows)
    finally:
        s.close()


def test_one_seat_ten_people_one_booking(race_engine, world):
    shift_id = world["shift_ids"][0]
    jobs = [
        (lambda db, i=i: create_public_signup(db, _payload(f"racer{i}-{uuid.uuid4().hex[:6]}@x.com", [shift_id])))
        for i in range(N)
    ]
    results = _race(race_engine, jobs)
    assert [r for r in results if r[0] != "ok"] == []
    count, statuses = _shift(race_engine, shift_id)
    assert count == 1  # never 2, never below zero
    assert statuses.count("pending") == 1
    assert statuses.count("waitlisted") == N - 1


def test_double_click_same_person_books_once(race_engine, world):
    shift_id = world["shift_ids"][0]
    email = f"clicker-{uuid.uuid4().hex[:6]}@x.com"
    results = _race(race_engine, [lambda db: create_public_signup(db, _payload(email, [shift_id]))] * 5)
    kinds = sorted(r[0] if r[0] != "http" else f"http{r[1]}" for r in results)
    assert kinds == ["http409"] * 4 + ["ok"], results
    count, statuses = _shift(race_engine, shift_id)
    assert (count, statuses) == (1, ["pending"])


def test_opposite_order_bookings_do_not_deadlock(race_engine, world):
    a, b = world["shift_ids"]
    jobs = []
    for i in range(N):
        order = [a, b] if i % 2 == 0 else [b, a]
        jobs.append(lambda db, i=i, order=order: create_public_signup(
            db, _payload(f"order{i}-{uuid.uuid4().hex[:6]}@x.com", order)))
    results = _race(race_engine, jobs)
    assert [r for r in results if r[0] != "ok"] == []
    for sid in (a, b):
        count, statuses = _shift(race_engine, sid)
        assert count == 1 and statuses.count("pending") == 1


def test_staff_add_volunteer_races_for_the_last_seat(race_engine, world):
    from app.routers.admin import admin_add_volunteer

    shift_id = world["shift_ids"][0]
    Session = sessionmaker(bind=race_engine)
    s = Session()
    owner = s.get(models.User, world["owner_id"])
    s.expunge(owner)
    s.close()

    def add(i):
        return lambda db: admin_add_volunteer(
            str(world["event_id"]),
            schemas.AdminAddVolunteer(
                first_name="Staff", last_name=f"Add{i}", email=f"staffadd{i}-{uuid.uuid4().hex[:6]}@x.com",
                shift_ids=[shift_id],
            ),
            db,
            db.merge(owner),
        )

    results = _race(race_engine, [add(i) for i in range(N)])
    assert [r for r in results if r[0] != "ok"] == []
    count, statuses = _shift(race_engine, shift_id)
    assert count == 1
    assert statuses.count("confirmed") == 1 and statuses.count("waitlisted") == N - 1


def test_two_staff_cancel_the_same_booking_frees_one_seat(race_engine, world):
    from app.routers.admin import admin_cancel_shift_signup

    shift_id = world["shift_ids"][0]
    booked = _race(race_engine, [lambda db: create_public_signup(db, _payload(f"cx-{uuid.uuid4().hex[:6]}@x.com", [shift_id]))])
    assert booked[0][0] == "ok"
    ss_id = booked[0][1].shift_signup_ids[0]

    Session = sessionmaker(bind=race_engine)
    s = Session()
    owner = s.get(models.User, world["owner_id"])
    s.expunge(owner)
    s.close()
    results = _race(
        race_engine, [lambda db: admin_cancel_shift_signup(str(ss_id), db, db.merge(owner))] * 5
    )
    assert [r for r in results if r[0] != "ok"] == []
    count, statuses = _shift(race_engine, shift_id)
    assert (count, statuses) == (0, ["cancelled"])  # 0, not -4
