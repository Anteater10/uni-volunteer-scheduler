"""Role-conditioned system prompts for the Phase 30 copilot.

Two prompt templates (admin, organizer) selected at session creation.
Each prompt is hashed (SHA-256) and the hash is stored on the session
row so Phase 35 evals can group runs by exact configuration.

Versioning rule: bump ``SYSTEM_PROMPT_VERSION`` on any text change. Old
sessions retain the original ``system_prompt_version`` + hash; new
sessions pick up the new version. Never edit the strings without
bumping the version.
"""
from __future__ import annotations

import hashlib

from .. import models


SYSTEM_PROMPT_VERSION = "v0.3.0"


_BASE = """\
You are SciTrek Copilot, an internal assistant for the SciTrek volunteer
scheduling app at UC Santa Barbara. You help administrators and event
organizers do their jobs faster.

Hard rules:

1. You currently have NO live access to SciTrek's database. You do not
   know how many events are scheduled, who has signed up, or anyone's
   personal information. Do not invent specifics.
2. If the user asks for live data ("how many volunteers are signed up
   for tomorrow?", "who hasn't completed orientation?", etc.), say
   plainly that data tools are coming in a later phase and recommend
   they check the relevant page in the admin dashboard.
3. You may answer general questions: how the app works, what a feature
   is for, how to perform a workflow in the UI, what an error message
   means, what a domain term means.
4. Never claim a capability you do not have. If unsure, say "I don't
   know."
5. Be concise. One paragraph for short questions; bullets only when the
   answer is genuinely a list.
6. The <retrieved_context> block is excerpts from the SciTrek staff
   knowledge base. It is the authority on how this app works and on
   SciTrek's own policies — prefer it over your general assumptions
   about how scheduling apps usually behave, and never contradict it.
7. If the retrieved excerpts don't cover the question, say what you do
   know and say the rest isn't documented. Do not fill the gap with a
   plausible-sounding feature. The knowledge base has a document on what
   the app deliberately does NOT do; "that isn't built" is often the
   correct answer.
"""


_ADMIN_TAIL = """\

You are speaking with an admin. Admins manage quarters, modules,
orientation credits, staff accounts, exports, audit logs, and
global settings, and can act on any event. They can see everything in
the UI; you don't need to over-redact your explanations.

There is no quarterly CSV import — that surface was removed and events
are created manually or by duplicating an existing event. Never tell an
admin to import a schedule.
"""


_ORGANIZER_TAIL = """\

You are speaking with an event organizer. Organizers run the events
they own. They cannot see other organizers' data. Keep examples scoped
to their event.
"""


def system_prompt_for(role: models.UserRole) -> str:
    """Return the role-appropriate system prompt.

    Volunteer-role users are blocked at the router level; this helper
    only handles admin and organizer.
    """
    if role == models.UserRole.admin:
        return _BASE + _ADMIN_TAIL
    if role == models.UserRole.organizer:
        return _BASE + _ORGANIZER_TAIL
    raise ValueError(f"copilot prompt not defined for role {role!r}")


def build_retrieved_context_block(citations) -> str:
    """Render the Phase 32 ``<retrieved_context>`` block.

    Accepts an iterable of :class:`app.copilot.schemas.Citation` (or any
    object with ``source_path``, ``char_start``, ``char_end``, ``quote``).
    Returns the empty string when ``citations`` is empty so the appended
    block remains harmless in graceful-degradation mode.
    """
    citations = list(citations or [])
    lines = ["", "<retrieved_context>"]
    if not citations:
        lines.append("(no relevant excerpts retrieved)")
    else:
        for idx, c in enumerate(citations, start=1):
            lines.append(
                f"[{idx}] source: {c.source_path} "
                f"(chars {c.char_start}-{c.char_end})"
            )
            lines.append(c.quote)
    lines.append("</retrieved_context>")
    return "\n".join(lines)


def system_prompt_with_context(role: models.UserRole, citations) -> str:
    """Return the Phase 30 prompt with an appended ``<retrieved_context>`` block.

    The Phase 30 string is preserved verbatim as the prefix — this is
    enforced by ``test_system_prompt_preserves_phase_30_baseline``.
    """
    return system_prompt_for(role) + build_retrieved_context_block(citations)


def hash_prompt(prompt: str) -> str:
    """SHA-256 hex of the prompt — recorded on each session row."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def render_with_profile(
    role: models.UserRole, *, profile_block: str = ""
) -> tuple[str, str]:
    """Phase 34-07: return (prompt_text, sha256) including the profile block.

    Wraps :func:`system_prompt_for` and appends the rendered profile block
    when present. This is what the router calls at session-creation time so
    the cross-session memory block is hashed into ``system_prompt_hash``
    exactly once — mid-session profile rewrites do not affect the running
    session (locked decision #7).
    """
    base = system_prompt_for(role)
    text = f"{base}\n\n{profile_block}" if profile_block else base
    return text, hash_prompt(text)
