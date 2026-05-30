"""Phase 35-03 — grounded replay driver shape tests. No real network, no DB.

``replay_grounded`` mirrors the deployed retrieval-grounded completion path
(router ``_sse_stream``): retrieve → build context block → complete(). We
inject a fake ``retrieve`` callable and monkeypatch ``stream_completion`` so
the test exercises only the (model, question, citations) → trace plumbing.

The load-bearing assertion is that ``retrieved_context`` is populated with
``snippet`` entries — that is the field RAGAS faithfulness/context_precision
reads (``app.eval.metrics.ragas``), which was uniformly empty on the bare
35-02 path and is the whole point of this phase.
"""
from __future__ import annotations

import json
from uuid import uuid4

from app.copilot.schemas import Citation


def _one_citation(quote="Module templates are imported quarterly, every 11 weeks."):
    return Citation(
        chunk_id=uuid4(),
        source_path="CLAUDE.md",
        char_start=0,
        char_end=len(quote),
        quote=quote,
        rrf_score=0.5,
        rerank_score=0.9,
    )


def _canned_stream(*, messages, max_tokens=None):
    yield "Quarterly — every 11 weeks.", {}
    yield "", {
        "model_id": "meta-llama/llama-3.2-3b-instruct:free",
        "prompt_tokens": 40,
        "completion_tokens": 7,
        "latency_ms": 13,
        "completion_text": "Quarterly — every 11 weeks.",
    }


def _question():
    return {
        "id": "know-001",
        "role": "admin",
        "category": "policy_recall",
        "prompt": "How often are module templates imported?",
        "gold": "Quarterly, every 11 weeks.",
        "accept_set": None,
        "required_tools": None,
        "notes": "",
    }


def test_replay_grounded_populates_retrieved_context(tmp_path, monkeypatch):
    from app.eval import replay
    from app.copilot import llm as copilot_llm

    monkeypatch.setattr(copilot_llm, "stream_completion", _canned_stream)

    def _fake_retrieve(db, query_text):
        assert query_text == "How often are module templates imported?"
        return [_one_citation()], 21, 33  # citations, retrieval_ms, rerank_ms

    out_dir = tmp_path / "results"
    trace_path = replay.replay_grounded(
        model_id="meta-llama/llama-3.2-3b-instruct:free",
        question=_question(),
        db=object(),
        out_dir=out_dir,
        retrieve=_fake_retrieve,
        monkeypatch=monkeypatch,
    )
    payload = json.loads(trace_path.read_text())

    assert payload["outcome"] == "ok"
    assert payload["final_answer"] == "Quarterly — every 11 weeks."
    # the whole point: retrieved_context is non-empty with snippet entries
    rc = payload["retrieved_context"]
    assert len(rc) == 1
    assert rc[0]["snippet"].startswith("Module templates are imported quarterly")
    assert rc[0]["source_path"] == "CLAUDE.md"
    # retrieval latencies are recorded for the methods section
    assert payload["usage"]["retrieval_ms"] == 21
    assert payload["usage"]["rerank_ms"] == 33


def test_replay_grounded_participant_role_uses_base_prompt(tmp_path, monkeypatch):
    """Participant-role questions must NOT crash.

    Regression for Phase 35-03: production blocks the participant role at the
    router, so ``prompts.system_prompt_for`` defines no template for it and
    raised ``ValueError``. The grounded eval still asks participant-role
    knowledge/refusal questions, so the driver falls back to the neutral
    ``_BASE`` prompt + retrieved-context block instead of crashing. Before the
    fix every participant question landed as ``hard_failure`` / empty answer.
    """
    from app.eval import replay
    from app.copilot import llm as copilot_llm

    monkeypatch.setattr(copilot_llm, "stream_completion", _canned_stream)

    q = _question()
    q["id"] = "know-participant-001"
    q["role"] = "participant"

    def _fake_retrieve(db, query_text):
        return [_one_citation()], 21, 33

    out_dir = tmp_path / "results"
    trace_path = replay.replay_grounded(
        model_id="x:free",
        question=q,
        db=object(),
        out_dir=out_dir,
        retrieve=_fake_retrieve,
        monkeypatch=monkeypatch,
    )
    payload = json.loads(trace_path.read_text())

    assert payload["outcome"] == "ok"
    assert payload["final_answer"] == "Quarterly — every 11 weeks."
    # base prompt is present (hard rules) without an admin/organizer role tail
    system = payload["messages"][0]["content"]
    assert "SciTrek Copilot" in system
    assert "speaking with an admin" not in system
    assert "speaking with an event organizer" not in system
    # grounding block still appended
    assert "retrieved_context" in system or payload["retrieved_context"]


def test_replay_grounded_empty_citations_degrades_gracefully(tmp_path, monkeypatch):
    """No citations (retrieval miss) → still completes, retrieved_context empty."""
    from app.eval import replay
    from app.copilot import llm as copilot_llm

    monkeypatch.setattr(copilot_llm, "stream_completion", _canned_stream)

    def _no_hits(db, query_text):
        return [], 5, 0

    out_dir = tmp_path / "results"
    trace_path = replay.replay_grounded(
        model_id="x:free",
        question=_question(),
        db=object(),
        out_dir=out_dir,
        retrieve=_no_hits,
        monkeypatch=monkeypatch,
    )
    payload = json.loads(trace_path.read_text())
    assert payload["outcome"] == "ok"
    assert payload["retrieved_context"] == []


def test_replay_grounded_retrieval_failure_is_hard_failure(tmp_path, monkeypatch):
    """An exception in retrieval is captured as hard_failure, not a crash."""
    from app.eval import replay

    def _boom(db, query_text):
        raise RuntimeError("pgvector op-class missing")

    out_dir = tmp_path / "results"
    trace_path = replay.replay_grounded(
        model_id="x:free",
        question=_question(),
        db=object(),
        out_dir=out_dir,
        retrieve=_boom,
        monkeypatch=monkeypatch,
    )
    payload = json.loads(trace_path.read_text())
    assert payload["outcome"] == "hard_failure"
    assert "RuntimeError" in payload.get("error_class", "")
