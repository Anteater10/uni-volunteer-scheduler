"""Server-side .ics builder for the signup confirmation attachment.

Mirrors frontend/src/lib/calendar.js — same PRODID, same UID scheme
(scitrek-{event_id}-slot-{slot_id}@scitrek.ucsb.edu), same METHOD:PUBLISH.
Calendars dedupe on UID, so a volunteer who imports the emailed file AND
uses the in-app download ends up with each session exactly once.
"""
from datetime import datetime, timezone

from . import models
from .config import settings

PRODID = "-//SciTrek//Volunteer Scheduler//EN"
UID_DOMAIN = "scitrek.ucsb.edu"


def _utc_stamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    """RFC 5545 §3.3.11 text escaping: backslash, newline, comma, semicolon."""
    return (
        text
        # Normalize first: a description can arrive with CRLF or bare CR
        # (browser textarea, pasted content), and a raw CR left inside a
        # property value corrupts the file's line structure. Mirrors
        # frontend/src/lib/calendar.js's escapeText().
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    """RFC 5545 §3.1: content lines fold at 75 octets with a leading space."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out, chunk = [], ""
    for ch in line:
        if len((chunk + ch).encode("utf-8")) > 74:
            out.append(chunk)
            chunk = " " + ch
        else:
            chunk += ch
    out.append(chunk)
    return "\r\n".join(out)


def _slot_kind(slot: "models.Slot") -> str:
    kind = getattr(slot.slot_type, "value", slot.slot_type) or ""
    return str(kind).title()


def build_signup_ics(event: "models.Event", slots: list) -> str:
    """One VEVENT per slot, CRLF-terminated VCALENDAR document."""
    if not slots:
        raise ValueError("Calendar export: at least one slot is required")

    dtstamp = _utc_stamp(datetime.now(timezone.utc))
    event_url = f"{settings.frontend_base_url}/volunteer/events/{event.id}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        # Required by Outlook to treat the file as a publishable calendar
        # rather than a meeting request it should RSVP to.
        "METHOD:PUBLISH",
    ]
    for slot in slots:
        kind = _slot_kind(slot)
        summary = f"SciTrek: {event.title} ({kind})" if kind else f"SciTrek: {event.title}"
        location = slot.location or event.location or event.school or ""
        description = (
            f"{event.description}\n\n{event_url}" if event.description else event_url
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:scitrek-{event.id}-slot-{slot.id}@{UID_DOMAIN}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{_utc_stamp(slot.start_time)}",
                f"DTEND:{_utc_stamp(slot.end_time)}",
                f"SUMMARY:{_escape(summary)}",
                f"LOCATION:{_escape(location)}",
                f"DESCRIPTION:{_escape(description)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
