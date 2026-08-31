"""Simulate Fall 2026 by extrapolating from the Spring 2026 seeded data.

This is NOT a copy of seed_quarter_demo.py — it reuses its low-level
primitives (booking, resolution, module/organizer lookup) but makes
different scheduling decisions based on what actually happened in Spring,
queried directly from this same database after running
`python -m app.seed_quarter_demo`:

    Observed Spring 2026 trends (from live query, not assumed):
      - Shift capacity utilization ~54% (600 capacity / 324 filled at
        Dos Pueblos, 50/26 at La Colina) and ZERO waitlisted signups —
        there was slack. A growing program should start filling shifts
        and occasionally waitlisting.
      - No-show rate 7.5% overall — reasonably healthy; a maturing
        program should nudge this down slightly, not up.
      - Module popularity (by signups): crispr-mutations-knockout-strategies
        (74) > thermodynamics (64, but this includes the never-resolved
        week-10 event) > glucose-sensing (62) ~ bioinformatics (62) ~
        crispr-gene-editing-basics (62). Middle-school modules had far
        fewer total signups, but La Colina only ran 5 of 10 weeks.
      - Volunteer participation was top-heavy: the 10 "lead" volunteers
        each worked 14-23 shifts; the least-active regulars worked only
        2-3. That's exactly the shape of a program with a strong core
        and a long tail of one-off participants — the long tail is where
        real-world attrition (graduation, schedule conflicts) shows up
        first, and where new-recruit growth gets absorbed.

    Fall 2026 modeling decisions that follow from that:
      1. GROWTH: higher booking density per shift (more leads/regulars
         sampled per shift) so utilization rises toward ~70-75% and a
         handful of shifts actually hit capacity -> real waitlisting,
         which Spring never produced.
      2. ROSTER CHURN: the 4 least-active Spring regulars are dropped
         from the active Fall pool (graduated / moved on — consistent
         with them being the least-engaged already). The 2 most-active
         Spring regulars (Malerie Gonzales, Chloe Chang) are promoted
         into the lead pool. 6 new recruits join as regulars. Net: the
         active volunteer base grows.
      3. EXPANSION: La Colina Junior High goes from biweekly to weekly
         (sustained middle-school demand), and a new partner —
         Santa Barbara HS — comes online starting week 4, using the
         same light Tue/Thu cadence La Colina started with.
      4. ATTENDANCE: nudged up slightly (90% attended / 6% no-show / 4%
         checked-in-only) vs Spring's (87/8/5), reflecting a maturing
         program rather than a fresh one.
      5. New recruits (only) get an orientation event — returning
         volunteers already hold permanent orientation credit from
         Spring (OrientationCredit is earned once, forever, per the
         orientation_service design), so re-orienting them would be
         wrong, not just redundant.

Run the same way as seed_quarter_demo.py — and after it, since this
script assumes Spring 2026 already exists and reads its own hardcoded
churn list rather than re-querying live (the query above was run once,
by hand, to inform these numbers; baking a live query into a seed script
would make it non-deterministic run to run):

    docker compose exec backend python -m app.seed_fall_quarter_demo

Env vars: RESET_DEMO=1, QUARTER_SEED=<int> (default 43 — different from
Spring's 42 on purpose, so the two quarters don't roll identically).
"""
import os
import random
from datetime import date, timedelta

from app.database import SessionLocal
from app import models
from app.seed_quarter_demo import (
    PT,
    HIGH_SCHOOL_MODULE_SLUGS,
    MIDDLE_SCHOOL_MODULE_SLUGS,
    ALL_MODULE_SLUGS,
    LEAD_VOLUNTEERS,
    REGULAR_VOLUNTEERS,
    _dt,
    _email_for,
    _phone_for,
    get_or_create_organizer,
    get_modules,
    book_shift,
    build_single_session_shift,
    build_orientation_event,
    default_shift_name,
)

# -------------------------
# Config
# -------------------------

SEED = int(os.getenv("QUARTER_SEED", "43"))
WEEKS = 10
QUARTER_SEASON = models.Quarter.FALL
QUARTER_YEAR = 2026
QUARTER_START = date(2026, 9, 28)  # Monday, week 1 — clear of Spring's Jun 12 end

DEMO_SCHOOLS = ["Dos Pueblos HS", "La Colina Junior High", "Santa Barbara HS"]

# Rotation reordered to lead with Spring's top performer (crispr-mutations),
# still an even rotation across the same 5 high-school modules — Spring
# didn't show a strong enough signal to actually drop any of them.
FALL_HIGH_SCHOOL_ROTATION = [
    "crispr-mutations-knockout-strategies",
    "glucose-sensing",
    "bioinformatics-gene-expression-cancer",
    "crispr-gene-editing-basics",
    "thermodynamics-heat-transfer-calorimetry",
]

