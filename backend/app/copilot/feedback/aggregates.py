"""Phase 35-01-C: feedback aggregate SQL.

Two read-only aggregators backing the admin feedback page:

- :func:`weekly_rollup` — ISO-week buckets (``date_trunc('week', ...)``,
  which in Postgres is Monday-start and matches ISO 8601). Returns one row
  per week in the window, oldest-first, with thumbs-up rate, session-rating
  average, and counts. Empty buckets get ``None`` for the rates (guarded
  with ``NULLIF`` semantics) so the frontend can distinguish "no data"
  from "0% up".
- :func:`bottom_messages` — bottom-quartile drill-down keyed off the
  partial index ``ix_copilot_message_ratings_value_down`` (created in
  35-01-A). Joins back to ``copilot_messages`` for the assistant text and
  uses a correlated sub-select for the immediately preceding ``role='user'``
  turn so reviewers can see what was asked.

The ``assistant_text`` and ``prior_user_text`` values are returned
**verbatim** — the Phase 33 redactor scrubbed them at persist-time and
re-scrubbing here would be redundant and slow. The
``test_bottom_messages_does_not_re_scrub_pii`` regression pins that
behaviour.

ISO-week label format: ``IYYY-"W"IW`` (e.g. ``2026-W21``). The literal
``"W"`` is required in the Postgres format string. The Python skeleton
uses ``datetime.isocalendar()`` which agrees with Postgres ISO semantics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session


def _iso_week_label(d: datetime) -> str:
    """Return the ``YYYY-Www`` label for a datetime (ISO-week, ISO-year)."""
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def weekly_rollup(db: Session, *, weeks: int) -> list[dict[str, Any]]:
    """Return ``weeks`` rows of per-ISO-week feedback stats, oldest first.

    Each row:

    - ``iso_week``: ``YYYY-Www`` label (ISO 8601 week-of-year).
    - ``thumbs_up_rate``: ``count(up) / count(up|down)`` or ``None`` when
      no message ratings landed in the bucket.
    - ``session_rating_avg``: AVG over ``copilot_session_ratings.value``
      (1-5 integer), or ``None`` when no session ratings in the bucket.
    - ``n_messages``: count of message ratings in the bucket.
    - ``n_sessions``: count of session ratings in the bucket.
    """
    now = datetime.now(timezone.utc)
    # Build the skeleton of N week labels covering the window. We anchor
    # by subtracting whole weeks from "now" — close enough for the label
    # given Postgres' ISO-week alignment.
    skeleton: list[dict[str, Any]] = []
    for i in range(weeks):
        week_anchor = now - timedelta(weeks=i)
        skeleton.append(
            {
                "iso_week": _iso_week_label(week_anchor),
                "thumbs_up_rate": None,
                "session_rating_avg": None,
                "n_messages": 0,
                "n_sessions": 0,
            }
        )
    skeleton.reverse()  # oldest first

    cutoff = now - timedelta(weeks=weeks)

    msg_rows = db.execute(
        sa_text(
            """
            SELECT
              to_char(date_trunc('week', created_at), 'IYYY-"W"IW') AS iso_week,
              COUNT(*) FILTER (WHERE value = 'up')   AS n_up,
              COUNT(*) FILTER (WHERE value IN ('up','down')) AS n_total
            FROM copilot_message_ratings
            WHERE created_at >= :cutoff
            GROUP BY 1
            """
        ),
        {"cutoff": cutoff},
    ).all()
    msg_by_week = {r.iso_week: (r.n_up, r.n_total) for r in msg_rows}

    sess_rows = db.execute(
        sa_text(
            """
            SELECT
              to_char(date_trunc('week', created_at), 'IYYY-"W"IW') AS iso_week,
              AVG(value)::float AS avg_value,
              COUNT(*)          AS n_sessions
            FROM copilot_session_ratings
            WHERE created_at >= :cutoff
            GROUP BY 1
            """
        ),
        {"cutoff": cutoff},
    ).all()
    sess_by_week = {r.iso_week: (r.avg_value, r.n_sessions) for r in sess_rows}

    for entry in skeleton:
        wk = entry["iso_week"]
        if wk in msg_by_week:
            n_up, n_total = msg_by_week[wk]
            entry["n_messages"] = int(n_total)
            entry["thumbs_up_rate"] = (
                (n_up / n_total) if n_total else None
            )
        if wk in sess_by_week:
            avg_value, n_sessions = sess_by_week[wk]
            entry["n_sessions"] = int(n_sessions)
            entry["session_rating_avg"] = avg_value
    return skeleton


def bottom_messages(db: Session, *, limit: int) -> list[dict[str, Any]]:
    """Stub — replaced by the real drill-down in 35-01-C Task 11."""
    return []
