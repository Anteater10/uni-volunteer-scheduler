"""Make the model's arguments match the shape the tool declared.

Models double-encode. Asked for a list of shifts, one will hand back the
list; another hands back a *string containing* the list, JSON inside JSON.
Both look like a well-formed tool call from the outside, and the second one
reached a handler that did ``shift.get("sessions")`` on a ``str`` and took
the whole request down with a 500 — after the confirmation card had already
been shown, so the admin clicked Confirm and got "Load failed".

So: where the schema says array or object and a string arrived, parse it.
Where it cannot be parsed, say so plainly and let the caller route it to the
model's retry path. A half-decoded argument is worse than a refused one —
it is the shape of a truncated tool call, and the missing half is silent.
"""
from __future__ import annotations

import json
from typing import Any

_STRUCTURED = {"array", "object"}


class CoercionError(ValueError):
    """A declared-structured argument arrived as unparseable text."""


def coerce_args(json_schema: dict[str, Any] | None, args: Any) -> dict[str, Any]:
    """Return ``args`` with stringified arrays/objects decoded.

    Raises :class:`CoercionError` when a string that should have been
    structured will not parse — which is what a truncated argument looks
    like, and the only signal we get that the model ran out of room.
    """
    if not isinstance(args, dict):
        raise CoercionError("tool arguments must be an object")
    properties = (json_schema or {}).get("properties") or {}

    out: dict[str, Any] = {}
    for key, value in args.items():
        declared = (properties.get(key) or {}).get("type")
        if declared in _STRUCTURED and isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError) as exc:
                raise CoercionError(
                    f"the {key!r} argument arrived as text that is not valid "
                    "JSON, which usually means it was cut off before it "
                    "finished. Send it again, shorter if you can."
                ) from exc
            expected = list if declared == "array" else dict
            if not isinstance(parsed, expected):
                raise CoercionError(
                    f"the {key!r} argument decoded to "
                    f"{type(parsed).__name__}, not {declared}"
                )
            out[key] = parsed
        else:
            out[key] = value
    return out
