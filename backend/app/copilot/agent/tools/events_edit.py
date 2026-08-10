"""Event editing tools: read a schedule, fix it, or remove it.

Why these exist: the copilot could create an event and could not fix one.
Every mistake it made — a wrong time, a missing room, a typo in the title —
was the admin's to repair by hand in the UI, which makes "let the AI
schedule it" a worse deal than doing it yourself. The first event this tool
set was written for was one the copilot itself had put at 2am.

Four tools, in the order a repair actually goes:

- ``get_event_schedule`` — what is there now, with the ids needed to change
  it and every time in Pacific. Nothing else here takes an id the model
  invented; they all come from this.
- ``update_event`` — the event's own fields: title, school, location,
  description, visibility.
- ``reschedule_slot`` — one orientation or one session: its day, its times,
  its room, its capacity.
- ``delete_event`` — the whole thing, and only when nobody has signed up.

The dangerous one is ``delete_event``. The database cascade will happily
take signups with it, so this tool refuses outright while any exist rather
than asking a question a tired admin will wave through at 5pm.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope, deny_if_not_owned
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for, suggesting
from app.copilot.agent.tools._when import (
    WEEKDAYS,
    BadArgs,
    at,
    hhmm,
    local_date,
    resolve_day,
)
from app.copilot.agent.tools.base import Tool
from app.models import (
    Event,
    Shift,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
)

_EVENT_SCHEMA = [
    "event_id",
    "title",
    "school",
    "location",
    "description",
    "visibility",
    "starts",
    "ends",
    "module_slug",
    "timezone",
    "orientations",
    "shifts",
    "signups",
    "changed",
    "deleted",
]

_SLOT_SCHEMA = [
    "slot_id",
    "kind",
    "name",
    "date",
    "weekday",
    "time",
    "location",
    "capacity",
    "filled",
    "shift_id",
    "shift_name",
    "changed",
]


def _as_uuid(value: Any) -> uuid.UUID | None:
    """A model-invented id is a wrong answer, not an exception.

    Checked here rather than caught after the query: Postgres aborts the
    whole transaction on a malformed uuid literal, so by the time the
    exception arrives, the audit-log write that records the failure cannot
    run either — one bad id takes the request down with it.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _get_event(db: Session, event_id: Any) -> Event | None:
    key = _as_uuid(event_id)
    if key is None:
        return None
    return db.query(Event).filter(Event.id == key).one_or_none()


def _get_slot(db: Session, slot_id: Any) -> Slot | None:
    key = _as_uuid(slot_id)
    if key is None:
        return None
    return db.query(Slot).filter(Slot.id == key).one_or_none()


def _slot_row(slot: Slot) -> dict[str, Any]:
    return {
        "slot_id": str(slot.id),
        "kind": "orientation"
        if slot.slot_type == SlotType.ORIENTATION
        else "session",
        "name": slot.name,
        "date": local_date(slot.start_time).isoformat(),
        "weekday": local_date(slot.start_time).strftime("%A"),
        "time": f"{hhmm(slot.start_time)}–{hhmm(slot.end_time)}",
        "location": slot.location,
        "capacity": slot.capacity,
        "filled": slot.current_count,
        "shift_id": str(slot.shift_id) if slot.shift_id else None,
    }


def _live_signups(db: Session, event_id: Any) -> int:
    """Everyone still committed to this event, of either kind.

    There are two, and counting only one is how a delete guard passes while
    a full shift roster goes over the cliff: an orientation booking is a
    ``Signup`` against the slot, a shift booking is a ``ShiftSignup``
    against the shift. Cancelled rows do not block anything.
    """
    orientations = (
        db.query(Signup)
        .join(Slot, Signup.slot_id == Slot.id)
        .filter(
            Slot.event_id == event_id,
            Signup.status != SignupStatus.cancelled,
        )
        .count()
    )
    shifts = (
        db.query(ShiftSignup)
        .join(Shift, ShiftSignup.shift_id == Shift.id)
        .filter(
            Shift.event_id == event_id,
            ShiftSignup.status != SignupStatus.cancelled,
        )
        .count()
    )
    return orientations + shifts


# ------------------------------------------------------------ read


