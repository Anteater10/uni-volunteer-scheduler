"""Seed a single event whose slot is inside the check-in window RIGHT NOW.

Run inside the backend container so it picks up the production DATABASE_URL:

    docker compose exec backend python -m scripts.seed_live_event

Idempotent by event title — re-running updates the slot to start 5 minutes
ago so the check-in window stays open.

Test volunteer email: live-test@e2e.example.com
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone, date

from app.database import SessionLocal
from app.models import (
    Event,
    Quarter,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    User,
    UserRole,
    Volunteer,
)
from app.routers.public.events import derive_quarter_week

EVENT_TITLE = "LIVE Check-in Test Event"
VOLUNTEER_EMAIL = "live-test@e2e.example.com"
ORGANIZER_EMAIL = "organizer@e2e.example.com"


def main() -> int:
    db = SessionLocal()
    try:
        organizer = (
            db.query(User).filter(User.email == ORGANIZER_EMAIL).one_or_none()
        )
        if organizer is None:
            print(
                f"ERROR: no user with email {ORGANIZER_EMAIL}. Run the "
                f"normal seed first (seed_e2e.py or /login page bootstrap).",
                file=sys.stderr,
            )
            return 1

        now = datetime.now(timezone.utc)
        slot_start = now - timedelta(minutes=5)   # 5 min ago → inside window
        slot_end = now + timedelta(hours=1)
        qstr, qyear, qweek = derive_quarter_week(now.date())
        qenum = Quarter(qstr)

        event = (
            db.query(Event).filter(Event.title == EVENT_TITLE).one_or_none()
        )
        if event is None:
            event = Event(
                id=uuid.uuid4(),
                owner_id=organizer.id,
                title=EVENT_TITLE,
                description="Seeded live test event — slot already started.",
                location="Check-in Test Location",
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(hours=2),
                visibility="public",
                quarter=qenum,
                year=qyear,
                week_number=qweek,
                school="Test High School",
            )
            db.add(event)
            db.flush()
            print(f"Created event {event.id}")
        else:
            event.start_date = now - timedelta(hours=1)
            event.end_date = now + timedelta(hours=2)
            event.quarter = qenum
            event.year = qyear
            event.week_number = qweek
            event.school = event.school or "Test High School"
            print(f"Reusing event {event.id}")

        slot = (
            db.query(Slot).filter(Slot.event_id == event.id).first()
        )
        # capacity=1 so the slot is at-capacity with one confirmed signup — a
        # second participant going through /events will be waitlisted
        # (useful for smoke-testing Phase 25 auto-promote).
        if slot is None:
            slot = Slot(
                id=uuid.uuid4(),
                event_id=event.id,
                start_time=slot_start,
                end_time=slot_end,
                capacity=1,
                current_count=1,
                slot_type=SlotType.PERIOD,
                date=date.today(),
                location="Check-in Test Location",
            )
            db.add(slot)
            db.flush()
            print(f"Created slot {slot.id}")
        else:
            slot.start_time = slot_start
            slot.end_time = slot_end
            slot.capacity = 1
            slot.current_count = 1
            print(f"Reset slot {slot.id} start_time to {slot_start.isoformat()}")

        volunteer = (
            db.query(Volunteer)
            .filter(Volunteer.email == VOLUNTEER_EMAIL)
            .one_or_none()
        )
        if volunteer is None:
            volunteer = Volunteer(
                id=uuid.uuid4(),
                email=VOLUNTEER_EMAIL,
                first_name="Live",
                last_name="Tester",
                phone_e164="+18055559999",
            )
            db.add(volunteer)
            db.flush()
            print(f"Created volunteer {volunteer.id}")
        else:
            print(f"Reusing volunteer {volunteer.id}")

        # Delete any stale signups on this slot from prior test rounds (other
        # volunteers). Hard-delete so the UNIQUE(volunteer_id, slot_id)
        # constraint doesn't block those volunteers from re-signing up to
        # test the waitlist flow. The seeder owns a clean
        # "capacity=1, live-test confirmed, no others" starting state.
        stale = (
            db.query(Signup)
            .filter(
                Signup.slot_id == slot.id,
                Signup.volunteer_id != volunteer.id,
            )
            .all()
        )
        for s in stale:
            sid = s.id
            prev = s.status
            db.delete(s)
            print(f"Deleted stale signup {sid} (was {prev})")
        if stale:
            db.flush()

        signup = (
            db.query(Signup)
            .filter(Signup.slot_id == slot.id, Signup.volunteer_id == volunteer.id)
            .one_or_none()
        )
        if signup is None:
            signup = Signup(
                id=uuid.uuid4(),
                volunteer_id=volunteer.id,
                slot_id=slot.id,
                status=SignupStatus.confirmed,
            )
            db.add(signup)
            db.flush()
            print(f"Created signup {signup.id}")
        else:
            signup.status = SignupStatus.confirmed
            signup.checked_in_at = None
            print(f"Reset signup {signup.id} to confirmed")

        db.commit()
        print()
        print("=" * 60)
        print("READY TO TEST")
        print("=" * 60)
        print(f"Event ID:         {event.id}")
        print(f"Event title:      {event.title}")
        print(f"Slot window:      {slot_start.isoformat()} → {slot_end.isoformat()}")
        print(f"Volunteer email:  {VOLUNTEER_EMAIL}")
        print()
        print("Admin page: /admin/events/%s" % event.id)
        print("QR target:  /event-check-in/%s" % event.id)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
