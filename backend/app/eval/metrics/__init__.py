"""Phase 35-02-D — metric orchestration.

Walk every per-question JSON trace under ``out_dir`` and attach RAGAS +
tool-use grades. Human-rating join is computed separately (per-model,
not per-question) and consumed by the report renderer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .ragas import score_trace as _score_ragas
from .tooluse import grade_trace as _grade_tooluse


def score_all_traces(
    *,
    out_dir: Path,
    questions: list[dict[str, Any]],
    judge: Callable[..., dict[str, float | None]] | None = None,
) -> None:
    """Mutate every trace JSON in-place: attach ``ragas`` and
    ``tool_use_grade`` fields.
    """
    q_by_id = {q["id"]: q for q in questions}
    for trace_path in Path(out_dir).rglob("q-*.json"):
        try:
            trace = json.loads(trace_path.read_text())
        except json.JSONDecodeError:
            continue
        qid = trace.get("question_id")
        question = q_by_id.get(qid)
        if not question:
            continue
        trace["ragas"] = _score_ragas(trace, question, judge=judge) if judge \
            else trace.get("ragas")
        trace["tool_use_grade"] = _grade_tooluse(trace, question)
        trace_path.write_text(json.dumps(trace, indent=2, default=str))


__all__ = ["score_all_traces"]
