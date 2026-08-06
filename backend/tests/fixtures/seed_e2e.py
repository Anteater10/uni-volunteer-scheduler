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
SHIFT_NAME = "E2E Shift"


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


def _season_for(d: date) -> str:
    """Rough month→season mapping. Only used to build a stable (season, year)
    key for the idempotent e2e quarter row — test data, not real UCSB dates."""
    if d.month <= 3:
        return "winter"
    if d.month <= 6:
        return "spring"
    if d.month <= 9:
        return "summer"
    return "fall"


def _ensure_quarters(admin_token: str) -> None:
    """Ensure an admin-entered quarter covers today through day-after-tomorrow.

    Issue #24: quarter-dependent features (current-week, event create) are
    blocked until a covering quarter exists, so the seed must enter one first.
    Idempotent: reuses a covering row; widens the same-(season, year, label)
    row if it exists but no longer covers; creates otherwise.
    """
    today = date.today()
    need_start = today.isoformat()
    need_end = (today + timedelta(days=2)).isoformat()

    s, rows = _req("GET", "/admin/quarters", token=admin_token)
    if s != 200 or not isinstance(rows, list):
        raise RuntimeError(f"quarter list failed: {s} {rows}")

    for row in rows:
        if row["start_date"] <= need_start and row["end_date"] >= need_end:
            print(f"[seed] reusing quarter {row.get('display_name', row['id'])}", file=sys.stderr)
            return

    season = _season_for(today)
    desired = {
        "season": season,
        "year": today.year,
        "label": "",
        "start_date": (today - timedelta(days=21)).isoformat(),
        "end_date": (today + timedelta(days=42)).isoformat(),
    }
    s, body = _req("POST", "/admin/quarters", token=admin_token, json_body=desired)
    if s in (200, 201):
        print(f"[seed] created quarter {season} {today.year} ({desired['start_date']} → {desired['end_date']})", file=sys.stderr)
        return

    if s == 409:
        # Same-key row exists with stale dates (or the new range overlaps it):
        # widen that row so it covers the needed window.
        for row in rows:
            if row["season"] == season and row["year"] == today.year and row.get("label", "") == "":
                patch = {
                    "start_date": min(row["start_date"], desired["start_date"]),
                    "end_date": max(row["end_date"], desired["end_date"]),
                }
                ps, pb = _req("PATCH", f"/admin/quarters/{row['id']}", token=admin_token, json_body=patch)
                if ps == 200:
                    print(f"[seed] widened quarter {season} {today.year} to {patch['start_date']} → {patch['end_date']}", file=sys.stderr)
                    return
                raise RuntimeError(f"quarter widen failed: {ps} {pb}")

    raise RuntimeError(f"quarter create failed: {s} {body}")


def _get_current_week() -> dict:
    """Return {quarter, year, week_number} from the backend."""
    s, body = _req("GET", "/public/current-week")
    if s != 200 or not isinstance(body, dict):
        raise RuntimeError(f"current-week failed: {s} {body}")
    if not body.get("configured"):
        raise RuntimeError(
            "current-week is unconfigured — _ensure_quarters should have entered one"
        )
    return body


def _ensure_module(admin_token: str, slug: str, name: str) -> None:
    """Ensure a module template exists — required since event create now
    rejects unknown module_slug (per-module orientation design, 2026-04-17)."""
    s, _ = _req("GET", f"/admin/modules", token=admin_token)
    if s != 200:
        return
    cs, _ = _req(
        "POST",
        "/admin/modules",
        token=admin_token,
        json_body={"slug": slug, "name": name},
    )
    # 409 = already exists (fine), 201 = created (fine).
    if cs not in (200, 201, 409):
        raise RuntimeError(f"module template create failed: {cs}")


def _get_or_create_event(
    admin_token: str, organizer_token: str, quarter: str, year: int, week_number: int
) -> dict:
    """Find existing seed event or create a new one. Returns event dict.

    The event is created AS THE ORGANIZER: staff check-in/roster routes are
    owner-scoped, and the e2e specs drive them with the organizer account.
    Module-template setup stays admin (admin-only endpoints).
    """
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
        ],
        # 2026-08-05 shifts: classroom work is a shift now. A bare period slot
        # is not creatable (POST /events refuses one, and the membership
        # constraint would reject the row anyway) and would not be bookable if
        # it were — `slot_ids` takes orientation only.
        "shifts": [
            {
                "name": SHIFT_NAME,
                "capacity": 200,
                "sort_order": 0,
                "sessions": [
                    {
                        "start_time": period_start.isoformat(),
                        "end_time": period_end.isoformat(),
                        "location": "E2E Hall Room B",
                        "name": "Period 1",
                        "sort_order": 0,
                    }
                ],
            }
        ],
    }
    s, body = _req("POST", "/events/", token=organizer_token, json_body=payload)
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


