"""Phase 35-03 — ``--grounded`` CLI routing. No real network, no DB.

When ``--grounded`` is passed, ``run.main`` must dispatch ``replay_grounded``
(one per model×question), open a DB session per call, and honor resume. We
stub ``replay_grounded`` and the session factory.
"""
from __future__ import annotations

import json


def test_grounded_flag_dispatches_replay_grounded(tmp_path, monkeypatch):
    from app.eval import run as eval_run

    calls: list[tuple[str, str]] = []

    def _stub_grounded(*, model_id, question, db, out_dir, **_kw):
        calls.append((model_id, question["id"]))
        d = out_dir / model_id.replace("/", "-").replace(":", "-")
        d.mkdir(parents=True, exist_ok=True)
        trace = d / f"q-{question['id']}.json"
        trace.write_text(json.dumps({"outcome": "ok"}))
        return trace

    sessions_opened = {"n": 0, "closed": 0}

    class _FakeSession:
        def close(self):
            sessions_opened["closed"] += 1

    def _fake_factory():
        sessions_opened["n"] += 1
        return _FakeSession()

    monkeypatch.setattr(eval_run, "replay_grounded", _stub_grounded)
    monkeypatch.setattr(eval_run, "_make_session", _fake_factory)
    questions = [
        {"id": f"q-{i}", "role": "admin", "category": "policy_recall",
         "prompt": "hi", "gold": "x"}
        for i in range(3)
    ]
    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: questions)

    out_dir = tmp_path / "results"
    eval_run.main(argv=[
        "--models", "meta-llama/llama-3.2-3b-instruct:free",
        "--testset", "ignored", "--out-dir", str(out_dir),
        "--grounded", "--max-workers", "1",
    ])
    assert len(calls) == 3
    # one session opened and closed per question
    assert sessions_opened["n"] == 3
    assert sessions_opened["closed"] == 3


def test_grounded_resume_skips_done(tmp_path, monkeypatch):
    from app.eval import run as eval_run

    model_id = "meta-llama/llama-3.2-3b-instruct:free"
    slug = model_id.replace("/", "-").replace(":", "-")
    out_dir = tmp_path / "results"
    (out_dir / slug).mkdir(parents=True)
    (out_dir / slug / "q-q-0.json").write_text(json.dumps({"outcome": "ok"}))

    calls: list[str] = []

    def _stub_grounded(*, model_id, question, db, out_dir, **_kw):
        calls.append(question["id"])
        d = out_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / f"q-{question['id']}.json").write_text(json.dumps({"outcome": "ok"}))
        return d / f"q-{question['id']}.json"

    monkeypatch.setattr(eval_run, "replay_grounded", _stub_grounded)
    monkeypatch.setattr(eval_run, "_make_session", lambda: type(
        "S", (), {"close": lambda self: None})())
    questions = [{"id": f"q-{i}", "role": "admin", "category": "policy_recall",
                  "prompt": "hi", "gold": "x"} for i in range(2)]
    monkeypatch.setattr(eval_run, "_load_testset", lambda *_a, **_kw: questions)

    eval_run.main(argv=[
        "--models", model_id, "--testset", "ignored",
        "--out-dir", str(out_dir), "--grounded", "--max-workers", "1",
    ])
    assert calls == ["q-1"]  # q-0 already ok → skipped
