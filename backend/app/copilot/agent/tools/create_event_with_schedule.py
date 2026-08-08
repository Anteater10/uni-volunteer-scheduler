"""create_event_with_schedule write tool (admin-only).

Creates one Event together with its orientation slots and its shifts, in a
single confirmed action.

Why this exists alongside ``create_module_from_template``: that tool creates
a skeleton Event pinned to a week's Monday and nothing else — no orientation,
no shifts, nothing anyone can actually sign up for. Asking the copilot for
"two orientations, then five shift days the week after" had no tool that
could express it, so the agent either refused or produced an empty event and
called it done. Real scheduling questions are about *days*, and a tool that
cannot say "Tuesday" cannot answer them.

Shape of the arguments:

- Days are given as a ``date`` — 2026-08-17. ISO week plus weekday still
  works and was the original shape, on the theory that a model is better at
  "the Monday of 2026-W34" than at the date it lands on. That theory did not
  survive contact: asked for the week of August 17th, a real model produced
  2026-W33, a valid week exactly seven days early, which no later check
  could distinguish from the truth. Copying a date is not arithmetic, so
  ``date`` is what the schema now asks for. A weekday given beside a date is
  checked against it, and disagreement is refused rather than resolved.
- Times are ``HH:MM`` **Pacific** — the venue's wall clock, which is what an
  admin types and what every screen in this app displays. They are converted
  to UTC for storage. The first version of this tool stamped them as UTC
  directly, so an event asked for at 9am appeared on the public page at
  2am. Nothing caught it because the tests asserted on dates, and the
  offset is smaller than a day.
- The Event's own ``start_date`` / ``end_date`` are derived to span
  everything scheduled, because ``shift_service.validate_session_range``
  rejects a session outside them.
- Location is optional but strongly wanted: the public event page prints
  "—" for a slot without one, which reads as broken rather than as unset.
  A top-level ``location`` applies to everything; anything more specific
  overrides it.

Orientation slots are deliberately NOT shift members
(``ck_slots_shift_membership_matches_type``): they stay individually
bookable, which is exactly the distinction a demo of this tool should show.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools._when import PT as _PT
from app.copilot.agent.tools._when import (
    WEEKDAYS,
    BadArgs,
    at,
    hhmm,
    parse_when,
)
from app.copilot.agent.tools.base import Tool
from app.models import (
    Event,
    Module,
    Quarter,
    Shift,
    Slot,
    SlotType,
    User,
    UserRole,
)
from app.services import quarter_service, shift_service

_PII_SCHEMA = [
    "event_id",
    "title",
    "school",
    "location",
    "starts",
    "ends",
    "orientations",
    "shifts",
    "sessions",
    "schedule",
]

# Day/time arithmetic lives in _when so a second tool cannot re-derive it
# differently; see that module for why Pacific is not negotiable here.
_BadArgs = BadArgs
_at = at
_pt = hhmm
_parse_when = parse_when


def _label(entry: dict[str, Any], fallback: str) -> str:
    """"Wednesday 2026-09-09", or the fallback when it cannot be read."""
    if entry.get("date"):
        try:
            day = date.fromisoformat(str(entry["date"]).strip())
        except (TypeError, ValueError):
            return fallback
        return f"{day.strftime('%A')} {day.isoformat()}"
    week, weekday = entry.get("week"), entry.get("weekday")
    if not week or not weekday:
        return fallback
    return f"{str(weekday).strip().title()} of {week}"


def _precheck(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any] | None:
    """Ask rather than invent, before the confirmation card is built.

    The first version filled a missing start time with 09:00, a missing
    orientation length with 60 minutes, and a missing capacity with the
    template's. Only the last of those came from anywhere: 09:00 and 60 were
    made up, and an event silently an hour or four off is worse than one that
    was never created, because nobody looks at a thing they already approved.

    So every consequential value has to be stated. The question carries the
    module's own configured number as a suggested answer where one exists,
    which keeps this one round trip instead of an interrogation.
    """
    orientations_in = args.get("orientations") or []
    shifts_in = args.get("shifts") or []

    # The event's own details first. These used to fall through to the
    # handler, which meant an empty request reached the confirmation card
    # and the admin was asked to approve an event with no name.
    # Note what is NOT demanded here: a title. Falling back to the module's
    # own name is not an invention — it is the name the module already has,
    # and every screen shows it.
    outline: list[str] = []
    if not args.get("template_id"):
        outline.append(
            "which module it runs — the slug, from list_module_templates"
        )
    if not orientations_in and not shifts_in:
        outline.append(
            "when it actually happens — the orientation times and the shifts "
            "volunteers can book, with the days and times of each"
        )
    if outline:
        return ask_for(outline)

    template = (
        db.query(Module).filter(Module.slug == args.get("template_id")).one_or_none()
    )
    suggested_capacity = template.default_capacity if template else None
    suggested_minutes = template.duration_minutes if template else None

    missing: list[str] = []

    for index, entry in enumerate(orientations_in, start=1):
        where = _label(entry, f"orientation {index}")
        wants = []
        if not entry.get("start_time"):
            wants.append("what time it starts")
        if not entry.get("duration_minutes"):
            wants.append("how long it runs")
        if not entry.get("capacity"):
            wants.append(
                f"how many volunteers it holds (the module is set to "
                f"{suggested_capacity})"
                if suggested_capacity
                else "how many volunteers it holds"
            )
        if wants:
            missing.append(f"Orientation on {where}: {', and '.join(wants)}.")

    for shift_index, shift_in in enumerate(shifts_in, start=1):
        sessions_in = shift_in.get("sessions") or []
        shift_name = shift_in.get("name") or f"shift {shift_index}"
        if not shift_in.get("capacity"):
            missing.append(
                f"{shift_name}: how many volunteers it holds"
                + (
                    f" (the module is set to {suggested_capacity})."
                    if suggested_capacity
                    else "."
                )
            )
        for session_index, session_in in enumerate(sessions_in, start=1):
            where = _label(session_in, f"session {session_index}")
            wants = []
            if not session_in.get("start_time"):
                wants.append("what time it starts")
            if not session_in.get("end_time"):
                wants.append(
                    f"what time it ends (the module's sessions are "
                    f"{suggested_minutes} minutes)"
                    if suggested_minutes
                    else "what time it ends"
                )
            if wants:
                missing.append(f"{shift_name}, {where}: {', and '.join(wants)}.")

    if not missing:
        return None

    return {
        "needs_answers": missing,
        "question": (
            "I can't create this yet — some details weren't given and I'm not "
            "going to invent them, because an event at the wrong time looks "
            "correct until someone shows up. Ask the user for the following, "
            "then call this tool again with the answers. Do not guess, and do "
            "not use the suggested values without the user agreeing to them."
        ),
    }


def _handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    template_id = args["template_id"]
    orientations_in = args.get("orientations") or []
    shifts_in = args.get("shifts") or []

    if not orientations_in and not shifts_in:
        return {
            "error": (
                "nothing to schedule — give at least one orientation or one "
                "shift, otherwise use create_module_from_template"
            )
        }

    template = db.query(Module).filter(Module.slug == template_id).one_or_none()
    if template is None:
        return {"error": f"template not found: {template_id}"}

    default_minutes = template.duration_minutes
    # A blank string is not a location; it would print as "—" all the same.
    event_location = (args.get("location") or "").strip() or None

    # -- resolve every datetime up front, so a bad argument fails before
    #    anything is written rather than halfway through.
    try:
        orientations: list[dict[str, Any]] = []
        for index, entry in enumerate(orientations_in, start=1):
            day = _parse_when(entry, "orientation")
            start = _at(day, entry.get("start_time") or "17:00")
            minutes = int(entry.get("duration_minutes") or 60)
            if minutes <= 0:
                raise _BadArgs("orientation duration_minutes must be positive")
            orientations.append(
                {
                    "name": (entry.get("name") or f"Orientation {index}").strip(),
                    "start": start,
                    "end": start + timedelta(minutes=minutes),
                    "capacity": int(
                        entry.get("capacity") or template.default_capacity
                    ),
                    "location": (entry.get("location") or "").strip()
                    or event_location,
                }
            )

        shifts: list[dict[str, Any]] = []
        for shift_index, shift_in in enumerate(shifts_in, start=1):
            sessions_in = shift_in.get("sessions") or []
            if not sessions_in:
                raise _BadArgs(
                    f"shift {shift_index} has no sessions — a shift is the "
                    "all-or-nothing package of days a volunteer signs up for, "
                    "so it needs at least one"
                )
            shift_location = (shift_in.get("location") or "").strip() or event_location
            sessions: list[dict[str, Any]] = []
            for session_in in sessions_in:
                day = _parse_when(session_in, "session")
                start = _at(day, session_in.get("start_time") or "09:00")
                end_hhmm = session_in.get("end_time")
                end = (
                    _at(day, end_hhmm)
                    if end_hhmm
                    else start + timedelta(minutes=default_minutes)
                )
                if end <= start:
                    raise _BadArgs(
                        f"session on {day.isoformat()} ends at or before it "
                        "starts"
                    )
                sessions.append(
                    {
                        "name": (session_in.get("name") or "").strip() or None,
                        "start": start,
                        "end": end,
                        "location": (session_in.get("location") or "").strip()
                        or shift_location,
                    }
                )
            # An unnamed shift gets the same "Tue 9:00-10:30" label migration
            # 0037 gives a backfilled one, so a generated shift and a migrated
            # one read identically in the roster. "Shift 3" told nobody when
            # it was — which is the only thing a volunteer picking one needs.
            fallback = shift_service.default_shift_name(
                sessions[0]["start"], sessions[0]["end"]
            )
            shifts.append(
                {
                    "name": (shift_in.get("name") or fallback).strip(),
                    "capacity": int(
                        shift_in.get("capacity") or template.default_capacity
                    ),
                    "sessions": sessions,
                }
            )
    except _BadArgs as exc:
        return {"error": str(exc)}
    except (ValueError, TypeError) as exc:
        return {"error": f"could not read the schedule: {exc}"}

    every_start = [o["start"] for o in orientations] + [
        s["start"] for sh in shifts for s in sh["sessions"]
    ]
    every_end = [o["end"] for o in orientations] + [
        s["end"] for sh in shifts for s in sh["sessions"]
    ]
    # Every date below is the *Pacific* date, never the UTC one. A 5pm
    # orientation is 00:00 UTC the following day, so a UTC ``.date()`` would
    # file a Monday orientation under Tuesday — in the quarter lookup, in the
    # event's date range, and in the ``slots.date`` column three screens read.
    first_day = min(s.astimezone(_PT).date() for s in every_start)
    last_day = max(e.astimezone(_PT).date() for e in every_end)
    # The event spans whole local days, so the public page's "Wed Sep 2 – Fri
    # Sep 4" is the range a human would write, and every session sits inside
    # it for shift_service.validate_session_range.
    starts_at = _at(first_day, "00:00")
    ends_at = _at(last_day, "23:59")

    # Same rule as every other write path: the quarter cache derives from the
    # admin-entered quarter ranges, and an event outside them has nowhere to
    # live. Name the missing range — "no quarter covers this" is only useful
    # if you know which date failed.
    derived = quarter_service.derive_quarter_week(db, first_day)
    if derived is None:
        return {
            "error": (
                f"No quarter covers {first_day.isoformat()} — add it in "
                "Admin → Quarters first, then ask me again"
            )
        }
    season_value, year, week_number, quarter_id = derived
    # The last day has to be inside a quarter too, or the event straddles the
    # edge of the calendar the rest of the app reasons about.
    if quarter_service.derive_quarter_week(db, last_day) is None:
        return {
            "error": (
                f"The schedule runs to {last_day.isoformat()}, which no "
                "quarter covers — extend the quarter in Admin → Quarters, or "
                "schedule inside it"
            )
        }

    owner_id = scope.caller_id
    if owner_id is None:
        admin = db.query(User).filter(User.role == UserRole.admin).first()
        owner_id = admin.id if admin is not None else None
    if owner_id is None:
        return {"error": "no admin available to own the new event"}

    event = Event(
        owner_id=owner_id,
        title=(args.get("title") or template.name).strip(),
        school=((args.get("school") or "").strip() or None),
        location=event_location,
        module_slug=template.slug,
        start_date=starts_at,
        end_date=ends_at,
        quarter=Quarter(season_value),
        year=year,
        week_number=week_number,
        quarter_id=quarter_id,
    )
    db.add(event)
    db.flush()

    for sort_order, orientation in enumerate(orientations):
        db.add(
            Slot(
                event_id=event.id,
                shift_id=None,
                slot_type=SlotType.ORIENTATION,
                name=orientation["name"],
                start_time=orientation["start"],
                end_time=orientation["end"],
                date=orientation["start"].astimezone(_PT).date(),
                location=orientation["location"],
                capacity=orientation["capacity"],
                current_count=0,
                sort_order=sort_order,
            )
        )

    session_total = 0
    for sort_order, shift_spec in enumerate(shifts):
        shift = Shift(
            event_id=event.id,
            name=shift_spec["name"],
            capacity=shift_spec["capacity"],
            sort_order=sort_order,
        )
        db.add(shift)
        db.flush()
        for index, session in enumerate(shift_spec["sessions"]):
            db.add(
                Slot(
                    event_id=event.id,
                    shift_id=shift.id,
                    slot_type=SlotType.PERIOD,
                    name=session["name"],
                    start_time=session["start"],
                    end_time=session["end"],
                    date=session["start"].astimezone(_PT).date(),
                    location=session["location"],
                    # Inert for a session — the shift owns capacity — but the
                    # column is NOT NULL.
                    capacity=1,
                    current_count=0,
                    sort_order=index,
                )
            )
            session_total += 1

    # K27: a write tool owns its write. Committing here keeps it out of the
    # reach of audit_log.update_status, which rolls back if it cannot find
    # its own row — and used to throw away the thing the admin just approved.
    db.commit()
    db.refresh(event)

    # Report the schedule back day by day, in Pacific. Counts alone let the
    # model narrate times it never checked — and the first thing an admin
    # does after approving is read that summary instead of the event page.
    schedule = {
        "timezone": "America/Los_Angeles",
        "orientations": [
            {
                "name": o["name"],
                "date": o["start"].astimezone(_PT).date().isoformat(),
                "weekday": o["start"].astimezone(_PT).strftime("%A"),
                "time": f"{_pt(o['start'])}–{_pt(o['end'])}",
                "capacity": o["capacity"],
                "location": o["location"],
            }
            for o in orientations
        ],
        "shifts": [
            {
                "name": sh["name"],
                "capacity": sh["capacity"],
                "sessions": [
                    {
                        "date": s["start"].astimezone(_PT).date().isoformat(),
                        "weekday": s["start"].astimezone(_PT).strftime("%A"),
                        "time": f"{_pt(s['start'])}–{_pt(s['end'])}",
                        "location": s["location"],
                    }
                    for s in sh["sessions"]
                ],
            }
            for sh in shifts
        ],
    }

    payload = {
        "event_id": str(event.id),
        "title": event.title,
        "school": event.school,
        "location": event_location,
        "starts": first_day.isoformat(),
        "ends": last_day.isoformat(),
        "orientations": len(orientations),
        "shifts": len(shifts),
        "sessions": session_total,
        "schedule": schedule,
    }
    return schema_apply(payload, allowed_fields=_PII_SCHEMA)


# ``date`` first and ``week`` kept only as a fallback. Deriving "the week of
# August 17th" into 2026-W34 is arithmetic, and a live request came back as
# 2026-W33 — a real week, seven days early, indistinguishable from the right
# answer once it reaches the database. A weekday alongside a date is a free
# check: if they disagree, one of them was a guess.
_WHEN_PROPERTIES = {
    "date": {
        "type": "string",
        "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
        "description": (
            "The calendar day, e.g. 2026-08-17. PREFER THIS. Do not convert "
            "dates to ISO week numbers yourself."
        ),
    },
    "week": {
        "type": "string",
        "pattern": "^[0-9]{4}-W[0-9]{1,2}$",
        "description": "ISO week, e.g. 2026-W34. Only if no date is known.",
    },
    "weekday": {
        "type": "string",
        "enum": list(WEEKDAYS),
        "description": (
            "Day of that week. Required with 'week'; optional with 'date', "
            "where it is checked against the date."
        ),
    },
}


CREATE_EVENT_WITH_SCHEDULE_TOOL = Tool(
    name="create_event_with_schedule",
    description=(
        "Create an event from a module template together with its orientation "
        "sessions and its shifts, on specific days. Use this whenever the "
        "request names days, orientations, or shifts — create_module_from_template "
        "only makes an empty event pinned to a week.\n"
        "\n"
        "All times are HH:MM 24-hour PACIFIC (the venue clock); do not convert "
        "to UTC yourself.\n"
        "\n"
        "Give every day as a 'date' like 2026-08-17. Do NOT work out ISO week "
        "numbers — that arithmetic is where this goes wrong. Each day carries "
        "its own date, so a module with orientations one week and shifts the "
        "next is one call with different dates. Never make two events for one "
        "module.\n"
        "\n"
        "A shift is the all-or-nothing package a volunteer signs up for:\n"
        "- 'three shifts a day, Monday to Friday' = 15 shifts, each with ONE "
        "session (a volunteer takes one morning, not the whole week).\n"
        "- 'a shift covering Thursday and Friday' = ONE shift with TWO "
        "sessions (signing up commits them to both days).\n"
        "Orientations are separate slots, booked one at a time.\n"
        "\n"
        "Pass a location if the request implies one — a slot without it prints "
        "'—' on the public page.\n"
        "\n"
        "Every start time, end time, duration and capacity must come from the "
        "user. If any is missing this tool will not create anything; it "
        "returns the list of what to ask. Ask those questions and call it "
        "again with the answers — do not fill them in yourself.\n"
        "\n"
        "Admin only. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Module slug, e.g. glucose-sensing.",
            },
            "title": {
                "type": "string",
                "description": "Event title. Defaults to the template name.",
            },
            "school": {"type": "string", "description": "School name, if known."},
            "location": {
                "type": "string",
                "description": (
                    "Where people go, e.g. 'Chem 1204' or the school name. "
                    "Applies to every orientation and session unless one "
                    "overrides it."
                ),
            },
            "orientations": {
                "type": "array",
                "description": "Orientation sessions, booked individually.",
                "items": {
                    "type": "object",
                    "properties": {
                        **_WHEN_PROPERTIES,
                        "name": {
                            "type": "string",
                            "description": "Defaults to 'Orientation 1', 2, …",
                        },
                        "start_time": {
                            "type": "string",
                            "description": (
                                "HH:MM 24-hour Pacific. 9am is '09:00', 1pm is "
                                "'13:00'. Defaults to 17:00."
                            ),
                        },
                        "duration_minutes": {"type": "integer"},
                        "capacity": {"type": "integer"},
                        "location": {"type": "string"},
                    },
                    "required": [],
                },
            },
            "shifts": {
                "type": "array",
                "description": (
                    "Shifts. Each entry is ONE bookable package and its "
                    "sessions are every day that package commits a volunteer "
                    "to. Three separate morning/midday/afternoon shifts on one "
                    "day are three entries with one session each — not one "
                    "entry with three sessions."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "What a volunteer picks from, e.g. 'Mon 8-10am'. "
                                "Defaults to the first session's day and time."
                            ),
                        },
                        "capacity": {
                            "type": "integer",
                            "description": "Volunteers for the whole package.",
                        },
                        "location": {"type": "string"},
                        "sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    **_WHEN_PROPERTIES,
                                    "name": {"type": "string"},
                                    "start_time": {
                                        "type": "string",
                                        "description": (
                                            "HH:MM 24-hour Pacific. Defaults "
                                            "to 09:00."
                                        ),
                                    },
                                    "end_time": {
                                        "type": "string",
                                        "description": (
                                            "HH:MM Pacific. Defaults to the "
                                            "template's duration after "
                                            "start_time."
                                        ),
                                    },
                                    "location": {"type": "string"},
                                },
                                "required": [],
                            },
                        },
                    },
                    "required": ["sessions"],
                },
            },
        },
        "required": ["template_id"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
    precheck=_precheck,
)
