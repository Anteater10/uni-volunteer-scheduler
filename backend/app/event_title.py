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
