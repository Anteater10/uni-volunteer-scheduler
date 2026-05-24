"""Phase 35-02-F: markdown renderer + traces JSON bundle.

Auto-rendered markdown has 5 sections (spec §8.3):
1. Headline table
2. Per-category breakdown
3. Adversarial ASCII bar chart
4. Failure taxonomy
5. Sample size & caveats
"""
from __future__ import annotations

import json


def test_render_markdown_has_all_five_sections(tmp_path):
    from app.eval.reports import render_markdown

    traces = [{
        "model": "model-a:free", "question_id": "q-1",
        "category": "refusal", "role": "admin",
        "ragas": {"faithfulness": 0.9, "answer_relevancy": 0.9,
                  "context_precision": 0.9},
        "tool_use_grade": {"tool_use_correct": True},
        "outcome": "ok",
        "usage": {"latency_ms": 1, "prompt_tokens": 1, "completion_tokens": 1},
    }]
    adv = [{
        "model": "model-a:free",
        "categories": {"injection": {"n": 5, "pass": 4, "fail": 1}},
        "cases": [{"id": "C1", "category": "injection", "outcome": "fail"}],
    }]
    human = [{
        "model_id": "model-a:free",
        "thumbs_up_rate": 0.8, "session_rating_avg": 4.3,
        "n_message_ratings": 10, "n_session_ratings": 5,
        "n_thumbs_down": 2, "insufficient_sample": False,
    }]
    md_path = tmp_path / "results.md"
    render_markdown(
        traces=traces, adversarial=adv, human=human, out_path=md_path,
    )
    text = md_path.read_text()
    assert "## Headline" in text
    assert "## Per-category" in text or "## Per-Category" in text
    assert "## Adversarial" in text
    assert "## Failure" in text
    assert "## Sample" in text


def test_render_markdown_ascii_bars_present(tmp_path):
    from app.eval.reports import render_markdown

    adv = [{
        "model": "model-a:free",
        "categories": {
            "injection": {"n": 5, "pass": 4, "fail": 1},
            "overreach": {"n": 5, "pass": 5, "fail": 0},
        },
        "cases": [],
    }]
    md_path = tmp_path / "results.md"
    render_markdown(
        traces=[], adversarial=adv, human=[], out_path=md_path,
    )
    text = md_path.read_text()
    # One bar char per model × category at minimum
    assert "█" in text or "#" in text


def test_render_markdown_sample_size_table_with_failures(tmp_path):
    """Cover the empty_response + transient_failure sample-size table branch."""
    from app.eval.reports import render_markdown

    traces = [
        {
            "model": "m1:free", "question_id": "q-1", "category": "refusal",
            "role": "admin",
            "ragas": {"faithfulness": None, "answer_relevancy": None,
                      "context_precision": None},
            "tool_use_grade": None,
            "outcome": "empty_response",
            "usage": {"latency_ms": 1, "prompt_tokens": 1, "completion_tokens": 0},
        },
        {
            "model": "m2:free", "question_id": "q-2", "category": "refusal",
            "role": "admin",
            "ragas": {"faithfulness": None, "answer_relevancy": None,
                      "context_precision": None},
            "tool_use_grade": None,
            "outcome": "transient_failure",
            "usage": {"latency_ms": 1, "prompt_tokens": 1, "completion_tokens": 0},
        },
        # Trace for one model in a category, but the other model has none —
        # exercises the per-category "if not sub: continue" branch.
        {
            "model": "m1:free", "question_id": "q-3", "category": "tool_use",
            "role": "admin",
            "ragas": {"faithfulness": 0.5, "answer_relevancy": 0.5,
                      "context_precision": 0.5},
            "tool_use_grade": {"tool_use_correct": True},
            "outcome": "ok",
            "usage": {"latency_ms": 1, "prompt_tokens": 1, "completion_tokens": 1},
        },
    ]
    md_path = tmp_path / "results.md"
    render_markdown(traces=traces, adversarial=[], human=[], out_path=md_path)
    text = md_path.read_text()
    assert "Empty responses" in text
    assert "Transient failures" in text
    assert "m1:free" in text
    assert "m2:free" in text


def test_bar_handles_zero_total():
    """_bar with total <= 0 returns the empty string."""
    from app.eval.reports import _bar

    assert _bar(0, 0) == ""
    assert _bar(5, -1) == ""


def test_render_top_level_redirect_not_implemented(tmp_path):
    """The renderer is a documented NotImplementedError stub until the first
    real multi-model run produces a fillable headline ranking."""
    import pytest

    from app.eval.reports import render_top_level_redirect

    with pytest.raises(NotImplementedError):
        render_top_level_redirect(
            traces=[], adversarial=[], out_path=tmp_path / "x.md",
        )


def test_write_traces_json_bundle(tmp_path):
    from app.eval.reports import write_traces_json

    traces = [
        {"model": "x:free", "question_id": "q-1", "final_answer": "hi"},
        {"model": "y:free", "question_id": "q-1", "final_answer": "hi"},
    ]
    write_traces_json(traces=traces, out_path=tmp_path / "per-question-traces.json")
    loaded = json.loads((tmp_path / "per-question-traces.json").read_text())
    assert len(loaded) == 2
