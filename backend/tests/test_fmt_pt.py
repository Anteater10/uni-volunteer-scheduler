"""_fmt_pt: the Pacific-time label on signup copy (roadmap #168).

The "timezone failed to load" fallback was deleted as dead (tzdata is
pinned), so these pin the three inputs the function still handles.
"""
from datetime import datetime, timezone

from app.services.public_signup_service import _fmt_pt


def test_none_formats_as_empty():
    assert _fmt_pt(None) == ""


def test_aware_utc_is_shown_in_pacific():
    # 17:00 UTC on 2026-09-21 is 10:00 PDT.
    assert _fmt_pt(datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)) == "Sep 21 2026 10:00 AM PT"


def test_naive_is_treated_as_utc():
    assert _fmt_pt(datetime(2026, 1, 5, 20, 30)) == "Jan 05 2026 12:30 PM PT"
