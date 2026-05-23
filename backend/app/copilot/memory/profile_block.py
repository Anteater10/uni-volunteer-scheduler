"""Phase 34-07: build the profile block injected into the session-start system prompt.

The block is rendered exactly once — at session creation — and the resulting
system prompt is hashed and stored on the ``CopilotSession`` row. Mid-session
profile rewrites therefore do not affect the running session (locked decision #7
in the design doc).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models


_HEADER = "## What you know about this user"
_FOOTER = "Use this context when it helps; ignore it when irrelevant."


def load_profile_block(db: Session, *, user_id) -> str:
    """Return the fenced profile block for ``user_id`` or ``""``.

    Empty/whitespace-only ``profile_text`` and missing rows both render as the
    empty string so callers can unconditionally append the result to a prompt.
    """
    row = (
        db.query(models.CopilotUserProfile)
        .filter(models.CopilotUserProfile.user_id == user_id)
        .first()
    )
    if row is None or not (row.profile_text or "").strip():
        return ""
    return f"{_HEADER}\n{row.profile_text}\n\n{_FOOTER}"
