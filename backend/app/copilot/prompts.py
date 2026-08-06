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


SYSTEM_PROMPT_VERSION = "v0.4.0"


_PREAMBLE = """\
You are SciTrek Copilot, an internal assistant for the SciTrek volunteer
scheduling app at UC Santa Barbara. You help administrators and event
organizers do their jobs faster.

Hard rules:

"""


# Rules 1-2, no-tools variant. True only while ``copilot_agent_loop_enabled``
# is off. See ``_AGENT_ACCESS_RULES`` for the other half of the pair.
_NO_TOOLS_ACCESS_RULES = """\
1. You currently have NO live access to SciTrek's database. You do not
   know how many events are scheduled, who has signed up, or anyone's
   personal information. Do not invent specifics.
2. If the user asks for live data ("how many volunteers are signed up
   for tomorrow?", "who hasn't completed orientation?", etc.), say
   plainly that data tools are coming in a later phase and recommend
   they check the relevant page in the admin dashboard.
"""


# Rules 1-2, agent variant. Phase B: with the ReAct loop on, the two rules
# above are false — the model *does* have live access and data tools are not
# "coming in a later phase", they are in its hands. Serving the no-tools text
# to a tool-using model told it to refuse work it could actually do, and told
# the user to go look it up themselves.
_AGENT_ACCESS_RULES = """\
1. You have live access to SciTrek's scheduling data through tools. When a
   question has a factual answer in the data, call a tool and answer from
   the result. Never state a count, a name, a date or a fill rate that did
   not come back from a tool in this turn — if you did not look it up, say
   so instead of estimating.
2. Some tools change data or send email. Those stop and ask the user to
   confirm before anything happens. When one does, describe plainly what
   is about to change and who it will reach, then wait. Do not say an
   action succeeded until you have seen its result — a confirmation card
   is a question, not a receipt.
"""


_SHARED_RULES = """\
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


# Assembled here rather than written out twice so rules 3-7 cannot drift
# between the two variants. ``_BASE`` must stay byte-identical to the
# v0.3.0 text — ``test_system_prompt_preserves_phase_30_baseline`` compares
# it against a checked-in fixture.
_BASE = _PREAMBLE + _NO_TOOLS_ACCESS_RULES + _SHARED_RULES
_AGENT_BASE = _PREAMBLE + _AGENT_ACCESS_RULES + _SHARED_RULES


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


def system_prompt_for(role: models.UserRole, *, agent: bool = False) -> str:
    """Return the role-appropriate system prompt.

    Volunteer-role users are blocked at the router level; this helper
    only handles admin and organizer.

    ``agent=True`` selects the tool-using variant. Pass the value of
    ``settings.copilot_agent_loop_enabled`` — the two variants disagree
    about whether the model can reach live data, and serving the wrong
    one is not a cosmetic error.
    """
    base = _AGENT_BASE if agent else _BASE
    if role == models.UserRole.admin:
        return base + _ADMIN_TAIL
    if role == models.UserRole.organizer:
        return base + _ORGANIZER_TAIL
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
    role: models.UserRole, *, profile_block: str = "", agent: bool = False
) -> tuple[str, str]:
    """Phase 34-07: return (prompt_text, sha256) including the profile block.

    Wraps :func:`system_prompt_for` and appends the rendered profile block
    when present. This is what the router calls at session-creation time so
    the cross-session memory block is hashed into ``system_prompt_hash``
    exactly once — mid-session profile rewrites do not affect the running
    session (locked decision #7).

    ``agent`` picks the tool-using variant. It is resolved once, at session
    creation, and baked into both the persisted system message and the
    hash — so ``GET /sessions/{id}`` replays what the model was actually
    told, and Phase 35 eval grouping keys on a prompt that really ran.
    """
    base = system_prompt_for(role, agent=agent)
    text = f"{base}\n\n{profile_block}" if profile_block else base
    return text, hash_prompt(text)
