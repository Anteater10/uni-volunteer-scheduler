"""Shared ISO-week parsing helper.

Extracted from list_modules so every week-aware read tool can share one
regex and one ValueError contract.
"""
from __future__ import annotations

import re

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def parse_iso_week(s: str) -> tuple[int, int]:
    m = _WEEK_RE.match(s)
    if not m:
        raise ValueError(f"bad ISO week: {s!r}")
    return int(m.group(1)), int(m.group(2))
