#!/usr/bin/env python3
"""
Idempotent E2E seed script.

Called from Playwright globalSetup. Makes HTTP calls against a running
backend (no direct DB / no SQLAlchemy dependency_overrides — per
00-RESEARCH.md Pitfall 6) and prints a JSON blob on stdout with the
created IDs for the Playwright specs to consume.

Usage:
    BACKEND_URL=http://localhost:8000 python backend/tests/fixtures/seed_e2e.py

Credentials are dev-only and hard-coded (T-00-27 accepted).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import urllib.request
import urllib.error
import urllib.parse


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BACKEND_URL}/api/v1"

ADMIN = {"name": "E2E Admin", "email": "admin@e2e.test", "password": "Admin!2345"}
ORGANIZER = {"name": "E2E Organizer", "email": "organizer@e2e.test", "password": "Organizer!2345"}
STUDENT = {"name": "E2E Student", "email": "student@e2e.test", "password": "Student!2345"}

PORTAL_NAME = "E2E Portal"
PORTAL_SLUG = "e2e-portal"
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


def _register_participant(email: str, password: str, name: str) -> None:
    status, body = _req("POST", "/auth/register", json_body={
        "name": name, "email": email, "password": password,
        "notify_email": True,
    })
    if status == 200:
        return
    # idempotency: already-registered is fine
    if status == 400 and isinstance(body, dict) and "already" in str(body).lower():
        return
    raise RuntimeError(f"register failed for {email}: {status} {body}")


def _admin_upsert_user(admin_token: str, email: str, password: str, name: str, role: str) -> None:
    # check list and skip if already present
    s, users = _req("GET", "/users/", token=admin_token)
    if s == 200 and isinstance(users, list):
        for u in users:
            if u.get("email") == email:
                return
    s, body = _req("POST", "/users/", token=admin_token, json_body={
        "name": name, "email": email, "password": password,
        "role": role, "notify_email": True,
    })
    if s == 200:
        return
    if s == 400 and isinstance(body, dict) and "exists" in str(body).lower():
        return
    raise RuntimeError(f"admin create {email} ({role}) failed: {s} {body}")


def _get_or_create_portal(admin_token: str) -> str:
    # check existing by slug
    s, body = _req("GET", f"/portals/{PORTAL_SLUG}")
    if s == 200 and isinstance(body, dict):
        return body.get("slug", PORTAL_SLUG)
    s, body = _req("POST", "/portals/", token=admin_token, json_body={
        "name": PORTAL_NAME,
        "description": "E2E seed portal",
        "visibility": "public",
    })
    if s != 200:
        raise RuntimeError(f"portal create failed: {s} {body}")
    return body.get("slug", PORTAL_SLUG)


def _get_or_create_event(organizer_token: str) -> tuple[str, list[str]]:
    # List events, find our seed by title
    s, events = _req("GET", "/events/", token=organizer_token)
    seed_event = None
    if s == 200 and isinstance(events, list):
        for ev in events:
            if ev.get("title") == EVENT_TITLE:
                seed_event = ev
                break

    now = datetime.now(timezone.utc)
    start = (now + timedelta(hours=25)).replace(microsecond=0)
    end = (now + timedelta(hours=30)).replace(microsecond=0)

    if seed_event is None:
        # Create event with 3 slots capacity 2 each
        slots = []
        for i in range(3):
            s_start = start + timedelta(minutes=30 * i)
            s_end = s_start + timedelta(minutes=25)
            slots.append({
                "start_time": s_start.isoformat(),
                "end_time": s_end.isoformat(),
                "capacity": 2,
            })
        payload = {
            "title": EVENT_TITLE,
            "description": "E2E seed event",
            "location": "E2E Hall",
            "visibility": "public",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "max_signups_per_user": 5,
            "slots": slots,
        }
        s, body = _req("POST", "/events/", token=organizer_token, json_body=payload)
        if s != 200:
            raise RuntimeError(f"event create failed: {s} {body}")
        seed_event = body

    event_id = seed_event["id"]
    # Fetch slots for the event
    s, slot_rows = _req("GET", f"/slots/?event_id={event_id}", token=organizer_token)
    if s != 200 or not isinstance(slot_rows, list):
        raise RuntimeError(f"slot list failed: {s} {slot_rows}")
    slot_ids = [row["id"] for row in slot_rows]

    # Ensure event is attached to portal (idempotent)
    s, body = _req("POST", f"/portals/{PORTAL_SLUG}/events/{event_id}", token=organizer_token)
    # 200/201 ok; 400/409 "already attached" ok; 404 means portals route differs — try alt
    if s not in (200, 201, 204, 400, 409):
        # non-fatal — attach path may differ; log but continue
        print(f"warn: portal attach returned {s} {body}", file=sys.stderr)

    return event_id, slot_ids


def main() -> int:
    # 1. Register participant via public endpoint (idempotent)
    _register_participant(STUDENT["email"], STUDENT["password"], STUDENT["name"])

    # 2. Admin must exist already (seed_admin baked into docker-compose migrate step).
    #    Prefer that admin; if the CI admin uses different creds, fall back to registering
    #    via a dev-only path. For the Hetzner dev stack we assume SEED_ADMIN_EMAIL matches.
    admin_email = os.environ.get("SEED_ADMIN_EMAIL", ADMIN["email"])
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD", ADMIN["password"])
    try:
        admin_token = _login(admin_email, admin_password)
    except Exception as e:
        print(f"fatal: cannot log in as admin {admin_email}: {e}", file=sys.stderr)
        print("Ensure the backend seed_admin step ran with SEED_ADMIN_EMAIL=admin@e2e.test "
              "SEED_ADMIN_PASSWORD=Admin!2345, or export those vars before running seed_e2e.py",
              file=sys.stderr)
        return 2

    # 3. Ensure organizer + student exist via admin (idempotent, sets correct role)
    _admin_upsert_user(admin_token, ORGANIZER["email"], ORGANIZER["password"], ORGANIZER["name"], "organizer")
    _admin_upsert_user(admin_token, STUDENT["email"], STUDENT["password"], STUDENT["name"], "participant")

    # 4. Portal
    portal_slug = _get_or_create_portal(admin_token)

    # 5. Event + slots (as organizer)
    organizer_token = _login(ORGANIZER["email"], ORGANIZER["password"])
    event_id, slot_ids = _get_or_create_event(organizer_token)

    out = {
        "event_id": event_id,
        "slot_ids": slot_ids,
        "portal_slug": portal_slug,
        "admin_email": admin_email,
        "organizer_email": ORGANIZER["email"],
        "student_email": STUDENT["email"],
        "event_title": EVENT_TITLE,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
