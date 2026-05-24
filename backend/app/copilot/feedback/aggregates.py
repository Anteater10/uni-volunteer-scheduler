"""Phase 35-01: feedback aggregate stubs.

Real SQL implementations land in 35-01-C (Tasks 10 + 11). These stubs
exist so the endpoint shells in 35-01-B can be wired and the router
contract is bisectable. They return empty/skeleton shapes so the
422-/404-bound endpoint tests pass without a real aggregator.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session


def weekly_rollup(db: Session, *, weeks: int) -> list[dict[str, Any]]:
    """Return ``weeks`` rows of empty per-week stats.

    Stub: 35-01-C Task 10 replaces this with a real ISO-week aggregate.
    Returns the most recent ``weeks`` ISO-week buckets with all metrics
    null/zero so the endpoint contract is satisfied for tests that only
    care about the row count + 422/404 surface.
    """
    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for i in range(weeks):
        d = today - timedelta(weeks=i)
        iso_year, iso_week, _ = d.isocalendar()
        rows.append(
            {
                "iso_week": f"{iso_year:04d}-W{iso_week:02d}",
                "thumbs_up_rate": None,
                "session_rating_avg": None,
                "n_messages": 0,
                "n_sessions": 0,
            }
        )
    return rows


def bottom_messages(db: Session, *, limit: int) -> list[dict[str, Any]]:
    """Return an empty list of bottom-quartile messages.

    Stub: 35-01-C Task 11 replaces this with a real SQL query that
    selects the lowest-rated assistant messages.
    """
    return []
