"""Simulate a full quarter of volunteer-scheduler activity.

Builds an AcademicQuarter, a set of Module templates, a pool of volunteers,
and ~10 weeks of Events -> Shifts -> Sessions -> ShiftSignups, with
SessionAttendance resolved for everything except the final week (left
"pending" so the admin resolve-event flow has something to do).

Modeled on the weekly schedule pattern from a real Dos Pueblos HS outreach
log (Mon-Fri, Period 1 + Period 2, rotating volunteer rosters per period),
plus two lighter secondary school partnerships and a one-time volunteer
orientation event.

Run it the same way seed_admin.py runs:

    docker compose exec backend python -m app.seed_quarter_demo

Env vars:
    RESET_DEMO=1        Delete previously-seeded demo data before reseeding
                         (safe to rerun; matches by the school names + quarter
                         used below, so it never touches unrelated data).
    QUARTER_SEED=<int>  Change the random seed (default 42) to get a
                         differently-shaped, still-deterministic dataset.
"""
import os
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone

from app.database import SessionLocal
from app import models
from app.deps import hash_password
from app.services.shift_service import default_shift_name

# -------------------------
# Config
# -------------------------

SEED = int(os.getenv("QUARTER_SEED", "42"))
WEEKS = 10
QUARTER_SEASON = models.Quarter.SPRING
QUARTER_YEAR = 2026
QUARTER_START = date(2026, 4, 6)  # Monday, week 1

ORGANIZER_EMAIL = "coordinator@ucsb.edu"
ORGANIZER_NAME = "Program Coordinator"
ORGANIZER_PASSWORD = os.getenv("SEED_ORGANIZER_PASSWORD", "ChangeMe123!")

DEMO_SCHOOLS = ["Dos Pueblos HS", "La Colina Junior High"]

PT = timezone(timedelta(hours=-7))  # PDT, close enough for seeded demo data


def _dt(d: date, hour: int, minute: int) -> datetime:
    """Build a UTC-aware datetime from a local (PT) wall-clock time."""
    local = datetime.combine(d, time(hour, minute), tzinfo=PT)
    return local.astimezone(timezone.utc)


# -------------------------
# Modules
# -------------------------
# The real SciTrek module catalog is seeded by Alembic migration
# 0038_seed_scitrek_modules (idempotent, ON CONFLICT DO NOTHING) — this
# script does NOT create modules, it just uses the ones already in the DB.
# `glucose-sensing` is the exact module from the screenshot this dataset is
# modeled on. Run `alembic upgrade head` before this script if the catalog
# isn't there yet.

HIGH_SCHOOL_MODULE_SLUGS = [
    "glucose-sensing",
    "crispr-gene-editing-basics",
    "crispr-mutations-knockout-strategies",
    "bioinformatics-gene-expression-cancer",
    "thermodynamics-heat-transfer-calorimetry",
]
MIDDLE_SCHOOL_MODULE_SLUGS = [
    "best-bread",
    "conservation-of-mass",
    "germs",
    "waves",
]
ALL_MODULE_SLUGS = HIGH_SCHOOL_MODULE_SLUGS + MIDDLE_SCHOOL_MODULE_SLUGS

# -------------------------
# Volunteer pool (first, last) — team leads appear far more often than
# one-off participants, mirroring the real roster's repeat names.
# -------------------------

LEAD_VOLUNTEERS = [
    ("Isa", "Farooqi"), ("Martin", "Reyes"), ("Brian", "Delgado"),
    ("Andy", "Kim"), ("Daniel", "Osei"), ("Emilio", "Vega"),
    ("Lexi", "Tran"), ("Trisha", "Nair"), ("Sophia", "Bianchi"),
    ("Kalani", "Akana"),
]

