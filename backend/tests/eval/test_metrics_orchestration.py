"""Phase 35-02-D: pipeline that runs all three metrics over a directory
of traces. The RAGAS judge is injected as a stub.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_score_all_traces_attaches_ragas_and_tooluse(tmp_path):
    from app.eval.metrics import score_all_traces

    model_dir = tmp_path / "model-x"
    model_dir.mkdir()
    trace = {
        "model": "x:free", "question_id": "q-1",
        "role": "admin", "category": "refusal",
        "prompt": "x", "final_answer": "I can't.",
        "tool_calls": [], "retrieved_context": [],
        "ragas": {
            "faithfulness": None, "answer_relevancy": None,
            "context_precision": None,
        },
        "tool_use_grade": None,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "latency_ms": 1},
        "outcome": "ok",
    }
    (model_dir / "q-q-1.json").write_text(json.dumps(trace))

    questions = [{
        "id": "q-1", "role": "admin", "category": "refusal",
        "prompt": "x", "gold": "refuses",
        "accept_set": ["I can't"],
        "required_tools": [{"name": "send_reminder_email",
                            "should_refuse": True}],
        "notes": "",
    }]
    score_all_traces(
        out_dir=tmp_path, questions=questions,
        judge=lambda **_: {
            "faithfulness": 0.9, "answer_relevancy": 0.8,
            "context_precision": 0.7,
        },
    )
    updated = json.loads((model_dir / "q-q-1.json").read_text())
    assert updated["ragas"]["context_precision"] is None
    assert updated["tool_use_grade"]["tool_use_correct"] is True
