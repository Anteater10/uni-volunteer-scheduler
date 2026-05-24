"""Phase 35-02-F — report renderers.

Three outputs:
1. ``results.csv`` — locked column order (spec §8.1).
2. ``per-question-traces.json`` — array of full trace objects (spec §8.2).
3. ``docs/documentation/35-02-multimodel-eval/results.md`` — auto-rendered
   markdown (spec §8.3).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

LOCKED_HEADER = [
    "model", "question_id", "category", "role",
    "ragas_faithfulness", "ragas_answer_relevancy", "ragas_context_precision",
    "tool_use_correct", "outcome",
    "latency_ms", "prompt_tokens", "completion_tokens",
]


def _fmt_float(v: Any) -> str:
    if v is None:
        return ""
    return f"{v}"


def _fmt_bool(v: Any) -> str:
    if v is None:
        return ""
    return "true" if v else "false"


def _row(trace: dict[str, Any]) -> dict[str, str]:
    ragas = trace.get("ragas") or {}
    tug = trace.get("tool_use_grade")
    usage = trace.get("usage") or {}
    return {
        "model": trace.get("model") or "",
        "question_id": trace.get("question_id") or "",
        "category": trace.get("category") or "",
        "role": trace.get("role") or "",
        "ragas_faithfulness": _fmt_float(ragas.get("faithfulness")),
        "ragas_answer_relevancy": _fmt_float(ragas.get("answer_relevancy")),
        "ragas_context_precision": _fmt_float(ragas.get("context_precision")),
        "tool_use_correct": _fmt_bool(
            tug.get("tool_use_correct") if tug else None
        ),
        "outcome": trace.get("outcome") or "",
        "latency_ms": _fmt_float(usage.get("latency_ms")),
        "prompt_tokens": _fmt_float(usage.get("prompt_tokens")),
        "completion_tokens": _fmt_float(usage.get("completion_tokens")),
    }


def write_results_csv(
    *, traces: Iterable[dict[str, Any]], out_path: Path,
) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOCKED_HEADER)
        writer.writeheader()
        for t in traces:
            writer.writerow(_row(t))


__all__ = ["LOCKED_HEADER", "write_results_csv"]
