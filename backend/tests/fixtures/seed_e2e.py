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

ADMIN = {"name": "E2E Admin", "email": "admin@e2e.example.com", "password": "Admin!2345"}
ORGANIZER = {"name": "E2E Organizer", "email": "organizer@e2e.example.com", "password": "Organizer!2345"}

ATTENDED_VOL = {
    "first_name": "Attended",
    "last_name": "Volunteer",
    "email": "attended-vol@e2e.example.com",
    "phone": "8055550100",
}
SEEDED_VOL = {
    "first_name": "Seeded",
    "last_name": "Pending",
    "email": "seeded-pending@e2e.example.com",
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


def _ensure_module(admin_token: str, slug: str, name: str) -> None:
    """Ensure a module template exists — required since event create now
    rejects unknown module_slug (per-module orientation design, 2026-04-17)."""
    s, _ = _req("GET", f"/admin/module-templates", token=admin_token)
    if s != 200:
        return
    cs, _ = _req(
        "POST",
        "/admin/module-templates",
        token=admin_token,
        json_body={"slug": slug, "name": name},
    )
    # 409 = already exists (fine), 201 = created (fine).
    if cs not in (200, 201, 409):
        raise RuntimeError(f"module template create failed: {cs}")


def _get_or_create_event(admin_token: str, quarter: str, year: int, week_number: int) -> dict:
    """Find existing seed event or create a new one. Returns event dict."""
    _ensure_module(admin_token, "e2e-test", "E2E Test Module")
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
                "capacity": 200,
                "location": "E2E Hall Room A",
            },
            {
                "slot_type": "period",
                "start_time": period_start.isoformat(),
                "end_time": period_end.isoformat(),
                "capacity": 200,
                "location": "E2E Hall Room B",
            },
        ],
    }
    s, body = _req("POST", "/events/", token=admin_token, json_body=payload)
    if s not in (200, 201):
        raise RuntimeError(f"event create failed: {s} {body}")
    print(f"[seed] created new event {body['id']}", file=sys.stderr)
    return body


def _ensure_slot_capacity(admin_token: str, slot_id: str, min_capacity: int = 200) -> None:
    """Ensure a slot has at least min_capacity to prevent test exhaustion."""
    s, slot = _req("GET", f"/slots/{slot_id}", token=admin_token)
    if s != 200 or not isinstance(slot, dict):
        return
    if (slot.get("capacity") or 0) < min_capacity:
        ps, pb = _req("PATCH", f"/slots/{slot_id}", token=admin_token,
                      json_body={"capacity": min_capacity})
        if ps not in (200, 201):
            print(f"[seed] warn: slot capacity update returned {ps} {pb}", file=sys.stderr)
        else:
            print(f"[seed] slot {slot_id} capacity set to {min_capacity}", file=sys.stderr)


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


def _cleanup_cancelled_signups(*emails: str) -> None:
    """Delete cancelled signups for given emails via test helper endpoint.

    This works around the UNIQUE(volunteer_id, slot_id) constraint so the seed
    can recreate signups from scratch. Only available when EXPOSE_TOKENS_FOR_TESTING=1.
    """
    email_str = ",".join(emails)
    url = f"{BACKEND_URL}/api/v1/test/seed-cleanup?emails={urllib.parse.quote(email_str)}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[seed] cleaned up cancelled signups for {email_str}", file=sys.stderr)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[seed] warn: seed-cleanup returned {e.code} {body}", file=sys.stderr)


