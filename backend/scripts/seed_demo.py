#!/usr/bin/env python3
"""Polished DEMO seed for the SciTrek volunteer scheduler.

Creates realistic, recruiter-demo-ready data by driving the REAL HTTP API
(no SQLAlchemy, no app-code changes). Because every signup goes through
``POST /public/signups`` and confirmations go through the magic-link
confirm endpoint, all capacity / waitlist / FIFO logic is exercised exactly
as production would.

Run from the HOST (rate limiting is bypassed because the backend container
has EXPOSE_TOKENS_FOR_TESTING=1, which also exposes confirm tokens):

    BACKEND_URL=http://localhost:8000 python backend/scripts/seed_demo.py

Demo beats this seed guarantees:
  * Multiple SciTrek events across summer 2026 weeks 2-5 (browse-by-week +
    duplicate-to-future-weeks look real).
  * Realistic volunteer names on confirmed signups (rosters look alive).
  * ONE event with a single high-demand session AT FULL CAPACITY plus a
    populated waitlist -> cancel a confirmed signup on camera and watch the
    next waitlisted volunteer auto-promote.
  * ONE event with TWO populated period sessions (each with spare room) ->
    admin slot-swap demo.

Idempotent-ish: events are keyed by title (skipped if present); signups
tolerate the UNIQUE(volunteer_id, slot_id) 409. Intended for a fresh DB.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BACKEND_URL}/api/v1"

ADMIN = {"name": "SciTrek Admin", "email": "admin@e2e.example.com", "password": "Admin!2345"}
ORGANIZER = {"name": "SciTrek Organizer", "email": "organizer@e2e.example.com", "password": "Organizer!2345"}

# Summer 2026 quarter anchor (Monday of week 1) — matches backend QUARTER_START_DATES.
SUMMER_2026_WEEK1_MONDAY = date(2026, 6, 22)
QUARTER = "summer"
YEAR = 2026


def week_monday(week_number: int) -> date:
    return SUMMER_2026_WEEK1_MONDAY + timedelta(weeks=week_number - 1)


# Realistic, diverse UCSB-student-style volunteer roster.
VOLUNTEERS = [
    ("Sofia", "Ramirez"), ("Ethan", "Nguyen"), ("Aisha", "Patel"),
    ("Marcus", "Johnson"), ("Emily", "Chen"), ("Diego", "Hernandez"),
    ("Hannah", "Kim"), ("Liam", "O'Brien"), ("Priya", "Sharma"),
    ("Noah", "Garcia"), ("Olivia", "Martinez"), ("Jacob", "Lee"),
    ("Mia", "Lopez"), ("Tyler", "Brooks"), ("Zoe", "Williams"),
    ("Andre", "Davis"), ("Grace", "Park"), ("Daniel", "Torres"),
    ("Maya", "Singh"), ("Brandon", "Wright"), ("Isabella", "Cruz"),
    ("Kevin", "Tran"), ("Natalie", "Reyes"), ("Caleb", "Adams"),
    ("Jasmine", "Flores"), ("Ryan", "Mitchell"), ("Leah", "Cohen"),
    ("Omar", "Hassan"), ("Chloe", "Bennett"), ("Vincent", "Castillo"),
    ("Amara", "Okafor"), ("Sean", "Murphy"), ("Yuki", "Tanaka"),
    ("Gabriela", "Santos"), ("Trevor", "Coleman"), ("Nadia", "Ali"),
]


def vol_dict(idx: int) -> dict:
    first, last = VOLUNTEERS[idx % len(VOLUNTEERS)]
    slug_last = last.lower().replace("'", "")
    return {
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}.{slug_last}{idx}@volunteer.demo",
        "phone": f"805555{1000 + idx:04d}",
    }


# -------------------------
# stdlib HTTP helpers
# -------------------------

def _req(method, path, *, token=None, json_body=None, form_body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    headers = {}
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    elif form_body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form_body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def log(msg):
    print(f"[demo] {msg}", file=sys.stderr)


def _login(email, password):
    s, b = _req("POST", "/auth/token", form_body={"username": email, "password": password})
    if s != 200 or not isinstance(b, dict):
        raise RuntimeError(f"login failed for {email}: {s} {b}")
    return b["access_token"]


def _admin_upsert_user(admin_token, email, password, name, role):
    s, users = _req("GET", "/users/", token=admin_token)
    if s == 200 and isinstance(users, list):
        for u in users:
            if u.get("email") == email:
                return
    s, b = _req("POST", "/users/", token=admin_token, json_body={
        "name": name, "email": email, "password": password,
        "role": role, "notify_email": True,
    })
    if s in (200, 201):
        return
    if s == 400 and "exist" in str(b).lower():
        return
    raise RuntimeError(f"create user {email} failed: {s} {b}")


def _ensure_module(token, slug, name, capacity=24):
    """Restore a soft-deleted template or create it; idempotent."""
    rs, _ = _req("POST", f"/admin/module-templates/{urllib.parse.quote(slug)}/restore", token=token)
    if rs in (200, 201):
        log(f"restored module template '{slug}'")
        return
    cs, cb = _req("POST", "/admin/module-templates", token=token,
                  json_body={"slug": slug, "name": name, "default_capacity": capacity})
    if cs in (200, 201, 409):
        return
    raise RuntimeError(f"module template '{slug}' restore={rs} create={cs} {cb}")


def _dt(d: date, hh: int, mm: int) -> str:
    return datetime.combine(d, time(hh, mm), tzinfo=timezone.utc).isoformat()


def _find_event(token, title) -> dict | None:
    s, events = _req("GET", "/events/", token=token)
    if s == 200 and isinstance(events, list):
        for e in events:
            if e.get("title") == title:
                return e
    return None


def _create_event(token, *, title, description, location, school, module_slug,
                  week_number, day_offset, slots) -> dict:
    """slots: list of dicts {slot_type, hh_start, mm_start, hh_end, mm_end, capacity, location}."""
    existing = _find_event(token, title)
    if existing:
        log(f"event already exists: {title}")
        return existing
    d = week_monday(week_number) + timedelta(days=day_offset)
    slot_payload = []
    starts, ends = [], []
    for sl in slots:
        st = _dt(d, sl["hh_start"], sl["mm_start"])
        en = _dt(d, sl["hh_end"], sl["mm_end"])
        starts.append(st)
        ends.append(en)
        slot_payload.append({
            "slot_type": sl["slot_type"],
            "start_time": st,
            "end_time": en,
            "capacity": sl["capacity"],
            "location": sl["location"],
        })
    payload = {
        "title": title,
        "description": description,
        "location": location,
        "visibility": "public",
        "start_date": min(starts),
        "end_date": max(ends),
        "quarter": QUARTER,
        "year": YEAR,
        "week_number": week_number,
        "module_slug": module_slug,
        "school": school,
        "slots": slot_payload,
    }
    s, b = _req("POST", "/events/", token=token, json_body=payload)
    if s not in (200, 201):
        raise RuntimeError(f"event create '{title}' failed: {s} {b}")
    log(f"created event: {title} (week {week_number})")
    return b


def _get_slots(token, event_id) -> list:
    s, slots = _req("GET", f"/slots/?event_id={event_id}", token=token)
    if s != 200 or not isinstance(slots, list):
        raise RuntimeError(f"slot list failed for {event_id}: {s} {slots}")
    return slots


def _signup(vol, slot_id) -> tuple[int, dict | str]:
    return _req("POST", "/public/signups", json_body={
        "first_name": vol["first_name"],
        "last_name": vol["last_name"],
        "email": vol["email"],
        "phone": vol["phone"],
        "slot_ids": [slot_id],
    })


def _confirm(token_raw):
    if not token_raw:
        return
    _req("POST", f"/public/signups/confirm?token={urllib.parse.quote(token_raw)}")


def _fill_slot(slot_id, vol_indices, *, confirm=True) -> dict:
    """Sign up each volunteer to slot_id. Returns {confirmed, waitlisted}."""
    out = {"confirmed": 0, "waitlisted": 0, "other": 0}
    for i in vol_indices:
        s, b = _signup(vol_dict(i), slot_id)
        if s not in (200, 201) or not isinstance(b, dict):
            if s == 409:
                out["other"] += 1
                continue
            log(f"warn: signup vol#{i} -> slot {slot_id}: {s} {b}")
            out["other"] += 1
            continue
        status = (b.get("signups") or [{}])[0].get("status")
        if status == "waitlisted":
            out["waitlisted"] += 1
        else:
            out["confirmed"] += 1
            if confirm:
                _confirm(b.get("confirm_token"))
    return out


def main() -> int:
    log(f"backend = {BACKEND_URL}")
    try:
        admin_token = _login(ADMIN["email"], ADMIN["password"])
    except Exception as e:
        log(f"FATAL: cannot log in as admin: {e}")
        return 2

    _admin_upsert_user(admin_token, ORGANIZER["email"], ORGANIZER["password"],
                       ORGANIZER["name"], "organizer")
    log("organizer user ensured")
    # Events are created AS THE ORGANIZER so the organizer demo path works:
    # ensure_event_owner_or_admin gates "Add a question" / event detail on
    # ownership, and admins retain full access regardless of owner.
    organizer_token = _login(ORGANIZER["email"], ORGANIZER["password"])

    # SciTrek modules
    _ensure_module(admin_token, "intro-chem", "Intro to Chemistry")
    _ensure_module(admin_token, "intro-bio", "Intro to Biology")
    _ensure_module(admin_token, "intro-physics", "Intro to Physics")
    _ensure_module(admin_token, "intro-astro", "Intro to Astronomy")
    _ensure_module(admin_token, "orientation", "Orientation")

    summary = {"events": [], "marquee_full_event": None, "swap_event": None}
    vi = 0  # rolling volunteer index

    def take(n):
        nonlocal vi
        idxs = list(range(vi, vi + n))
        vi += n
        return idxs

    # ----- standard browse events (orientation + period) across weeks -----
    standard = [
        dict(title="SciTrek Module 3 — Chemistry @ Lincoln Elementary",
             school="Lincoln Elementary", module_slug="intro-chem",
             location="Lincoln Elementary, Santa Barbara", week=2, day=2,
             orient=5, period=7),
        dict(title="SciTrek Module 4 — Astronomy @ McKinley Elementary",
             school="McKinley Elementary", module_slug="intro-astro",
             location="McKinley Elementary, Santa Barbara", week=2, day=3,
             orient=4, period=5),
        dict(title="SciTrek Module 3 — Chemistry @ Goleta Family School",
             school="Goleta Family School", module_slug="intro-chem",
             location="Goleta Family School, Goleta", week=3, day=1,
             orient=4, period=6),
        dict(title="SciTrek Module 1 — Biology @ Lincoln Elementary",
             school="Lincoln Elementary", module_slug="intro-bio",
             location="Lincoln Elementary, Santa Barbara", week=4, day=2,
             orient=3, period=4),
        dict(title="SciTrek Module 2 — Physics @ Isla Vista Elementary",
             school="Isla Vista Elementary", module_slug="intro-physics",
             location="Isla Vista Elementary, Goleta", week=5, day=3,
             orient=2, period=3),
    ]
    for ev in standard:
        event = _create_event(
            organizer_token,
            title=ev["title"],
            description=f"SciTrek classroom science module at {ev['school']}. "
                        "Volunteers run a hands-on inquiry lesson with K-6 students.",
            location=ev["location"], school=ev["school"], module_slug=ev["module_slug"],
            week_number=ev["week"], day_offset=ev["day"],
            slots=[
                dict(slot_type="orientation", hh_start=15, mm_start=30, hh_end=16, mm_end=30,
                     capacity=12, location="Volunteer Orientation Room"),
                dict(slot_type="period", hh_start=16, mm_start=45, hh_end=18, mm_end=45,
                     capacity=12, location="Classroom Session"),
            ],
        )
        slots = _get_slots(admin_token, event["id"])
        orient = next(s for s in slots if s["slot_type"] == "orientation")
        period = next(s for s in slots if s["slot_type"] == "period")
        _fill_slot(orient["id"], take(ev["orient"]))
        _fill_slot(period["id"], take(ev["period"]))
        summary["events"].append({"title": ev["title"], "week": ev["week"], "id": event["id"]})

    # ----- MARQUEE: full session + populated waitlist (cancel -> auto-promote) -----
    full_event = _create_event(
        organizer_token,
        title="SciTrek Module 1 — Biology @ Isla Vista Elementary",
        description="High-demand SciTrek Biology session. Classroom capacity is "
                    "capped; extra volunteers join the waitlist and are auto-promoted "
                    "when a confirmed volunteer cancels.",
        location="Isla Vista Elementary, Goleta", school="Isla Vista Elementary",
        module_slug="intro-bio", week_number=2, day_offset=4,
        slots=[
            dict(slot_type="period", hh_start=16, mm_start=45, hh_end=18, mm_end=45,
                 capacity=6, location="Classroom 4 (capacity 6)"),
        ],
    )
    full_slots = _get_slots(admin_token, full_event["id"])
    full_slot = full_slots[0]
    # 6 confirmed (fills capacity) then 3 more -> auto-waitlisted
    res = _fill_slot(full_slot["id"], take(6))        # confirmed
    res_wl = _fill_slot(full_slot["id"], take(3))     # waitlisted
    summary["marquee_full_event"] = {
        "title": full_event["title"], "id": full_event["id"], "slot_id": full_slot["id"],
        "capacity": full_slot["capacity"],
        "confirmed": res["confirmed"], "waitlisted": res_wl["waitlisted"],
    }

    # ----- SWAP: two populated period sessions with spare room -----
    swap_event = _create_event(
        organizer_token,
        title="SciTrek Module 2 — Physics @ Adelante Charter",
        description="Two parallel SciTrek Physics sessions. Admins can swap a "
                    "volunteer between the morning and afternoon classroom slots.",
        location="Adelante Charter, Santa Barbara", school="Adelante Charter",
        module_slug="intro-physics", week_number=3, day_offset=3,
        slots=[
            dict(slot_type="period", hh_start=16, mm_start=0, hh_end=18, mm_end=0,
                 capacity=8, location="Morning Session (Rm 2)"),
            dict(slot_type="period", hh_start=19, mm_start=0, hh_end=21, mm_end=0,
                 capacity=8, location="Afternoon Session (Rm 5)"),
        ],
    )
    swap_slots = _get_slots(admin_token, swap_event["id"])
    swap_slots_sorted = sorted(swap_slots, key=lambda s: s["start_time"])
    morning, afternoon = swap_slots_sorted[0], swap_slots_sorted[1]
    _fill_slot(morning["id"], take(4))
    _fill_slot(afternoon["id"], take(3))
    summary["swap_event"] = {
        "title": swap_event["title"], "id": swap_event["id"],
        "morning_slot_id": morning["id"], "afternoon_slot_id": afternoon["id"],
    }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
