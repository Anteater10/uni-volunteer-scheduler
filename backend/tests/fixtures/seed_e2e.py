#!/usr/bin/env python3
"""
Idempotent E2E seed script for v1.1 (account-less volunteer model).

Called from Playwright globalSetup. Makes HTTP calls against a running
backend (no direct DB / no SQLAlchemy dependency_overrides) and prints a
JSON blob on stdout with the created IDs for the Playwright specs to consume.

Usage:
    BACKEND_URL=http://localhost:8000 EXPOSE_TOKENS_FOR_TESTING=1 \\
        python backend/tests/fixtures/seed_e2e.py

Credentials are dev-only and hard-coded (T-00-27 accepted).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone, date

import urllib.request
import urllib.error
import urllib.parse


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BACKEND_URL}/api/v1"

ADMIN = {"name": "E2E Admin", "email": "admin@e2e.test", "password": "Admin!2345"}
ORGANIZER = {"name": "E2E Organizer", "email": "organizer@e2e.test", "password": "Organizer!2345"}

ATTENDED_VOL = {
    "first_name": "Attended",
    "last_name": "Volunteer",
    "email": "attended-vol@e2e.test",
    "phone": "8055550100",
}
SEEDED_VOL = {
    "first_name": "Seeded",
    "last_name": "Pending",
    "email": "seeded-pending@e2e.test",
    "phone": "8055550101",
}

EVENT_TITLE = "E2E Seed Event"


# -------------------------
# tiny HTTP helpers (stdlib only so this script has no extra deps)
# -------------------------

def _req(method: str, path: str, *, token: str | None = None,
         json_body: dict | None = None, form_body: dict | None = None) -> tuple[int, dict | list | str]:
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


def _login(email: str, password: str) -> str:
    status, body = _req("POST", "/auth/token", form_body={"username": email, "password": password})
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"login failed for {email}: {status} {body}")
    return body["access_token"]


def _admin_upsert_user(admin_token: str, email: str, password: str, name: str, role: str) -> None:
    """Create user if not already present (idempotent)."""
    s, users = _req("GET", "/users/", token=admin_token)
    if s == 200 and isinstance(users, list):
        for u in users:
            if u.get("email") == email:
                return
    s, body = _req("POST", "/users/", token=admin_token, json_body={
        "name": name, "email": email, "password": password,
        "role": role, "notify_email": True,
    })
    if s in (200, 201):
        return
    if s == 400 and isinstance(body, dict) and "exists" in str(body).lower():
        return
    raise RuntimeError(f"admin create {email} ({role}) failed: {s} {body}")


def _get_current_week() -> dict:
    """Return {quarter, year, week_number} from the backend."""
    s, body = _req("GET", "/public/current-week")
    if s != 200 or not isinstance(body, dict):
        raise RuntimeError(f"current-week failed: {s} {body}")
    return body


def _get_or_create_event(admin_token: str, quarter: str, year: int, week_number: int) -> dict:
    """Find existing seed event or create a new one. Returns event dict."""
    s, events = _req(
        "GET",
        f"/public/events?quarter={quarter}&year={year}&week_number={week_number}",
    )
    if s == 200 and isinstance(events, list):
        for ev in events:
            if ev.get("title") == EVENT_TITLE:
                print(f"[seed] reusing existing event {ev['id']}", file=sys.stderr)
                return ev

    # Create new event in the current quarter/week
    today = date.today()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    orientation_start = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, tzinfo=timezone.utc
    )
    orientation_end = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 10, 0, tzinfo=timezone.utc
    )
    period_start = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 10, 30, tzinfo=timezone.utc
    )
    period_end = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 12, 0, tzinfo=timezone.utc
    )
    event_start = orientation_start
    event_end = datetime(
        day_after.year, day_after.month, day_after.day, 18, 0, tzinfo=timezone.utc
    )

    payload = {
        "title": EVENT_TITLE,
        "description": "E2E seed event — safe to delete",
        "location": "E2E Hall",
        "visibility": "public",
        "start_date": event_start.isoformat(),
        "end_date": event_end.isoformat(),
        "quarter": quarter,
        "year": year,
        "week_number": week_number,
        "module_slug": "e2e-test",
        "school": "E2E High School",
        "slots": [
            {
                "slot_type": "orientation",
                "start_time": orientation_start.isoformat(),
                "end_time": orientation_end.isoformat(),
                "capacity": 20,
                "location": "E2E Hall Room A",
            },
            {
                "slot_type": "period",
                "start_time": period_start.isoformat(),
                "end_time": period_end.isoformat(),
                "capacity": 20,
                "location": "E2E Hall Room B",
            },
        ],
    }
    s, body = _req("POST", "/events/", token=admin_token, json_body=payload)
    if s not in (200, 201):
        raise RuntimeError(f"event create failed: {s} {body}")
    print(f"[seed] created new event {body['id']}", file=sys.stderr)
    return body


def _get_slots(admin_token: str, event_id: str) -> tuple[str, str]:
    """Return (orientation_slot_id, period_slot_id) for the event."""
    s, slots = _req("GET", f"/slots/?event_id={event_id}", token=admin_token)
    if s != 200 or not isinstance(slots, list):
        raise RuntimeError(f"slot list failed: {s} {slots}")

    orientation_id = None
    period_id = None
    for slot in slots:
        st = slot.get("slot_type")
        if st == "orientation" and orientation_id is None:
            orientation_id = slot["id"]
        elif st == "period" and period_id is None:
            period_id = slot["id"]

    if not orientation_id:
        raise RuntimeError(f"No orientation slot found for event {event_id}. slots: {slots}")
    if not period_id:
        raise RuntimeError(f"No period slot found for event {event_id}. slots: {slots}")

    return orientation_id, period_id


def _signup_volunteer(vol: dict, slot_ids: list) -> tuple[int, dict | str]:
    """Call POST /public/signups and return (status_code, body)."""
    return _req("POST", "/public/signups", json_body={
        "first_name": vol["first_name"],
        "last_name": vol["last_name"],
        "email": vol["email"],
        "phone": vol["phone"],
        "slot_ids": slot_ids,
    })


def _ensure_attended_volunteer(
    admin_token: str,
    organizer_token: str,
    orientation_slot_id: str,
) -> None:
    """Create attended-vol@e2e.test with an attended orientation signup.

    Idempotent: If 409 (already signed up), tries to check-in existing signup.
    """
    s, body = _signup_volunteer(ATTENDED_VOL, [orientation_slot_id])
    if s in (200, 201):
        signup_id = body["signup_ids"][0]
        # Check in the signup to create attended status
        cs, cb = _req("POST", f"/signups/{signup_id}/check-in", token=organizer_token)
        if cs not in (200, 201):
            print(f"[seed] warn: check-in for attended vol returned {cs} {cb}", file=sys.stderr)
        else:
            print(f"[seed] attended volunteer checked in: signup {signup_id}", file=sys.stderr)
    elif s == 409:
        print(f"[seed] attended volunteer already signed up — checking for existing signup",
              file=sys.stderr)
        # Find existing signup and check it in
        sv, sv_body = _req("GET", f"/slots/{orientation_slot_id}", token=admin_token)
        # Try to find signups for this slot
        ss, signups = _req("GET", f"/signups/?slot_id={orientation_slot_id}", token=admin_token)
        if ss == 200 and isinstance(signups, list):
            for su in signups:
                if su.get("status") in ("attended", "checked_in"):
                    print(f"[seed] attended volunteer already has attended status", file=sys.stderr)
                    return
                # Check in the first non-cancelled signup
                if su.get("status") not in ("cancelled",):
                    cs, _ = _req("POST", f"/signups/{su['id']}/check-in", token=organizer_token)
                    if cs in (200, 201):
                        print(f"[seed] checked in existing signup {su['id']}", file=sys.stderr)
                        return
    else:
        print(f"[seed] warn: attended volunteer signup returned {s} {body}", file=sys.stderr)


def _create_seeded_pending(period_slot_id: str) -> str | None:
    """Create seeded-pending@e2e.test with a period slot signup and return the confirm token.

    Returns None if EXPOSE_TOKENS_FOR_TESTING is not set or signup fails.
    Idempotent: if 409 (already signed up), returns None (token unavailable).
    """
    s, body = _signup_volunteer(SEEDED_VOL, [period_slot_id])
    if s in (200, 201):
        token = body.get("confirm_token")
        if token:
            print(f"[seed] seeded pending volunteer created, token obtained", file=sys.stderr)
        else:
            print(
                "[seed] warn: confirm_token absent — EXPOSE_TOKENS_FOR_TESTING must be set on backend",
                file=sys.stderr,
            )
        return token
    elif s == 409:
        print(
            f"[seed] seeded pending volunteer already signed up — confirm_token unavailable this run",
            file=sys.stderr,
        )
        return None
    else:
        print(f"[seed] warn: seeded pending signup returned {s} {body}", file=sys.stderr)
        return None


def main() -> int:
    # 1. Log in as admin (must already exist from seed_admin.py / migrate step)
    admin_email = os.environ.get("SEED_ADMIN_EMAIL", ADMIN["email"])
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD", ADMIN["password"])
    try:
        admin_token = _login(admin_email, admin_password)
    except Exception as e:
        print(f"fatal: cannot log in as admin {admin_email}: {e}", file=sys.stderr)
        print(
            "Ensure the backend seed_admin step ran with SEED_ADMIN_EMAIL=admin@e2e.test "
            "SEED_ADMIN_PASSWORD=Admin!2345, or export those vars before running seed_e2e.py",
            file=sys.stderr,
        )
        return 2

    # 2. Ensure organizer user exists (idempotent)
    _admin_upsert_user(
        admin_token, ORGANIZER["email"], ORGANIZER["password"], ORGANIZER["name"], "organizer"
    )
    organizer_token = _login(ORGANIZER["email"], ORGANIZER["password"])

    # 3. Get current week (so event is in the browseable range)
    week = _get_current_week()
    quarter = week["quarter"]
    year = week["year"]
    week_number = week["week_number"]
    print(f"[seed] current week: {quarter} {year} week {week_number}", file=sys.stderr)

    # 4. Get or create seed event
    event = _get_or_create_event(admin_token, quarter, year, week_number)
    event_id = event["id"]
    event_title = event.get("title", EVENT_TITLE)

    # 5. Identify orientation and period slots
    orientation_slot_id, period_slot_id = _get_slots(admin_token, event_id)
    print(
        f"[seed] slots: orientation={orientation_slot_id} period={period_slot_id}",
        file=sys.stderr,
    )

    # 6. Ensure "attended orientation" volunteer (idempotent)
    _ensure_attended_volunteer(admin_token, organizer_token, orientation_slot_id)

    # 7. Create "seeded pending" volunteer with a fresh confirm_token
    confirm_token = _create_seeded_pending(period_slot_id)

    out = {
        "event_id": event_id,
        "event_title": event_title,
        "orientation_slot_id": orientation_slot_id,
        "period_slot_id": period_slot_id,
        "quarter": quarter,
        "year": year,
        "week_number": week_number,
        "confirm_token": confirm_token,
        "seeded_volunteer_email": SEEDED_VOL["email"],
        "attended_volunteer_email": ATTENDED_VOL["email"],
        "organizer_email": ORGANIZER["email"],
        "admin_email": admin_email,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
