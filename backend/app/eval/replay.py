"""Phase 35-02-C — replay driver.

One function: ``replay_one(model_id, question, out_dir, monkeypatch=None)``.
Pins both primary + fallback to ``model_id`` (via
``app.eval.models.set_model_for_replay``), calls
``app.copilot.llm.complete`` with the question's prompt, captures the
result + usage + (any) tool-call trace, writes a single per-question JSON
file at ``out_dir/{model_slug}/q-{NNN}.json``.

This module does NOT compute RAGAS — that lives in
``app.eval.metrics.ragas``. Replay leaves the ``ragas`` field as a dict
of nulls so the renderer has a stable shape to fill in later.

This module does NOT do parallelism — that lives in ``app.eval.run``
which dispatches via ``ThreadPoolExecutor`` and feeds replay_one one
question at a time.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from app.copilot import llm as copilot_llm

from .models import set_model_for_replay

logger = logging.getLogger(__name__)


def _model_slug(model_id: str) -> str:
    """Filesystem-safe slug — slashes and colons become dashes."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", model_id)


def replay_one(
    *,
    model_id: str,
    question: dict[str, Any],
    out_dir: Path,
    monkeypatch: Any | None = None,
    use_agent_loop: bool = False,
) -> Path:
    """Replay one question against one model. Returns the trace path.

    When ``use_agent_loop=False`` (default), drive the LLM with
    :func:`app.copilot.llm.complete` — a thin, dependency-free path that
    can be monkeypatched in unit tests via ``stream_completion``.

    When ``use_agent_loop=True``, drive the full agent loop via
    :func:`app.copilot.agent.loop.run_turn`. That path needs a DB session,
    user scope, and retrieval cache — the executing CLI is responsible for
    wiring those in a follow-up. Tests monkeypatch ``run_turn`` so the
    flag is exercised without standing up the full stack.
    """
    set_model_for_replay(model_id, monkeypatch=monkeypatch)
    model_dir = Path(out_dir) / _model_slug(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    trace_path = model_dir / f"q-{question['id']}.json"

    started = time.monotonic()
    payload: dict[str, Any] = {
        "model": model_id,
        "question_id": question["id"],
        "role": question.get("role"),
        "category": question.get("category"),
        "prompt": question["prompt"],
        "final_answer": "",
        "messages": [{"role": "user", "content": question["prompt"]}],
        "tool_calls": [],
        "retrieved_context": [],
        "ragas": {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
        },
        "tool_use_grade": None,
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "latency_ms": None,
        },
        "outcome": "ok",
    }

    logger.info(
        "eval_replay_started model=%s question_id=%s use_agent_loop=%s",
        model_id, question["id"], use_agent_loop,
    )

    if use_agent_loop:
        return _replay_via_agent_loop(
            model_id=model_id,
            question=question,
            payload=payload,
            trace_path=trace_path,
            started=started,
        )

    try:
        text, meta = copilot_llm.complete(
            messages=payload["messages"],
            max_tokens=1024,
        )
    except Exception as exc:  # noqa: BLE001 — wide catch is the spec contract
        payload["outcome"] = "hard_failure"
        payload["error_class"] = exc.__class__.__name__
        payload["error"] = str(exc)
        payload["usage"]["latency_ms"] = int((time.monotonic() - started) * 1000)
        trace_path.write_text(json.dumps(payload, indent=2, default=str))
        logger.info(
            "eval_replay_finished model=%s question_id=%s outcome=%s latency_ms=%s",
            model_id, question["id"], payload["outcome"],
            payload["usage"]["latency_ms"],
        )
        return trace_path

    payload["final_answer"] = text or ""
    payload["usage"] = {
        "prompt_tokens": meta.get("prompt_tokens"),
        "completion_tokens": meta.get("completion_tokens"),
        "latency_ms": meta.get(
            "latency_ms", int((time.monotonic() - started) * 1000)
        ),
    }
    if not (text or "").strip():
        payload["outcome"] = "empty_response"

    trace_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info(
        "eval_replay_finished model=%s question_id=%s outcome=%s "
        "latency_ms=%s prompt_tokens=%s completion_tokens=%s",
        model_id, question["id"], payload["outcome"],
        payload["usage"]["latency_ms"],
        payload["usage"]["prompt_tokens"],
        payload["usage"]["completion_tokens"],
    )
    return trace_path


def _default_retrieve(db, query_text):
    """Production retrieval entry point (Phase 32).

    Lazy import keeps ``app.copilot.router`` (and its FastAPI deps) out of
    the import path for the bare/unit-test code that never touches grounding.
    Returns ``(citations, retrieval_ms, rerank_ms)``.
    """
    from app.copilot.router import _run_retrieval

    return _run_retrieval(db, query_text)