# Roster churn, derived from the live Spring participation query (see
# module docstring). Names, not IDs, because these Volunteer rows already
# exist from seed_quarter_demo.py.
DEPARTED_REGULARS = {"Jenny Gibson", "John Hu", "Sareena Gavaskar", "Sophia Howard"}
PROMOTED_TO_LEAD = {"Malerie Gonzales", "Chloe Chang"}
NEW_RECRUITS = [
    ("Owen", "Castillo"), ("Priya", "Anand"), ("Marcus", "Webb"),
    ("Lian", "Zhao"), ("Aiyana", "Redcloud"), ("Ben", "Sorensen"),
]


def build_fall_volunteer_pools(db) -> tuple[list[models.Volunteer], list[models.Volunteer]]:
    """Start from the Spring roster, apply churn, add recruits.

    Departed volunteers' rows are left untouched (they may still hold
    historical signups/credit) — they're just excluded from Fall's
    booking pools.
    """
    by_full_name = {}
    for first, last in LEAD_VOLUNTEERS + REGULAR_VOLUNTEERS:
        email = _email_for(first, last)
        vol = db.query(models.Volunteer).filter(models.Volunteer.email == email).first()
        if vol:
            by_full_name[f"{first} {last}"] = vol

    leads = [by_full_name[f"{f} {l}"] for f, l in LEAD_VOLUNTEERS if f"{f} {l}" in by_full_name]
    leads += [by_full_name[name] for name in PROMOTED_TO_LEAD if name in by_full_name]

    regulars = [
        by_full_name[f"{f} {l}"]
        for f, l in REGULAR_VOLUNTEERS
        if f"{f} {l}" in by_full_name
        and f"{f} {l}" not in PROMOTED_TO_LEAD
        and f"{f} {l}" not in DEPARTED_REGULARS
    ]

    idx = 1000  # keep phone numbers distinct from Spring's
    for first, last in NEW_RECRUITS:
        idx += 1
        email = _email_for(first, last)
        vol = db.query(models.Volunteer).filter(models.Volunteer.email == email).first()
        if not vol:
            vol = models.Volunteer(
                email=email, first_name=first, last_name=last,
                phone_e164=_phone_for(idx),
            )
            db.add(vol)
        regulars.append(vol)

    db.flush()
    return leads, regulars


def get_or_create_fall_quarter(db) -> models.AcademicQuarter:
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
    end_date = last_week_start + timedelta(days=4)
    quarter = models.AcademicQuarter(
        season=QUARTER_SEASON, year=QUARTER_YEAR, label="",
        start_date=QUARTER_START, end_date=end_date,
    )
    db.add(quarter)
    db.flush()
    print(f"Created quarter: {quarter.display_name} ({quarter.start_date} - {quarter.end_date}, "
          f"{quarter.weeks_in_quarter} weeks)")
    return quarter


def reset_fall_demo_data(db, quarter: models.AcademicQuarter) -> None:
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
    print(f"RESET_DEMO=1: deleting {len(events)} previously-seeded Fall events...")
    for ev in events:
        db.delete(ev)
    db.flush()


