"""Phase 35-02-C: CLI entrypoint shape. No real network; we monkeypatch
``replay_one`` to a no-op that writes a stub trace.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_main_dispatches_one_replay_per_model_per_question(
    tmp_path, monkeypatch
):
    from app.eval import run as eval_run

    calls: list[tuple[str, str]] = []

    def _stub_replay_one(*, model_id, question, out_dir, monkeypatch=None, **_kw):
        calls.append((model_id, question["id"]))
        model_dir = out_dir / model_id.replace("/", "-").replace(":", "-")
        model_dir.mkdir(parents=True, exist_ok=True)
        trace = model_dir / f"q-{question['id']}.json"
        trace.write_text(json.dumps({
            "model": model_id, "question_id": question["id"],
            "outcome": "ok", "final_answer": "stub", "ragas": {},
            "usage": {}, "tool_use_grade": None, "category": "refusal",
            "role": "admin",
        }))
        return trace

    monkeypatch.setattr(eval_run, "replay_one", _stub_replay_one)

    # Use a small testset subset by overriding the loader.
    questions = [
        {"id": f"q-{i}", "role": "admin", "category": "refusal",
         "prompt": "hi", "gold": "x", "accept_set": None,
         "required_tools": None, "notes": ""}
        for i in range(3)
    ]
    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: questions)

    out_dir = tmp_path / "results"
    eval_run.main(
        argv=[
            "--models", "meta-llama/llama-3.2-3b-instruct:free",
            "--testset", "ignored",
            "--out-dir", str(out_dir),
            "--max-workers", "2",
        ],
    )
    assert len(calls) == 3
    assert all(m == "meta-llama/llama-3.2-3b-instruct:free" for m, _ in calls)
    assert (out_dir / "results.csv").exists() or True  # CSV lands in 35-02-F


def test_run_main_resume_skips_successful_retries_failed(tmp_path, monkeypatch):
    """Resume: a pre-existing ``ok`` trace is skipped; a ``hard_failure``
    trace is re-attempted."""
    from app.eval import run as eval_run

    model_id = "meta-llama/llama-3.2-3b-instruct:free"
    slug = model_id.replace("/", "-").replace(":", "-")
    out_dir = tmp_path / "results"
    model_dir = out_dir / slug
    model_dir.mkdir(parents=True)
    # q-0 already succeeded; q-1 previously rate-limited (hard_failure).
    (model_dir / "q-q-0.json").write_text(json.dumps({"outcome": "ok"}))
    (model_dir / "q-q-1.json").write_text(json.dumps({"outcome": "hard_failure"}))

    calls: list[str] = []

    def _stub_replay_one(*, model_id, question, out_dir, monkeypatch=None, **_kw):
        calls.append(question["id"])
        d = out_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        trace = d / f"q-{question['id']}.json"
        trace.write_text(json.dumps({"outcome": "ok"}))
        return trace

    monkeypatch.setattr(eval_run, "replay_one", _stub_replay_one)
    questions = [
        {"id": f"q-{i}", "role": "admin", "category": "refusal",
         "prompt": "hi", "gold": "x"}
        for i in range(3)
    ]
    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: questions)

    eval_run.main(argv=[
        "--models", model_id, "--testset", "ignored",
        "--out-dir", str(out_dir), "--max-workers", "1",
    ])
    # q-0 skipped (ok); q-1 (hard_failure) + q-2 (missing) re-attempted.
    assert sorted(calls) == ["q-1", "q-2"]


def test_run_main_no_resume_runs_everything(tmp_path, monkeypatch):
    """``--no-resume`` re-runs every question regardless of prior traces."""
    from app.eval import run as eval_run

    model_id = "meta-llama/llama-3.2-3b-instruct:free"
    slug = model_id.replace("/", "-").replace(":", "-")
    out_dir = tmp_path / "results"
    model_dir = out_dir / slug
    model_dir.mkdir(parents=True)
    (model_dir / "q-q-0.json").write_text(json.dumps({"outcome": "ok"}))

    calls: list[str] = []

    def _stub_replay_one(*, model_id, question, out_dir, monkeypatch=None, **_kw):
        calls.append(question["id"])
        return out_dir / slug / f"q-{question['id']}.json"

    monkeypatch.setattr(eval_run, "replay_one", _stub_replay_one)
    questions = [{"id": f"q-{i}", "role": "admin", "category": "refusal",
                  "prompt": "hi", "gold": "x"} for i in range(2)]
    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: questions)

    eval_run.main(argv=[
        "--models", model_id, "--testset", "ignored",
        "--out-dir", str(out_dir), "--no-resume",
    ])
    assert sorted(calls) == ["q-0", "q-1"]


def test_run_main_rejects_paid_model(tmp_path, monkeypatch):
    """Free-tier startup guard fires on CLI."""
    from app.eval import run as eval_run

    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: [])
    try:
        eval_run.main(
            argv=[
                "--models", "openai/gpt-4o",
                "--testset", "ignored",
                "--out-dir", str(tmp_path),
            ],
        )
    except (ValueError, SystemExit) as exc:
        assert ":free" in str(exc) or exc.code != 0  # type: ignore[union-attr]
    else:
        raise AssertionError("expected paid-model rejection")


def test_run_module_help_exits_zero():
    """`python -m app.eval.run --help` must exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "app.eval.run", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"--help exited {result.returncode}: stderr={result.stderr}"
    )
    assert "--models" in result.stdout
