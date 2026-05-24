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
) -> Path:
    """Replay one question against one model. Returns the trace path."""
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
        "eval_replay_started model=%s question_id=%s", model_id, question["id"]
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


__all__ = ["replay_one", "_model_slug"]