REGULAR_VOLUNTEERS = [
    ("Chloe", "Chon"), ("Samuel", "Rivera"), ("Flyn", "Olson"),
    ("Gabriel", "Wilkinson"), ("Jenny", "Gibson"), ("Sophia", "Howard"),
    ("John", "Hu"), ("Ava", "Gardner"), ("Natalia", "Christian"),
    ("Chloe", "Chang"), ("Malerie", "Gonzales"), ("Miguel", "Orozco"),
    ("Ishaan", "Shah"), ("Kaden", "Wheeler"), ("Josh", "Buccat"),
    ("Danielle", "McGary"), ("Sareena", "Gavaskar"), ("Nicole", "Rodriguez"),
    ("Fatima", "Lopez"), ("Kai", "Huynh"), ("Jacqueline", "Coen"),
    ("Delila", "Ruesch"), ("Joanna", "Basbous"), ("Yulia", "Ivanytskyy"),
]


def _email_for(first: str, last: str) -> str:
    return f"{first.lower()}.{last.lower()}@ucsb.edu".replace(" ", "")


def _phone_for(index: int) -> str:
    return f"+1805555{index:04d}"


# -------------------------
# Setup helpers
# -------------------------


def get_or_create_organizer(db) -> models.User:
    user = db.query(models.User).filter(models.User.email == ORGANIZER_EMAIL).first()
    if user:
        return user
    user = models.User(
        name=ORGANIZER_NAME,
        email=ORGANIZER_EMAIL,
        role=models.UserRole.organizer,
        hashed_password=hash_password(ORGANIZER_PASSWORD),
        notify_email=True,
    )
    db.add(user)
    db.flush()
    print(f"Created organizer: {user.email} (password: {ORGANIZER_PASSWORD})")
    return user


def get_or_create_quarter(db) -> models.AcademicQuarter:
    existing = (
        db.query(models.AcademicQuarter)
        .filter(
            models.AcademicQuarter.season == QUARTER_SEASON,
            models.AcademicQuarter.year == QUARTER_YEAR,
            models.AcademicQuarter.label == "",
        )
        .first()
    )
    if existing:
        return existing
    last_week_start = QUARTER_START + timedelta(weeks=WEEKS - 1)
    end_date = last_week_start + timedelta(days=4)  # Friday of the final week
    quarter = models.AcademicQuarter(
        season=QUARTER_SEASON,
        year=QUARTER_YEAR,
        label="",
        start_date=QUARTER_START,
        end_date=end_date,
    )
    db.add(quarter)
    db.flush()
    print(f"Created quarter: {quarter.display_name} ({quarter.start_date} - {quarter.end_date}, "
          f"{quarter.weeks_in_quarter} weeks)")
    return quarter


def get_modules(db) -> dict[str, models.Module]:
    rows = (
        db.query(models.Module)
        .filter(models.Module.slug.in_(ALL_MODULE_SLUGS), models.Module.deleted_at.is_(None))
        .all()
    )
    modules = {m.slug: m for m in rows}
    missing = set(ALL_MODULE_SLUGS) - set(modules)
    if missing:
        raise SystemExit(
            f"Missing expected SciTrek modules: {sorted(missing)}. "
            "Run `alembic upgrade head` (migration 0038_seed_scitrek_modules) first."
        )
    return modules


def get_or_create_volunteers(db) -> tuple[list[models.Volunteer], list[models.Volunteer]]:
    leads, regulars = [], []
    idx = 0
    for pool, bucket in ((LEAD_VOLUNTEERS, leads), (REGULAR_VOLUNTEERS, regulars)):
        for first, last in pool:
            idx += 1
            email = _email_for(first, last)
            vol = db.query(models.Volunteer).filter(models.Volunteer.email == email).first()
            if not vol:
                vol = models.Volunteer(
                    email=email,
                    first_name=first,
                    last_name=last,
                    phone_e164=_phone_for(idx),
                )
                db.add(vol)
            bucket.append(vol)
    db.flush()
    return leads, regulars


def reset_demo_data(db, quarter: models.AcademicQuarter) -> None:
    events = (
        db.query(models.Event)
        .filter(
            models.Event.quarter_id == quarter.id,
            models.Event.school.in_(DEMO_SCHOOLS + ["UCSB (Orientation)"]),
        )
        .all()
    )
    if not events:
        return
    print(f"RESET_DEMO=1: deleting {len(events)} previously-seeded events for this quarter...")
    for ev in events:
        db.delete(ev)  # cascades: slots/shifts/signups/etc. per model relationships
    db.flush()


