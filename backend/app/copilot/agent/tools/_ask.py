"""Shared "ask, don't guess" plumbing for the write tools.

Every tool that changes data runs a ``precheck`` before the confirmation
card is built (see ``Tool.precheck``). The rule it enforces is one rule:

    A value the user did not state is not a value the tool may choose.

The tool that taught us this filled a missing start time with 09:00. The
event looked correct — right school, right week, right module — and would
have gone on looking correct until somebody stood in an empty classroom at
nine in the morning. A refusal is visible; an invented number is not.

Two shapes of question live here:

- :func:`ask_for` — "you did not tell me X". The model relays it and calls
  the tool again with the answers.
- :func:`ambiguous` — "X could mean two things". Same mechanism, different
  reason: the tool understood the words and still cannot act on them.

Both return the same payload so the model only has to learn one shape, and
both name a suggested value where a real one exists (a module's configured
capacity, say) so asking costs one round trip rather than twenty.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

_PREFACE = (
    "I can't do this yet — some details weren't given and I'm not going to "
    "invent them, because a wrong value nobody was asked about looks correct "
    "until it isn't. Ask the user for the following, in one message, then "
    "call this tool again with the answers. Do not guess, and do not use a "
    "suggested value without the user agreeing to it."
)

_AMBIGUOUS_PREFACE = (
    "I can't do this yet — the request could mean more than one thing and "
    "picking wrong would change what happens. Put the choice below to the "
    "user and call this tool again once they have decided."
)


def ask_for(missing: list[str]) -> dict[str, Any] | None:
    """The payload a precheck returns, or None when nothing is missing.

    Returning None rather than an empty payload is what lets a precheck end
    with ``return ask_for(missing)`` and still fall through to the handler
    when the request was complete.
    """
    if not missing:
        return None
    return {"needs_answers": missing, "question": _PREFACE}


def ambiguous(choices: list[str]) -> dict[str, Any]:
    """The request parsed, and still has more than one reading."""
    return {"needs_answers": choices, "question": _AMBIGUOUS_PREFACE}


def suggesting(text: str, value: Any) -> str:
    """"how many volunteers (the module is set to 20)" — ask, with a hint.

    A bare "how many volunteers?" makes the user go and look it up, so they
    stop using the copilot and open the admin page instead. Naming the
    configured value keeps this one exchange while leaving the decision
    where it belongs.
    """
    return text if value in (None, "") else f"{text} (currently {value})"


def service_error(exc: HTTPException) -> dict[str, Any]:
    """Turn a service-layer HTTPException into something the model can act on.

    The services raise HTTPException because their first caller was a
    router. Letting that escape a tool would surface to the admin as a 500
    from the copilot rather than as the specific, already-well-worded
    complaint the service made ("Dates overlap Summer 2026 · Session B").
    """
    detail = exc.detail
    if isinstance(detail, dict):
        detail = detail.get("detail") or detail.get("message") or str(detail)
    return {"error": str(detail)}