def _get_units(admin_token: str, event_id: str) -> tuple[str, str, str]:
    """Return (orientation_slot_id, shift_id, session_slot_id) for the event.

    Two bookable kinds now: an orientation slot, booked on its own through
    `slot_ids`, and a shift, booked as a bundle through `shift_ids`. The
    session id is still handed out because check-in and the roster address a
    session directly — but nothing signs up for one.
    """
    s, slots = _req("GET", f"/slots/?event_id={event_id}", token=admin_token)
    if s != 200 or not isinstance(slots, list):
        raise RuntimeError(f"slot list failed: {s} {slots}")

    orientation_id = None
    for slot in slots:
        if slot.get("slot_type") == "orientation":
            orientation_id = slot["id"]
            break
    if not orientation_id:
        raise RuntimeError(f"No orientation slot found for event {event_id}. slots: {slots}")

    hs, shifts = _req("GET", f"/shifts/?event_id={event_id}", token=admin_token)
    if hs != 200 or not isinstance(shifts, list) or not shifts:
        raise RuntimeError(f"No shift found for event {event_id}: {hs} {shifts}")
    shift = shifts[0]
    sessions = sorted(shift.get("sessions") or [], key=lambda x: x.get("sort_order", 0))
    if not sessions:
        raise RuntimeError(f"Shift {shift['id']} has no sessions: {shift}")

    return orientation_id, shift["id"], sessions[0]["id"]


def _ensure_shift_capacity(admin_token: str, shift_id: str, min_capacity: int = 200) -> None:
    """Capacity lives on the shift, so this is where test exhaustion is kept
    at bay — the sessions' own capacity column is inert."""
    ps, pb = _req("PATCH", f"/shifts/{shift_id}", token=admin_token,
                  json_body={"capacity": min_capacity})
    if ps not in (200, 201):
        print(f"[seed] warn: shift capacity update returned {ps} {pb}", file=sys.stderr)
    else:
        print(f"[seed] shift {shift_id} capacity set to {min_capacity}", file=sys.stderr)