def _schedule_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    event = _get_event(db, args.get("event_id"))
    if event is None:
        return {"error": f"no event with id {args.get('event_id')!r}"}

    denied = deny_if_not_owned(scope, event)
    if denied is not None:
        return denied

    slots = (
        db.query(Slot)
        .filter(Slot.event_id == event.id)
        .order_by(Slot.start_time, Slot.sort_order)
        .all()
    )
    shifts = {
        s.id: s for s in db.query(Shift).filter(Shift.event_id == event.id)
    }

    orientations = []
    by_shift: dict[Any, list[dict[str, Any]]] = {}
    for slot in slots:
        row = _slot_row(slot)
        if slot.shift_id is None:
            orientations.append(schema_apply(row, allowed_fields=_SLOT_SCHEMA))
        else:
            row["shift_name"] = (
                shifts[slot.shift_id].name if slot.shift_id in shifts else None
            )
            by_shift.setdefault(slot.shift_id, []).append(
                schema_apply(row, allowed_fields=_SLOT_SCHEMA)
            )

    payload = {
        "event_id": str(event.id),
        "title": event.title,
        "school": event.school,
        "location": event.location,
        "visibility": event.visibility,
        "module_slug": event.module_slug,
        "starts": local_date(event.start_date).isoformat(),
        "ends": local_date(event.end_date).isoformat(),
        # Said out loud so a reader never has to wonder which clock this is.
        "timezone": "America/Los_Angeles",
        "signups": _live_signups(db, event.id),
        "orientations": orientations,
        "shifts": [
            {
                "shift_id": str(shift_id),
                "name": shifts[shift_id].name if shift_id in shifts else None,
                "capacity": shifts[shift_id].capacity
                if shift_id in shifts
                else None,
                "sessions": sessions,
            }
            for shift_id, sessions in by_shift.items()
        ],
    }
    return schema_apply(payload, allowed_fields=_EVENT_SCHEMA)


GET_EVENT_SCHEDULE_TOOL = Tool(
    name="get_event_schedule",
    description=(
        "Show one event in full: its details, every orientation and every "
        "shift with its sessions, all times in Pacific, plus the slot_id and "
        "shift_id needed to change any of them. Call this before editing "
        "anything — never invent an id, and never tell the user what an "
        "event looks like without reading it here first. Read-only."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "From list_modules or find_module_by_name.",
            }
        },
        "required": ["event_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_EVENT_SCHEMA + _SLOT_SCHEMA,
    handler=_schedule_handler,
)


# ------------------------------------------------------------ update event


_EVENT_FIELDS = ("title", "school", "location", "description", "visibility")


def _update_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing = []
    if not args.get("event_id"):
        return ask_for(
            ["which event to change — find it first and confirm it is the "
             "one they mean"]
        )
    if not any(args.get(f) is not None for f in _EVENT_FIELDS):
        event = _get_event(db, args["event_id"])
        missing.append(
            suggesting(
                "what to change — the title, school, location, description "
                "or visibility",
                event.title if event else None,
            )
        )
    return ask_for(missing)


def _update_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    event = _get_event(db, args.get("event_id"))
    if event is None:
        return {"error": f"no event with id {args.get('event_id')!r}"}

    denied = deny_if_not_owned(scope, event)
    if denied is not None:
        return denied

    changed = []
    for field in _EVENT_FIELDS:
        if args.get(field) is None:
            continue
        value = str(args[field]).strip()
        # An empty string is how a field gets cleared; " " is not a location.
        setattr(event, field, value or None)
        changed.append(field)

    if not changed:
        return {"error": "nothing to change"}

    # Dates deliberately absent: moving an event re-derives its quarter and
    # can strand its own sessions outside the new range. That is
    # reschedule_slot's job, one slot at a time, where the effect is visible.
    db.add(event)
    db.commit()
    db.refresh(event)

    return schema_apply(
        {
            "event_id": str(event.id),
            "title": event.title,
            "school": event.school,
            "location": event.location,
            "description": event.description,
            "visibility": event.visibility,
            "changed": changed,
        },
        allowed_fields=_EVENT_SCHEMA,
    )


