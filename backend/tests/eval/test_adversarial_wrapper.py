"""Phase 35-02-E: adversarial wrapper shape tests.

CI-safe — we monkeypatch the case-runner to a sentinel and assert the
wrapper iterates models x cases and writes one JSON per model. The
real ``_run_one_case`` requires DB state that the offline harness
does not set up; it is therefore exercised only via the manual
driver path on Andy's machine.
"""
from __future__ import annotations

import json

import pytest


def test_wrapper_iterates_models_writes_per_model_json(tmp_path, monkeypatch):
    from app.eval import adversarial

    monkeypatch.setattr(
        adversarial, "_load_cases",
        lambda: [
            {"id": "C1", "category": "injection"},
            {"id": "C2", "category": "overreach"},
        ],
    )

    def _stub_run_one(model_id, case):
        return {
            "id": case["id"],
            "category": case["category"],
            "outcome": "pass",
            "trace_path": "n/a",
        }

    monkeypatch.setattr(adversarial, "_run_one_case", _stub_run_one)
    # Avoid touching os.environ during a CI run.
    monkeypatch.setattr(
        adversarial, "set_model_for_replay", lambda mid, monkeypatch=None: None
    )

    out_dir = tmp_path / "adv"
    adversarial.run_adversarial(
        models=["model-a:free", "model-b:free"],
        out_dir=out_dir,
    )
    paths = sorted(out_dir.iterdir())
    assert [p.name for p in paths] == [
        "model-a-free.json",
        "model-b-free.json",
    ]
    a = json.loads(paths[0].read_text())
    assert a["model"] == "model-a:free"
    assert {c["id"] for c in a["cases"]} == {"C1", "C2"}
    assert a["categories"]["injection"]["pass"] == 1
    assert a["categories"]["injection"]["n"] == 1
    assert a["categories"]["overreach"]["pass"] == 1
    assert a["categories"]["overreach"]["n"] == 1


def test_wrapper_rejects_paid_model(tmp_path):
    from app.eval import adversarial

    with pytest.raises(ValueError, match=":free"):
        adversarial.run_adversarial(
            models=["openai/gpt-4o"], out_dir=tmp_path,
        )
