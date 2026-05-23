"""Boundary layer 3: PII redactor.

Runs last, after schema filter (layer 1) and role-scope (layer 2). Scans every
string value in the payload (regardless of key) for known PII shapes — email,
phone, SSN, UCSB campus NID — and replaces matches with `[REDACTED:<kind>]`.

Each match produces a `RedactionEvent`. The `declared` flag tells us whether the
caller (typically the tool dispatcher) declared this payload's fields as
potentially containing PII. A hit on a declared field is expected and harmless
after redaction (severity `"LOW"`). A hit on an undeclared payload means
schema-filter and role-scope both let the value through — this is a boundary
bug upstream and is flagged `"HIGH"`."""

from dataclasses import dataclass
from typing import Any
import re


@dataclass(frozen=True)
class RedactionEvent:
    kind: str
    severity: str
    path: str
    original_len: int


# Order matters: email first (contains `.` which other patterns ignore), then
# SSN (3-2-4 digits) before phone (3-3-4 digits) so the more specific shape
# wins, then phone, then UCSB NID (letters + digits — no overlap with the
# others but kept last for clarity).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ucsb_nid", re.compile(r"\b[A-Za-z]{1,3}\d{5,7}\b")),
]


def _scrub_string(
    value: str, *, path: str, declared: bool
) -> tuple[str, list[RedactionEvent]]:
    events: list[RedactionEvent] = []
    severity = "LOW" if declared else "HIGH"
    out = value
    for kind, pattern in _PATTERNS:
        def _replace(match: re.Match[str], _kind: str = kind) -> str:
            events.append(
                RedactionEvent(
                    kind=_kind,
                    severity=severity,
                    path=path,
                    original_len=len(match.group(0)),
                )
            )
            return f"[REDACTED:{_kind}]"

        out = pattern.sub(_replace, out)
    return out, events


def _walk(
    data: Any, *, path: str, declared: bool
) -> tuple[Any, list[RedactionEvent]]:
    if isinstance(data, str):
        return _scrub_string(data, path=path, declared=declared)
    if isinstance(data, list):
        new_list: list[Any] = []
        all_events: list[RedactionEvent] = []
        for i, item in enumerate(data):
            child_path = f"{path}.{i}" if path else str(i)
            new_item, events = _walk(item, path=child_path, declared=declared)
            new_list.append(new_item)
            all_events.extend(events)
        return new_list, all_events
    if isinstance(data, dict):
        new_dict: dict[Any, Any] = {}
        all_events = []
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else str(key)
            new_value, events = _walk(value, path=child_path, declared=declared)
            new_dict[key] = new_value
            all_events.extend(events)
        return new_dict, all_events
    # ints, bools, None, floats — pass through
    return data, []


def scrub(data: Any, *, declared: bool) -> tuple[Any, list[RedactionEvent]]:
    """Walk `data`, redact PII in string values, return (scrubbed, events).

    The input is not mutated; lists and dicts are rebuilt. `declared=True` means
    the caller acknowledged this payload may contain PII (e.g. a roster tool
    that selects email by name) — hits are expected, severity `"LOW"`. `False`
    means a hit is a layer-3 catch of an upstream boundary bug, severity
    `"HIGH"`."""
    return _walk(data, path="", declared=declared)