def _reset_event_signups(event_id: str, keep_emails: list[str]) -> None:
    """Cancel all non-essential signups for the event to free slot capacity.

    Prevents test slot exhaustion from repeated Playwright runs. Keeps only
    the named seed-volunteer signups (attended and seeded-pending).
    """
    keep_str = ",".join(keep_emails)
    url = (
        f"{BACKEND_URL}/api/v1/test/event-signups-cleanup"
        f"?event_id={event_id}&keep_emails={urllib.parse.quote(keep_str)}"
    )
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(
                f"[seed] cleared test signups for event {event_id} (kept: {keep_str})",
                file=sys.stderr,
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[seed] warn: event-signups-cleanup returned {e.code} {body}", file=sys.stderr)


def _find_signup_in_roster(
    token: str,
    event_id: str,
    student_name: str,
    slot_time_contains: str | None = None,
) -> dict | None:
    """Find a roster row by student_name (and optionally slot_time substring).

    Returns the first matching row dict, or None.
    """
    rs, roster = _req("GET", f"/events/{event_id}/roster", token=token)
    if rs != 200 or not isinstance(roster, dict):
        return None
    for row in roster.get("rows", []):
        if row.get("student_name") == student_name:
            if slot_time_contains is None or slot_time_contains in (row.get("slot_time") or ""):
                return row
    return None


def _cancel_signup(signup_id: str, organizer_token: str) -> None:
    """Cancel a signup via organizer cancel endpoint."""
    cs, cb = _req("POST", f"/signups/{signup_id}/cancel", token=organizer_token)
    if cs not in (200, 201, 204):
        print(f"[seed] warn: cancel signup {signup_id} returned {cs} {cb}", file=sys.stderr)
    else:
        print(f"[seed] cancelled signup {signup_id}", file=sys.stderr)


def _ensure_attended_volunteer(
    admin_token: str,
    organizer_token: str,
    event_id: str,
    orientation_slot_id: str,
) -> None:
    """Create attended-vol@e2e.example.com with a checked_in orientation signup.

    Flow: public signup (pending) -> confirm via token -> organizer check-in (checked_in).
    The orientation_service counts both 'attended' and 'checked_in' as having attended.

    Idempotent strategy:
    1. Check roster — if already checked_in/attended, done.
    2. If pending/confirmed, advance to checked_in.
    3. If cancelled (or no signup), clean up cancelled rows first, then create fresh.
    """
    row = _find_signup_in_roster(admin_token, event_id, "Attended Volunteer")
    if row is not None:
        status = row.get("status")
        signup_id = row["signup_id"]

        if status in ("checked_in", "attended"):
            print(
                f"[seed] attended volunteer already has status {status} — skipping",
                file=sys.stderr,
            )
            return

        if status == "confirmed":
            # Skip straight to check-in
            cs, cb = _req("POST", f"/signups/{signup_id}/check-in", token=organizer_token)
            if cs not in (200, 201):
                print(
                    f"[seed] warn: check-in for already-confirmed vol returned {cs} {cb}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[seed] attended volunteer (confirmed) checked in: signup {signup_id}",
                    file=sys.stderr,
                )
            return

        if status == "pending":
            # Need to confirm first via admin, then check-in.
            # No raw token available — use admin promote if waitlisted, else resend.
            # Simplest: resend confirmation email gives no raw token. Instead,
            # cancel this pending signup, clean up (delete cancelled row), and recreate.
            _cancel_signup(signup_id, organizer_token)
            status = "cancelled"
            # Fall through to cancelled handling below

        if status == "cancelled":
            # Delete the cancelled row so UNIQUE constraint allows re-signup
            _cleanup_cancelled_signups(ATTENDED_VOL["email"])

    # Always clean up any residual cancelled rows before re-signing up.
    # (No-op when there are none — UNIQUE(volunteer_id, slot_id) blocks re-signup.)
    if row is None:
        _cleanup_cancelled_signups(ATTENDED_VOL["email"])

    # No existing signup (or just cleaned up) — create fresh
    s, body = _signup_volunteer(ATTENDED_VOL, [orientation_slot_id])
    if s not in (200, 201):
        print(f"[seed] warn: attended volunteer signup returned {s} {body}", file=sys.stderr)
        return

    signup_id = body["signup_ids"][0]

    # Step 1: Confirm the signup (pending -> confirmed) so check-in can proceed
    raw_token = body.get("confirm_token")
    if raw_token:
        cs, cb = _req("POST", f"/public/signups/confirm?token={raw_token}")
        if cs not in (200, 201, 204):
            print(f"[seed] warn: confirm for attended vol returned {cs} {cb}", file=sys.stderr)
        else:
            print(f"[seed] attended volunteer signup confirmed", file=sys.stderr)
    else:
        print(
            "[seed] warn: no confirm_token — EXPOSE_TOKENS_FOR_TESTING must be set",
            file=sys.stderr,
        )

    # Step 2: Check in (confirmed -> checked_in)
    cs, cb = _req("POST", f"/signups/{signup_id}/check-in", token=organizer_token)
    if cs not in (200, 201):
        print(f"[seed] warn: check-in for attended vol returned {cs} {cb}", file=sys.stderr)
    else:
        print(f"[seed] attended volunteer checked in: signup {signup_id}", file=sys.stderr)


def _create_seeded_pending(
    organizer_token: str,
    event_id: str,
    period_slot_id: str,
) -> str | None:
    """Create seeded-pending@e2e.example.com with a period slot signup and return the confirm token.

    Returns the raw confirm_token if EXPOSE_TOKENS_FOR_TESTING is set, else None.
    Idempotent: cancels any existing active signup, cleans up cancelled rows, and
    recreates fresh so Playwright always gets a usable token.
    """
    row = _find_signup_in_roster(organizer_token, event_id, "Seeded Pending")
    if row is not None:
        status = row.get("status")
        if status not in ("cancelled",):
            # Cancel the existing signup so we can recreate fresh
            _cancel_signup(row["signup_id"], organizer_token)

    # Always clean up any cancelled rows before re-signing up.
    # The UNIQUE(volunteer_id, slot_id) constraint blocks re-signup even for cancelled rows.
    _cleanup_cancelled_signups(SEEDED_VOL["email"])

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
            "Ensure the backend seed_admin step ran with SEED_ADMIN_EMAIL=admin@e2e.example.com "
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
    _ensure_slot_capacity(admin_token, orientation_slot_id)
    _ensure_slot_capacity(admin_token, period_slot_id)

    # 5b. Reset extra test signups so slots never fill up from repeated Playwright runs.
    # Keeps only the two named seed volunteers; cancels everything else.
    _reset_event_signups(
        event_id,
        keep_emails=[ATTENDED_VOL["email"], SEEDED_VOL["email"]],
    )

    # 6. Ensure "attended orientation" volunteer (idempotent)
    _ensure_attended_volunteer(admin_token, organizer_token, event_id, orientation_slot_id)

    # 7. Create "seeded pending" volunteer with a fresh confirm_token
    confirm_token = _create_seeded_pending(organizer_token, event_id, period_slot_id)

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