# -------------------------
# Attendance simulation
# -------------------------


def _resolve_shift_signup(db, rng: random.Random, shift_signup: models.ShiftSignup,
                           sessions: list[models.Slot]) -> None:
    """Mark a confirmed shift signup as attended/no_show across its session(s)."""
    if shift_signup.status != models.SignupStatus.confirmed:
        return
    shift_signup.status = models.SignupStatus.confirmed  # lifecycle unchanged
    roll = rng.random()
    for session in sessions:
        if roll < 0.87:
            outcome = models.SignupStatus.attended
            checked_in_at = session.start_time + timedelta(minutes=rng.randint(-5, 8))
        elif roll < 0.95:
            outcome = models.SignupStatus.no_show
            checked_in_at = None
        else:
            outcome = models.SignupStatus.checked_in
            checked_in_at = session.start_time + timedelta(minutes=rng.randint(-5, 8))
        db.add(models.SessionAttendance(
            shift_signup_id=shift_signup.id,
            slot_id=session.id,
            status=outcome,
            checked_in_at=checked_in_at,
        ))


def _resolve_signup(rng: random.Random, signup: models.Signup) -> None:
    """Orientation (plain Signup) attendance."""
    if signup.status != models.SignupStatus.confirmed:
        return
    roll = rng.random()
    if roll < 0.90:
        signup.status = models.SignupStatus.attended
        signup.checked_in_at = signup.slot.start_time + timedelta(minutes=rng.randint(-5, 5))
    else:
        signup.status = models.SignupStatus.no_show


# -------------------------
# Core builders
# -------------------------


def book_shift(db, rng: random.Random, shift: models.Shift, leads: list, regulars: list,
                n_leads: int, n_regulars: int) -> list[models.ShiftSignup]:
    """Sample volunteers into a shift, respecting capacity (overflow -> waitlisted)."""
    chosen = rng.sample(leads, k=min(n_leads, len(leads))) + \
        rng.sample(regulars, k=min(n_regulars, len(regulars)))
    rng.shuffle(chosen)

    created = []
    for i, volunteer in enumerate(chosen):
        status = models.SignupStatus.confirmed if i < shift.capacity else models.SignupStatus.waitlisted
        signup = models.ShiftSignup(
            shift_id=shift.id,
            volunteer_id=volunteer.id,
            status=status,
            timestamp=datetime.now(timezone.utc) - timedelta(days=rng.randint(3, 21), minutes=rng.randint(0, 500)),
        )
        db.add(signup)
        db.flush()
        created.append(signup)
        if status == models.SignupStatus.confirmed:
            shift.current_count += 1
    return created


def build_single_session_shift(db, event: models.Event, sort_order: int, name: str,
                                start: datetime, end: datetime, location: str,
                                capacity: int) -> models.Shift:
    shift = models.Shift(
        event_id=event.id,
        name=name,
        sort_order=sort_order,
        capacity=capacity,
        current_count=0,
    )
    db.add(shift)
    db.flush()
    db.add(models.Slot(
        event_id=event.id,
        shift_id=shift.id,
        slot_type=models.SlotType.PERIOD,
        start_time=start,
        end_time=end,
        date=start.astimezone(PT).date(),
        location=location,
        name=None,
        sort_order=0,
        capacity=1,
        current_count=0,
    ))
    db.flush()
    return shift


