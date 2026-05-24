"""Phase 35-02-D — human-rating join.

Reads the 35-01 feedback tables (``copilot_message_ratings``,
``copilot_session_ratings``) and joins them through ``copilot_sessions``
to ``copilot_sessions.model_id``. Per-model: thumbs-up rate, average
session rating, n_thumbs_down, insufficient-sample flag (n < 10).

Spec §6.3.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session


_INSUFFICIENT_N = 10


def per_model_rollup(db: Session) -> list[dict[str, Any]]:
    """One dict per model_id observed in ``copilot_sessions``."""
    msg_rows = db.execute(sa_text(
        """
        SELECT
          s.model_id                                                AS model_id,
          COUNT(r.id)                                               AS n_total,
          COUNT(*) FILTER (WHERE r.value = 'up')                    AS n_up,
          COUNT(*) FILTER (WHERE r.value = 'down')                  AS n_down
        FROM copilot_message_ratings r
        JOIN copilot_messages m  ON m.id = r.message_id
        JOIN copilot_sessions s  ON s.id = m.session_id
        WHERE s.model_id IS NOT NULL
        GROUP BY s.model_id
        """
    )).all()

    sess_rows = db.execute(sa_text(
        """
        SELECT
          s.model_id                            AS model_id,
          AVG(r.value)::float                   AS avg_value,
          COUNT(*)                              AS n_sessions
        FROM copilot_session_ratings r
        JOIN copilot_sessions s ON s.id = r.session_id
        WHERE s.model_id IS NOT NULL
        GROUP BY s.model_id
        """
    )).all()

    by_model: dict[str, dict[str, Any]] = {}
    for r in msg_rows:
        by_model[r.model_id] = {
            "model_id": r.model_id,
            "n_message_ratings": int(r.n_total or 0),
            "thumbs_up_rate": (
                (r.n_up / r.n_total) if r.n_total else None
            ),
            "n_thumbs_down": int(r.n_down or 0),
            "session_rating_avg": None,
            "n_session_ratings": 0,
            "insufficient_sample": False,
        }
    for r in sess_rows:
        entry = by_model.setdefault(r.model_id, {
            "model_id": r.model_id, "n_message_ratings": 0,
            "thumbs_up_rate": None, "n_thumbs_down": 0,
        })
        entry["session_rating_avg"] = r.avg_value
        entry["n_session_ratings"] = int(r.n_sessions or 0)

    for entry in by_model.values():
        n = entry.get("n_message_ratings", 0) + entry.get("n_session_ratings", 0)
        entry["insufficient_sample"] = n < _INSUFFICIENT_N

    return sorted(by_model.values(), key=lambda r: r["model_id"])


__all__ = ["per_model_rollup"]
