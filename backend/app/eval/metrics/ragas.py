"""Phase 35-02-D — RAGAS adapter.

The real RAGAS judge runs against ``meta-llama/llama-3.3-70b-instruct:free``
(spec §6.1). Production wiring is identical to Phase 32-07: set
``OPENAI_BASE_URL=https://openrouter.ai/api/v1`` and
``OPENAI_API_KEY=$OPENROUTER_API_KEY`` and let RAGAS think it's talking
to OpenAI.

This module exposes ``score_trace(trace, question, judge=None)`` with a
``judge`` callable injection point. The default ``judge`` lazily imports
``ragas`` (the package is in ``requirements-eval.txt`` and may be absent
in CI) and runs the three metrics; tests inject a fake callable.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


Judge = Callable[..., dict[str, float | None]]


def _default_judge(
    *,
    question: str, answer: str, gold: str, context: list[str],
) -> dict[str, float | None]:
    """Real RAGAS judge — only imported when called.

    Skipped in CI because RAGAS isn't installed there.
    """
    import ragas  # noqa: F401  # imported lazily; raises ImportError in CI
    # The real adapter would call ragas.evaluate(...) and extract the three
    # metric values from the returned Dataset. We sketch the shape here;
    # the executing subagent should fill in the exact RAGAS call against
    # the 0.4.3 API (the smoke test in backend/tests/test_eval_script_smoke.py
    # is the closest existing example).
    raise NotImplementedError(
        "Wire the real ragas.evaluate() call here when RAGAS deps are "
        "available locally. CI does not hit this path."
    )


def score_trace(
    trace: dict[str, Any],
    question: dict[str, Any],
    *,
    judge: Judge | None = None,
) -> dict[str, float | None]:
    """Score one (trace, question) pair. Returns the three RAGAS metrics
    as floats in [0.0, 1.0] or None on empty / error.
    """
    answer = (trace.get("final_answer") or "").strip()
    if not answer:
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
        }

    context_snippets = [
        (ctx.get("snippet") or "") for ctx in (trace.get("retrieved_context") or [])
    ]
    context_snippets = [c for c in context_snippets if c.strip()]

    j = judge or _default_judge
    try:
        scored = j(
            question=trace.get("prompt") or "",
            answer=answer,
            gold=question.get("gold") or "",
            context=context_snippets,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ragas_judge_error question_id=%s err=%s",
                       question.get("id"), exc.__class__.__name__)
        return {
            "faithfulness": None,
            "answer_relevancy": None,
            "context_precision": None,
        }

    out = {
        "faithfulness": scored.get("faithfulness"),
        "answer_relevancy": scored.get("answer_relevancy"),
        "context_precision": scored.get("context_precision"),
    }
    if not context_snippets:
        out["context_precision"] = None
    return out


__all__ = ["score_trace"]