UPDATE_EVENT_TOOL = Tool(
    name="update_event",
    description=(
        "Change an event's title, school, location, description or "
        "visibility. Pass only the fields that change; anything omitted is "
        "left alone, and an empty string clears a field. This does NOT move "
        "dates or times — use reschedule_slot for those, one slot at a time. "
        "Get event_id from a search or get_event_schedule. Requires user "
        "confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "title": {"type": "string"},
            "school": {"type": "string"},
            "location": {
                "type": "string",
                "description": "The event's default meeting place.",
            },
            "description": {"type": "string"},
            "visibility": {
                "type": "string",
                "description": (
                    "'public' or 'private'. Making an event private hides it "
                    "from volunteers without deleting anything — this is the "
                    "closest thing to cancelling an event."
                ),
            },
        },
        "required": ["event_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_EVENT_SCHEMA,
    handler=_update_handler,
    precheck=_update_precheck,
)


# ------------------------------------------------------------ reschedule slot


_SLOT_FIELDS = ("weekday", "week", "date", "start_time", "end_time",
                "location", "capacity", "name")


def _reschedule_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("slot_id"):
        return ask_for(
            ["which orientation or session to move — call get_event_schedule "
             "and read the slot_id from it"]
        )
    if not any(args.get(f) is not None for f in _SLOT_FIELDS):
        slot = _get_slot(db, args["slot_id"])
        return ask_for(
            [
                suggesting(
                    "what to change about this slot — its day, start time, "
                    "end time, room, capacity or name",
                    f"{local_date(slot.start_time)} "
                    f"{hhmm(slot.start_time)}–{hhmm(slot.end_time)} Pacific"
                    if slot
                    else None,
                )
            ]
        )
    # Moving the start without saying where the end goes would silently keep
    # the old end and change the length of the session.
    if args.get("start_time") and not args.get("end_time"):
        slot = _get_slot(db, args["slot_id"])
        if slot is not None:
            return ask_for(
                [
                    f"what time this should end — it currently runs "
                    f"{hhmm(slot.start_time)}–{hhmm(slot.end_time)} Pacific, "
                    f"and moving only the start would change how long it is"
                ]
            )
    return None


def _reschedule_handler(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any]:
    slot = _get_slot(db, args.get("slot_id"))
    if slot is None:
        return {"error": f"no slot with id {args.get('slot_id')!r}"}

    event = db.query(Event).filter(Event.id == slot.event_id).one()

    denied = deny_if_not_owned(scope, event)
    if denied is not None:
        return denied

    changed: list[str] = []

    try:
        day = local_date(slot.start_time)
        if args.get("date"):
            from datetime import date as _date

            day = _date.fromisoformat(str(args["date"]))
            changed.append("date")
        elif args.get("weekday"):
            weekday = str(args["weekday"]).strip().lower()
            if weekday not in WEEKDAYS:
                return {"error": f"unknown weekday {args['weekday']!r}"}
            week = args.get("week")
            if not week:
                # No week given means "the same week, a different day", which
                # is the common repair: "move it to Thursday".
                iso = day.isocalendar()
                week = f"{iso.year}-W{iso.week:02d}"
            day = resolve_day(str(week), weekday)
            changed.append("date")

        # Both ends are rebuilt from the local day, so a date change and a
        # time change compose instead of fighting. Keeping the old wall-clock
        # rather than the old instant is deliberate: a slot moved across the
        # DST boundary should still start at 9am, not at 8am.
        if args.get("start_time"):
            start = at(day, args["start_time"])
            changed.append("start_time")
        else:
            start = at(day, hhmm(slot.start_time))

        if args.get("end_time"):
            end = at(day, args["end_time"])
            changed.append("end_time")
        else:
            # No end given means the slot keeps its length, wherever it moved.
            end = start + (slot.end_time - slot.start_time)
    except (BadArgs, ValueError, TypeError) as exc:
        return {"error": str(exc)}

    if end <= start:
        return {"error": "the slot would end at or before it starts"}

    # The event's own range is what shift_service.validate_session_range
    # checks on every later edit; a slot outside it is a row the UI cannot
    # save again.
    if start < event.start_date or end > event.end_date:
        return {
            "error": (
                f"that puts the slot on {local_date(start).isoformat()}, "
                f"outside the event's {local_date(event.start_date).isoformat()} "
                f"– {local_date(event.end_date).isoformat()} range. Move the "
                "event's dates first, or pick a day inside it."
            )
        }

    slot.start_time = start
    slot.end_time = end
    slot.date = local_date(start)

    if args.get("location") is not None:
        slot.location = str(args["location"]).strip() or None
        changed.append("location")
    if args.get("name") is not None:
        slot.name = str(args["name"]).strip() or None
        changed.append("name")
    if args.get("capacity") is not None:
        if slot.shift_id is not None:
            return {
                "error": (
                    "a session's capacity is inert — the shift it belongs to "
                    "owns how many volunteers it holds. Change the shift "
                    "instead."
                )
            }
        new_capacity = int(args["capacity"])
        if new_capacity < slot.current_count:
            return {
                "error": (
                    f"{slot.current_count} people are already signed up, so "
                    f"capacity cannot go down to {new_capacity}"
                )
            }
        slot.capacity = new_capacity
        changed.append("capacity")

    db.add(slot)
    db.commit()
    db.refresh(slot)

    row = _slot_row(slot)
    row["changed"] = changed
    return schema_apply(row, allowed_fields=_SLOT_SCHEMA)


RESCHEDULE_SLOT_TOOL = Tool(
    name="reschedule_slot",
    description=(
        "Move or edit one orientation or one session: its day, its start and "
        "end time, its room, its name, or (orientations only) its capacity. "
        "Times are HH:MM 24-hour Pacific. Get slot_id from "
        "get_event_schedule. Changing the day alone keeps the same time of "
        "day; changing the start alone is refused, because it would silently "
        "change how long the session runs. This is the tool for fixing a slot "
        "that was created at the wrong time. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "slot_id": {
                "type": "string",
                "description": "From get_event_schedule.",
            },
            "date": {
                "type": "string",
                "description": "YYYY-MM-DD. Use this or weekday, not both.",
            },
            "weekday": {"type": "string", "enum": list(WEEKDAYS)},
            "week": {
                "type": "string",
                "description": (
                    "ISO week for the weekday, e.g. 2026-W37. Omit to stay in "
                    "the week the slot is already in."
                ),
            },
            "start_time": {"type": "string", "description": "HH:MM Pacific."},
            "end_time": {"type": "string", "description": "HH:MM Pacific."},
            "location": {"type": "string"},
            "name": {"type": "string"},
            "capacity": {
                "type": "integer",
                "description": "Orientations only; a shift owns its own.",
            },
        },
        "required": ["slot_id"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_SLOT_SCHEMA,
    handler=_reschedule_handler,
    precheck=_reschedule_precheck,
)


# ------------------------------------------------------------ delete


def _delete_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("event_id"):
        return ask_for(
            ["which event to delete — read it back to the user by name and "
             "date before doing anything"]
        )
    return None


def _delete_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    event = _get_event(db, args.get("event_id"))
    if event is None:
        return {"error": f"no event with id {args.get('event_id')!r}"}

    denied = deny_if_not_owned(scope, event)
    if denied is not None:
        return denied

    signups = _live_signups(db, event.id)
    if signups:
        # Not a question. A question at the end of a long afternoon gets a
        # yes, and the cascade takes every signup with it — including the
        # volunteers' record that they ever attended.
        return {
            "error": (
                f"refusing to delete '{event.title}': {signups} people are "
                "signed up and deleting the event deletes their signups with "
                "it. Cancel it instead by setting visibility to private with "
                "update_event, or remove the signups first if that is really "
                "what is wanted."
            )
        }

    title = event.title
    db.delete(event)
    db.commit()
    return schema_apply(
        {"deleted": True, "title": title, "event_id": str(args["event_id"])},
        allowed_fields=_EVENT_SCHEMA,
    )


DELETE_EVENT_TOOL = Tool(
    name="delete_event",
    description=(
        "Permanently delete an event and everything under it — its "
        "orientations, its shifts and its sessions. Refused outright while "
        "anyone is signed up; to take an event down without losing that "
        "history, set its visibility to private with update_event instead. "
        "This is how a mistakenly created event gets removed. Requires user "
        "confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {"event_id": {"type": "string"}},
        "required": ["event_id"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_EVENT_SCHEMA,
    handler=_delete_handler,
    precheck=_delete_precheck,
)