def build_dos_pueblos_week(db, rng, organizer, quarter, module, leads, regulars, week_number: int,
                            week_start: date, resolve: bool) -> models.Event:
    """Mon-Fri, Period 1 (8:00-10:30) + Period 2 (9:40-12:20), matching the
    real block-schedule pattern (P1 and P2 overlap; different sections)."""
    monday = week_start
    friday = week_start + timedelta(days=4)
    event = models.Event(
        owner_id=organizer.id,
        title=f"{module.name} \u2014 Dos Pueblos HS (Mike Lynch) \u2014 Week {week_number}",
        description=(
            "Weekly outreach at Dos Pueblos HS with teacher Mike Lynch. "
            "Period 1: ~29 students. Period 2: ~31 students."
        ),
        location="Dos Pueblos High School, Goleta, CA",
        visibility="public",
        start_date=_dt(monday, 7, 0),
        end_date=_dt(friday, 13, 0),
        school="Dos Pueblos HS",
        module_slug=module.slug,
        quarter=quarter.season,
        year=quarter.year,
        week_number=week_number,
        quarter_id=quarter.id,
        reminder_1h_enabled=True,
    )
    db.add(event)
    db.flush()

    sort_order = 0
    all_shift_sessions = []
    for day_offset in range(5):  # Mon..Fri
        day = monday + timedelta(days=day_offset)
        p1 = build_single_session_shift(
            db, event, sort_order,
            default_shift_name(_dt(day, 8, 0), _dt(day, 10, 30)),
            _dt(day, 8, 0), _dt(day, 10, 30),
            "Dos Pueblos HS \u2014 Rm 214", capacity=6,
        )
        sort_order += 1
        p2 = build_single_session_shift(
            db, event, sort_order,
            default_shift_name(_dt(day, 9, 40), _dt(day, 12, 20)),
            _dt(day, 9, 40), _dt(day, 12, 20),
            "Dos Pueblos HS \u2014 Rm 214", capacity=6,
        )
        sort_order += 1

        for shift in (p1, p2):
            n_leads = rng.choice([1, 1, 2, 2, 3])
            n_regulars = rng.choice([0, 1, 1, 2, 2, 3])
            book_shift(db, rng, shift, leads, regulars, n_leads, n_regulars)
            all_shift_sessions.append(shift)

    db.flush()

    if resolve:
        for shift in all_shift_sessions:
            sessions = list(shift.sessions)
            for ss in shift.shift_signups:
                _resolve_shift_signup(db, rng, ss, sessions)
        event.completed_at = _dt(friday, 13, 0)

    return event


def build_secondary_event(db, rng, organizer, quarter, module, school: str, teacher: str,
                           leads, regulars, week_number: int, week_start: date,
                           resolve: bool) -> models.Event:
    """Lighter partnership: Tue + Thu, one period each."""
    tuesday = week_start + timedelta(days=1)
    thursday = week_start + timedelta(days=3)
    event = models.Event(
        owner_id=organizer.id,
        title=f"{module.name} \u2014 {school} ({teacher}) \u2014 Week {week_number}",
        description=f"Outreach at {school} with teacher {teacher}.",
        location=f"{school}, Santa Barbara, CA",
        visibility="public",
        start_date=_dt(tuesday, 7, 0),
        end_date=_dt(thursday, 13, 0),
        school=school,
        module_slug=module.slug,
        quarter=quarter.season,
        year=quarter.year,
        week_number=week_number,
        quarter_id=quarter.id,
        reminder_1h_enabled=True,
    )
    db.add(event)
    db.flush()

    shifts = []
    for i, day in enumerate((tuesday, thursday)):
        shift = build_single_session_shift(
            db, event, i,
            default_shift_name(_dt(day, 13, 0), _dt(day, 14, 30)),
            _dt(day, 13, 0), _dt(day, 14, 30),
            f"{school} \u2014 Science Lab", capacity=5,
        )
        n_leads = rng.choice([0, 1, 1])
        n_regulars = rng.choice([1, 2, 2, 3])
        book_shift(db, rng, shift, leads, regulars, n_leads, n_regulars)
        shifts.append(shift)

    db.flush()

    if resolve:
        for shift in shifts:
            sessions = list(shift.sessions)
            for ss in shift.shift_signups:
                _resolve_shift_signup(db, rng, ss, sessions)
        event.completed_at = _dt(thursday, 14, 30)

    return event


