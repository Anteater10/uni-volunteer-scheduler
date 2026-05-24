"""Phase 35-02-F: CSV writer with locked column order.

Spec §8.1 header:
  model,question_id,category,role,ragas_faithfulness,ragas_answer_relevancy,
  ragas_context_precision,tool_use_correct,outcome,latency_ms,
  prompt_tokens,completion_tokens
"""
from __future__ import annotations

import csv

_LOCKED_HEADER = [
    "model", "question_id", "category", "role",
    "ragas_faithfulness", "ragas_answer_relevancy", "ragas_context_precision",
    "tool_use_correct", "outcome",
    "latency_ms", "prompt_tokens", "completion_tokens",
]


def test_csv_header_is_locked(tmp_path):
    from app.eval.reports import write_results_csv

    write_results_csv(traces=[], out_path=tmp_path / "results.csv")
    with (tmp_path / "results.csv").open() as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == _LOCKED_HEADER


def test_csv_row_serializes_one_trace(tmp_path):
    from app.eval.reports import write_results_csv

    trace = {
        "model": "x:free", "question_id": "q-1", "category": "refusal",
        "role": "admin",
        "ragas": {
            "faithfulness": 0.81, "answer_relevancy": 0.79,
            "context_precision": None,
        },
        "tool_use_grade": {"tool_use_correct": True},
        "outcome": "ok",
        "usage": {
            "latency_ms": 1842, "prompt_tokens": 1820, "completion_tokens": 96,
        },
    }
    write_results_csv(traces=[trace], out_path=tmp_path / "results.csv")
    with (tmp_path / "results.csv").open() as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["model"] == "x:free"
    assert row["ragas_faithfulness"] == "0.81"
    assert row["ragas_context_precision"] == ""  # null serialises as empty
    assert row["tool_use_correct"] == "true"


def test_csv_row_nulls_for_non_agentic_tool_use(tmp_path):
    from app.eval.reports import write_results_csv

    trace = {
        "model": "x:free", "question_id": "q-2", "category": "profile_recall",
        "role": "participant",
        "ragas": {"faithfulness": 0.5, "answer_relevancy": 0.5,
                  "context_precision": 0.5},
        "tool_use_grade": None,
        "outcome": "ok",
        "usage": {"latency_ms": 10, "prompt_tokens": 1, "completion_tokens": 1},
    }
    write_results_csv(traces=[trace], out_path=tmp_path / "results.csv")
    with (tmp_path / "results.csv").open() as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["tool_use_correct"] == ""