def _signup_volunteer(vol: dict, slot_ids: list, shift_ids: list | None = None) -> tuple[int, dict | str]:
    """Call POST /public/signups and return (status_code, body).

    Two id lists since 2026-08-05: orientation slots in `slot_ids`, shifts in
    `shift_ids`. Sending a session id in `slot_ids` is a 422.
    """
    return _req("POST", "/public/signups", json_body={
        "first_name": vol["first_name"],
        "last_name": vol["last_name"],
        "email": vol["email"],
        "phone": vol["phone"],
        "slot_ids": slot_ids,
        "shift_ids": shift_ids or [],
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


def _cancel_signup(signup_id: str, organizer_token: str, *, is_shift: bool = False) -> None:
    """Cancel a signup via the staff cancel endpoint.

    A roster row's `signup_id` holds a shift-commitment id when `is_shift` is
    set — same field name, different table — so the route has to match or the
    cancel 404s and the seed then trips the unique constraint on re-signup.
    """
    path = (
        f"/admin/shift-signups/{signup_id}/cancel"
        if is_shift
        else f"/signups/{signup_id}/cancel"
    )
    cs, cb = _req("POST", path, token=organizer_token)
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
    """Create attended-vol@e2e.example.com with a checked_in orientation signup
    AND an orientation credit row.

    Flow: public signup (pending) -> confirm via token -> organizer check-in (checked_in).
    Credit is never implicit (grant-on-slot-end design): a checked_in orientation
    signup earns nothing until the slot is ended, and the seed can't end the slot
    (Test A still signs up for it live) — so grant the credit row explicitly, the
    same way _create_seeded_pending does.

    Idempotent strategy:
    1. Grant orientation credit for the seed family (duplicate rows are harmless —
       the lookup takes the most recent unrevoked row).
    2. Check roster — if already checked_in/attended, done.
    3. If pending/confirmed, advance to checked_in.
    4. If cancelled (or no signup), clean up cancelled rows first, then create fresh.
    """
    gs, gb = _req(
        "POST",
        "/admin/orientation-credits",
        token=admin_token,
        json_body={
            "volunteer_email": ATTENDED_VOL["email"],
            "family_key": "e2e-test",
            "notes": "e2e seed grant (attended volunteer — orientation-modal Test B)",
        },
    )
    if gs not in (200, 201):
        print(f"[seed] warn: attended-vol credit grant returned {gs} {gb}", file=sys.stderr)

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
    admin_token: str,
    organizer_token: str,
    event_id: str,
    shift_id: str,
) -> str | None:
    """Create seeded-pending@e2e.example.com with a shift signup and return the confirm token.

    Returns the raw confirm_token if EXPOSE_TOKENS_FOR_TESTING is set, else None.
    Idempotent: cancels any existing active signup, cleans up cancelled rows, and
    recreates fresh so Playwright always gets a usable token.

    The signup is shift-only, so the server-enforced orientation requirement
    would 422 it — grant orientation credit for the seed family first.
    """
    gs, gb = _req(
        "POST",
        "/admin/orientation-credits",
        token=admin_token,
        json_body={
            "volunteer_email": SEEDED_VOL["email"],
            "family_key": "e2e-test",
            "notes": "e2e seed grant (shift-only pending signup)",
        },
    )
    if gs not in (200, 201):
        print(f"[seed] warn: orientation credit grant returned {gs} {gb}", file=sys.stderr)

    row = _find_signup_in_roster(organizer_token, event_id, "Seeded Pending")
    if row is not None:
        status = row.get("status")
        if status not in ("cancelled",):
            # Cancel the existing signup so we can recreate fresh
            _cancel_signup(
                row["signup_id"], organizer_token, is_shift=bool(row.get("is_shift"))
            )

    # Always clean up any cancelled rows before re-signing up.
    # UNIQUE(volunteer_id, shift_id) blocks re-signup even for cancelled rows.
    _cleanup_cancelled_signups(SEEDED_VOL["email"])

    s, body = _signup_volunteer(SEEDED_VOL, [], [shift_id])
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

    # 3. Ensure a quarter covers the seed window (issue #24 gating), then
    #    get the current week (so event is in the browseable range)
    _ensure_quarters(admin_token)
    week = _get_current_week()
    quarter = week["quarter"]
    year = week["year"]
    week_number = week["week_number"]
    print(f"[seed] current week: {quarter} {year} week {week_number}", file=sys.stderr)

    # 4. Get or create seed event
    event = _get_or_create_event(admin_token, organizer_token, quarter, year, week_number)
    event_id = event["id"]
    event_title = event.get("title", EVENT_TITLE)

    # 5. Identify the bookable units: an orientation slot and a shift.
    orientation_slot_id, shift_id, session_slot_id = _get_units(admin_token, event_id)
    print(
        f"[seed] units: orientation={orientation_slot_id} shift={shift_id} "
        f"session={session_slot_id}",
        file=sys.stderr,
    )
    _ensure_slot_capacity(admin_token, orientation_slot_id)
    _ensure_shift_capacity(admin_token, shift_id)

    # 5b. Reset extra test signups so slots never fill up from repeated Playwright runs.
    # Keeps only the two named seed volunteers; cancels everything else.
    _reset_event_signups(
        event_id,
        keep_emails=[ATTENDED_VOL["email"], SEEDED_VOL["email"]],
    )

    # 6. Ensure "attended orientation" volunteer (idempotent)
    _ensure_attended_volunteer(admin_token, organizer_token, event_id, orientation_slot_id)

    # 7. Create "seeded pending" volunteer with a fresh confirm_token
    confirm_token = _create_seeded_pending(
        admin_token, organizer_token, event_id, shift_id
    )

    out = {
        "event_id": event_id,
        "event_title": event_title,
        "orientation_slot_id": orientation_slot_id,
        # The bookable classroom unit, and the session the roster + check-in
        # address inside it. `period_slot_id` is gone: nothing books one.
        "shift_id": shift_id,
        "shift_name": SHIFT_NAME,
        "session_slot_id": session_slot_id,
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