def build_orientation_event(db, rng, organizer, quarter, leads, regulars,
                             resolve: bool) -> models.Event:
    """Orientation isn't tied to a SciTrek content module (module_slug=None) —
    it's the volunteer-training session, using SlotType.ORIENTATION."""
    day = QUARTER_START - timedelta(days=3)  # the Friday before week 1
    event = models.Event(
        owner_id=organizer.id,
        title=f"New Volunteer Orientation \u2014 {quarter.display_name}",
        description="Required orientation session for all new outreach volunteers this quarter.",
        location="UCSB, Bioengineering Bldg Rm 1001",
        visibility="public",
        start_date=_dt(day, 16, 0),
        end_date=_dt(day, 17, 0),
        school="UCSB (Orientation)",
        module_slug=None,
        quarter=quarter.season,
        year=quarter.year,
        week_number=0,
        quarter_id=quarter.id,
    )
    db.add(event)
    db.flush()

    slot = models.Slot(
        event_id=event.id,
        slot_type=models.SlotType.ORIENTATION,
        start_time=_dt(day, 16, 0),
        end_time=_dt(day, 17, 0),
        date=day,
        location=event.location,
        name="Orientation",
        sort_order=0,
        capacity=40,
        current_count=0,
    )
    db.add(slot)
    db.flush()

    attendees = leads + rng.sample(regulars, k=min(15, len(regulars)))
    for volunteer in attendees:
        signup = models.Signup(
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=models.SignupStatus.confirmed,
            timestamp=_dt(day, 16, 0) - timedelta(days=rng.randint(2, 10)),
        )
        db.add(signup)
        db.flush()
        slot.current_count += 1
        if resolve:
            _resolve_signup(rng, signup)

    db.flush()
    if resolve:
        event.completed_at = _dt(day, 17, 0)
    return event


# -------------------------
# Main
# -------------------------


def main():
    rng = random.Random(SEED)
    db = SessionLocal()
    try:
        quarter = get_or_create_quarter(db)
        db.commit()

        if os.getenv("RESET_DEMO") == "1":
            reset_demo_data(db, quarter)
            db.commit()

        organizer = get_or_create_organizer(db)
        modules = get_modules(db)
        leads, regulars = get_or_create_volunteers(db)
        db.commit()

        # Dos Pueblos rotates through the high-school modules, ~2 weeks each,
        # starting on glucose-sensing to match the source screenshot (Week 8
        # in the real log was mid-rotation on Glucose Sensing).
        rotation = [HIGH_SCHOOL_MODULE_SLUGS[i % len(HIGH_SCHOOL_MODULE_SLUGS)]
                    for i in range(WEEKS)]

        # Lighter Tue/Thu partnership at a middle school, active every other
        # week, cycling through the middle-school-level modules.
        secondary_schedule = {
            week: ("La Colina Junior High", "Priya Anand",
                   MIDDLE_SCHOOL_MODULE_SLUGS[idx % len(MIDDLE_SCHOOL_MODULE_SLUGS)])
            for idx, week in enumerate([2, 4, 6, 8, 9])
        }

        build_orientation_event(
            db, rng, organizer, quarter, leads, regulars, resolve=True,
        )
        db.commit()

        events_created = 1
        for week_number in range(1, WEEKS + 1):
            week_start = QUARTER_START + timedelta(weeks=week_number - 1)
            resolve = week_number < WEEKS  # leave the final week un-resolved

            module = modules[rotation[week_number - 1]]
            build_dos_pueblos_week(
                db, rng, organizer, quarter, module, leads, regulars,
                week_number, week_start, resolve,
            )
            events_created += 1

            if week_number in secondary_schedule:
                school, teacher, mod_slug = secondary_schedule[week_number]
                build_secondary_event(
                    db, rng, organizer, quarter, modules[mod_slug], school, teacher,
                    leads, regulars, week_number, week_start, resolve,
                )
                events_created += 1

            db.commit()
            print(f"Week {week_number}/{WEEKS} seeded"
                  + (" (left pending resolution)" if not resolve else ""))

        print(f"\nDone. Seeded {events_created} events across {quarter.display_name} "
              f"({quarter.weeks_in_quarter} weeks), {len(leads) + len(regulars)} volunteers.")
        print(f"Organizer login: {ORGANIZER_EMAIL} / {ORGANIZER_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()