def replay_grounded(
    *,
    model_id: str,
    question: dict[str, Any],
    db: Any,
    out_dir: Path,
    retrieve: Any | None = None,
    monkeypatch: Any | None = None,
) -> Path:
    """Replay one question through the deployed retrieval-grounded path.

    Mirrors ``app.copilot.router._sse_stream`` (the path the deployed copilot
    actually runs — the tool/agent loop is unbuilt): retrieve real corpus
    chunks, append a ``<retrieved_context>`` block to the role system prompt,
    and call :func:`app.copilot.llm.complete`. Unlike the bare 35-02 path,
    this populates ``retrieved_context`` so RAGAS faithfulness /
    context_precision become valid.

    ``retrieve`` is injectable for unit tests; production passes ``None`` and
    the Phase 32 ``_run_retrieval`` is used. Needs a real DB session reaching
    the ingested corpus — the CLI builds one via ``SessionLocal`` and runs
    inside the docker network.
    """
    from app import models
    from app.copilot.prompts import system_prompt_with_context

    set_model_for_replay(model_id, monkeypatch=monkeypatch)
    retrieve = retrieve or _default_retrieve
    model_dir = Path(out_dir) / _model_slug(model_id)
    model_dir.mkdir(parents=True, exist_ok=True)
    trace_path = model_dir / f"q-{question['id']}.json"

    started = time.monotonic()
    payload: dict[str, Any] = {
        "model": model_id,
        "question_id": question["id"],
        "role": question.get("role"),
        "category": question.get("category"),
        "prompt": question["prompt"],
        "final_answer": "",
        "messages": [],
        "tool_calls": [],
        "retrieved_context": [],
        "ragas": {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
        },
        "tool_use_grade": None,
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "latency_ms": None,
            "retrieval_ms": None,
            "rerank_ms": None,
        },
        "grounded": True,
        "outcome": "ok",
    }

    logger.info(
        "eval_grounded_started model=%s question_id=%s", model_id, question["id"]
    )

    try:
        citations, retrieval_ms, rerank_ms = retrieve(db, question["prompt"])
        payload["usage"]["retrieval_ms"] = retrieval_ms
        payload["usage"]["rerank_ms"] = rerank_ms
        payload["retrieved_context"] = [
            {
                "chunk_id": str(getattr(c, "chunk_id", "")),
                "source_path": getattr(c, "source_path", None),
                "char_start": getattr(c, "char_start", None),
                "char_end": getattr(c, "char_end", None),
                "snippet": getattr(c, "quote", "") or "",
            }
            for c in (citations or [])
        ]

        try:
            role = models.UserRole(question.get("role"))
        except (ValueError, KeyError):
            role = models.UserRole.participant
        system = system_prompt_with_context(role, citations or [])
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question["prompt"]},
        ]
        payload["messages"] = messages

        text, meta = copilot_llm.complete(messages=messages, max_tokens=1024)
    except Exception as exc:  # noqa: BLE001 — spec contract: never crash a run
        payload["outcome"] = "hard_failure"
        payload["error_class"] = exc.__class__.__name__
        payload["error"] = str(exc)
        payload["usage"]["latency_ms"] = int((time.monotonic() - started) * 1000)
        trace_path.write_text(json.dumps(payload, indent=2, default=str))
        logger.info(
            "eval_grounded_finished model=%s question_id=%s outcome=%s",
            model_id, question["id"], payload["outcome"],
        )
        return trace_path

    payload["final_answer"] = text or ""
    payload["usage"]["prompt_tokens"] = meta.get("prompt_tokens")
    payload["usage"]["completion_tokens"] = meta.get("completion_tokens")
    payload["usage"]["latency_ms"] = meta.get(
        "latency_ms", int((time.monotonic() - started) * 1000)
    )
    if not (text or "").strip():
        payload["outcome"] = "empty_response"

    trace_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info(
        "eval_grounded_finished model=%s question_id=%s outcome=%s "
        "n_citations=%s latency_ms=%s",
        model_id, question["id"], payload["outcome"],
        len(payload["retrieved_context"]), payload["usage"]["latency_ms"],
    )
    return trace_path


def _replay_via_agent_loop(
    *,
    model_id: str,
    question: dict[str, Any],
    payload: dict[str, Any],
    trace_path: Path,
    started: float,
) -> Path:
    """Drive the full agent loop for one question.

    Test paths monkeypatch ``app.copilot.agent.loop.run_turn`` to a stub
    that returns an object with ``final_answer``, ``tool_calls``,
    ``retrieved_context``, ``usage`` attributes. Real CLI invocation with
    this flag set still needs DB / scope plumbing — that wiring lives in a
    follow-up task. We pass placeholder kwargs and surface any exception
    as a ``hard_failure`` outcome so the harness can keep moving.
    """
    try:
        from app.copilot.agent import loop as agent_loop  # noqa: WPS433

        result = agent_loop.run_turn(
            db=None,
            llm=None,
            scope=None,
            session_id=None,
            user_message=question["prompt"],
            retrieval_context="",
            model=model_id,
        )
        payload["final_answer"] = (
            getattr(result, "final_answer", "") or ""
        )
        payload["tool_calls"] = [
            {
                "name": getattr(tc, "name", None),
                "args": getattr(tc, "args", None),
                "result_preview": (
                    str(getattr(tc, "result_preview", ""))[:200]
                    if hasattr(tc, "result_preview")
                    else None
                ),
            }
            for tc in (getattr(result, "tool_calls", []) or [])
        ]
        payload["retrieved_context"] = [
            {
                "doc_id": getattr(ctx, "doc_id", None),
                "snippet": (getattr(ctx, "snippet", "") or "")[:300],
            }
            for ctx in (getattr(result, "retrieved_context", []) or [])
        ]
        payload["usage"] = dict(getattr(result, "usage", {}) or {})
        if not (payload["final_answer"] or "").strip():
            payload["outcome"] = "empty_response"
    except Exception as exc:  # noqa: BLE001
        payload["outcome"] = "hard_failure"
        payload["error_class"] = exc.__class__.__name__
        payload["error"] = str(exc)
        payload["usage"]["latency_ms"] = int(
            (time.monotonic() - started) * 1000
        )

    trace_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info(
        "eval_replay_finished model=%s question_id=%s outcome=%s "
        "agent_loop=1",
        model_id, question["id"], payload["outcome"],
    )
    return trace_path


__all__ = ["replay_one", "replay_grounded", "_model_slug"]