def build_dos_pueblos_week_fall(db, rng, organizer, quarter, module, leads, regulars,
                                 week_number: int, week_start: date, resolve: bool) -> models.Event:
    """Same Mon-Fri x P1/P2 shape as Spring, but denser booking (growth) and
    capacity raised 6 -> 7 to reflect a program that's outgrowing last
    quarter's shift sizes."""
    monday = week_start
    friday = week_start + timedelta(days=4)
    event = models.Event(
        owner_id=organizer.id,
        title=f"{module.name} \u2014 Dos Pueblos HS (Mike Lynch) \u2014 Week {week_number}",
        description=(
            "Weekly outreach at Dos Pueblos HS with teacher Mike Lynch. "
            "Continuing partnership from Spring 2026."
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
    all_shifts = []
    for day_offset in range(5):
        day = monday + timedelta(days=day_offset)
        p1 = build_single_session_shift(
            db, event, sort_order,
            default_shift_name(_dt(day, 8, 0), _dt(day, 10, 30)),
            _dt(day, 8, 0), _dt(day, 10, 30),
            "Dos Pueblos HS \u2014 Rm 214", capacity=7,
        )
        sort_order += 1
        p2 = build_single_session_shift(
            db, event, sort_order,
            default_shift_name(_dt(day, 9, 40), _dt(day, 12, 20)),
            _dt(day, 9, 40), _dt(day, 12, 20),
            "Dos Pueblos HS \u2014 Rm 214", capacity=7,
        )
        sort_order += 1

        for shift in (p1, p2):
            # Denser than Spring's [1,1,2,2,3] / [0,1,1,2,2,3] — this is
            # the growth lever. Occasionally exceeds capacity 7 -> waitlist.
            n_leads = rng.choice([1, 2, 2, 2, 3, 3])
            n_regulars = rng.choice([1, 2, 2, 3, 3, 4, 5])
            book_shift(db, rng, shift, leads, regulars, n_leads, n_regulars)
            all_shifts.append(shift)

    db.flush()

    if resolve:
        for shift in all_shifts:
            sessions = list(shift.sessions)
            for ss in shift.shift_signups:
                _resolve_shift_signup_fall(db, rng, ss, sessions)
        event.completed_at = _dt(friday, 13, 0)

    return event


def _resolve_shift_signup_fall(db, rng: random.Random, shift_signup, sessions) -> None:
    """Same shape as seed_quarter_demo._resolve_shift_signup, but with
    Fall's slightly improved attendance split (90/6/4 vs Spring's 87/8/5)."""
    if shift_signup.status != models.SignupStatus.confirmed:
        return
    roll = rng.random()
    for session in sessions:
        if roll < 0.90:
            outcome = models.SignupStatus.attended
            checked_in_at = session.start_time + timedelta(minutes=rng.randint(-5, 8))
        elif roll < 0.96:
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


def build_secondary_event_fall(db, rng, organizer, quarter, module, school, teacher,
                                leads, regulars, week_number, week_start, resolve, capacity=6):
    """Same Tue/Thu shape as seed_quarter_demo.build_secondary_event, but with
    capacity raised to 6 (was 5 in Spring) decided BEFORE booking (so it
    actually affects who gets waitlisted) and Fall's attendance resolver."""
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
            f"{school} \u2014 Science Lab", capacity=capacity,
        )
        n_leads = rng.choice([0, 1, 1, 2])
        n_regulars = rng.choice([1, 2, 2, 3, 3])
        book_shift(db, rng, shift, leads, regulars, n_leads, n_regulars)
        shifts.append(shift)

    db.flush()

    if resolve:
        for shift in shifts:
            sessions = list(shift.sessions)
            for ss in shift.shift_signups:
                _resolve_shift_signup_fall(db, rng, ss, sessions)
        event.completed_at = _dt(thursday, 14, 30)

    return event


# -------------------------
# Main
# -------------------------


def main():
    rng = random.Random(SEED)
    db = SessionLocal()
    try:
        spring = (
            db.query(models.AcademicQuarter)
            .filter(models.AcademicQuarter.season == models.Quarter.SPRING,
                    models.AcademicQuarter.year == 2026)
            .first()
        )
        if not spring:
            raise SystemExit(
                "Spring 2026 not found. Run `python -m app.seed_quarter_demo` first — "
                "this script extrapolates from it."
            )

        quarter = get_or_create_fall_quarter(db)
        db.commit()

        if os.getenv("RESET_DEMO") == "1":
            reset_fall_demo_data(db, quarter)
            db.commit()

        organizer = get_or_create_organizer(db)
        modules = get_modules(db)
        leads, regulars = build_fall_volunteer_pools(db)
        db.commit()
        print(f"Fall roster: {len(leads)} leads, {len(regulars)} regulars "
              f"({len(DEPARTED_REGULARS)} departed, {len(PROMOTED_TO_LEAD)} promoted, "
              f"{len(NEW_RECRUITS)} new recruits)")

        # Only the brand-new recruits need orientation — returning
        # volunteers keep permanent credit from Spring.
        new_recruit_vols = [v for v in regulars if (v.first_name, v.last_name) in NEW_RECRUITS]
        build_orientation_event(
            db, rng, organizer, quarter, [], new_recruit_vols, resolve=True,
        )
        db.commit()

        rotation = [FALL_HIGH_SCHOOL_ROTATION[i % len(FALL_HIGH_SCHOOL_ROTATION)]
                    for i in range(WEEKS)]

        # La Colina: biweekly -> weekly (sustained demand).
        # Santa Barbara HS: new partner, onboards week 4 onward.
        secondary_schedule = {}
        for week in range(1, WEEKS + 1):
            entries = []
            mid_slug = MIDDLE_SCHOOL_MODULE_SLUGS[(week - 1) % len(MIDDLE_SCHOOL_MODULE_SLUGS)]
            entries.append(("La Colina Junior High", "Priya Anand", mid_slug))
            if week >= 4:
                hs_slug = FALL_HIGH_SCHOOL_ROTATION[(week - 4) % len(FALL_HIGH_SCHOOL_ROTATION)]
                entries.append(("Santa Barbara HS", "Owen Castillo", hs_slug))
            secondary_schedule[week] = entries

        events_created = 1  # orientation
        for week_number in range(1, WEEKS + 1):
            week_start = QUARTER_START + timedelta(weeks=week_number - 1)
            resolve = week_number < WEEKS

            module = modules[rotation[week_number - 1]]
            build_dos_pueblos_week_fall(
                db, rng, organizer, quarter, module, leads, regulars,
                week_number, week_start, resolve,
            )
            events_created += 1

            for school, teacher, mod_slug in secondary_schedule[week_number]:
                build_secondary_event_fall(
                    db, rng, organizer, quarter, modules[mod_slug], school, teacher,
                    leads, regulars, week_number, week_start, resolve,
                )
                events_created += 1

            db.commit()
            print(f"Week {week_number}/{WEEKS} seeded"
                  + (" (left pending resolution)" if not resolve else ""))

        print(f"\nDone. Seeded {events_created} events across {quarter.display_name} "
              f"({quarter.weeks_in_quarter} weeks), {len(leads) + len(regulars)} active volunteers.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()