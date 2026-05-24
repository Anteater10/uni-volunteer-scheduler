"""Phase 35-02-D: RAGAS adapter unit tests. No real network — the judge
LLM is stubbed via a fake ``score_one`` callable injected into the adapter.
"""
from __future__ import annotations

import pytest


def test_score_trace_empty_answer_returns_null_metrics():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "",
        "prompt": "hi",
        "retrieved_context": [{"doc_id": "d1", "snippet": "x"}],
    }
    question = {"gold": "irrelevant"}
    out = score_trace(trace, question, judge=lambda *_a, **_kw: {
        "faithfulness": 1.0, "answer_relevancy": 1.0, "context_precision": 1.0,
    })
    assert out == {
        "faithfulness": None, "answer_relevancy": None,
        "context_precision": None,
    }


def test_score_trace_no_context_skips_context_precision():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "answer text",
        "prompt": "hi",
        "retrieved_context": [],
    }
    question = {"gold": "answer text"}

    def _judge(**kwargs):
        return {
            "faithfulness": 0.9, "answer_relevancy": 0.9,
            "context_precision": 0.5,
        }

    out = score_trace(trace, question, judge=_judge)
    assert out["faithfulness"] == 0.9
    assert out["answer_relevancy"] == 0.9
    assert out["context_precision"] is None


def test_score_trace_judge_error_records_null(monkeypatch):
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "text",
        "prompt": "hi",
        "retrieved_context": [{"doc_id": "d", "snippet": "s"}],
    }
    question = {"gold": "text"}

    def _judge(**_kw):
        raise RuntimeError("judge unreachable")

    out = score_trace(trace, question, judge=_judge)
    assert out == {
        "faithfulness": None, "answer_relevancy": None,
        "context_precision": None,
    }


def test_score_trace_passes_values_through_on_happy_path():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "the answer",
        "prompt": "the question",
        "retrieved_context": [{"doc_id": "d", "snippet": "the answer"}],
    }
    question = {"gold": "the answer"}
    out = score_trace(trace, question, judge=lambda **_: {
        "faithfulness": 0.81, "answer_relevancy": 0.79, "context_precision": 0.74,
    })
    assert out == {
        "faithfulness": 0.81, "answer_relevancy": 0.79, "context_precision": 0.74,
    }
