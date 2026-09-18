"""
Canonical event-title format (SCRUM-154).

Every event is named `Week {N} - {Module Name} - {School}`. This is the one
place the rule is written down on the backend; the copilot's event tools and
any API-side validation import from here so the two enforcement points cannot
drift apart. The frontend mirror lives in `frontend/src/lib/eventTitle.js` —
change both together.

Titles created before this rule are left as-is; nothing is backfilled.
"""

import re

#: `Week 7 - Conservation of Mass - GVJH` — single space, hyphen, single space.
EVENT_TITLE_PATTERN = re.compile(r"^Week \d+ - .+ - .+$")

EVENT_TITLE_FORMAT_HINT = (
    'Event titles must match "Week {N} - {Module Name} - {School}" '
    '(for example: "Week 7 - Conservation of Mass - GVJH").'
)


def is_valid_event_title(title: str | None) -> bool:
    """True if `title` matches the canonical format, ignoring outer whitespace."""
    if not title:
        return False
    return bool(EVENT_TITLE_PATTERN.match(title.strip()))


#: Lenient *extraction* counterpart to EVENT_TITLE_PATTERN above.
#:
#: EVENT_TITLE_PATTERN validates the whole canonical shape; this one only digs
#: the week number out of the front of a title, and deliberately tolerates the
#: spacing variants that exist in real data ("Week 5- Germs- LaCumbre"). It is
#: capped at two digits with a trailing boundary so "Week 123" parses as
#: nothing rather than silently as week 12.
WEEK_IN_TITLE_PATTERN = re.compile(r"^\s*week\s*(\d{1,2})\b", re.IGNORECASE)


def week_from_title(title: str | None) -> int | None:
    """The week number a title claims, or None if it doesn't state one.

    This is the source of truth for which "Week N" group an event belongs to.
    It is deliberately *not* the event's calendar position: an orientation for
    the Week 8 module is often scheduled to run during week 2, and volunteers
    need it filed under the module's week, not the date's.
    """
    if not title:
        return None
    match = WEEK_IN_TITLE_PATTERN.match(title)
    return int(match.group(1)) if match else None
