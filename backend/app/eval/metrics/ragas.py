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

    Builds a single-row ``datasets.Dataset`` and runs ``ragas.evaluate`` with
    the judge LLM pointed at OpenRouter (``OPENAI_BASE_URL`` /
    ``OPENAI_API_KEY``, judge model = ``RAGAS_JUDGE_MODEL``). Returns the three
    metric floats. Mirrors ``scripts/eval_rerank_lift.py::_evaluate_with_ragas``
    (Phase 32-07), trimmed to one row + the reference-based
    ``context_precision`` (we have ``gold`` here, so the with-reference metric
    applies).

    Skipped in CI because RAGAS isn't installed there.
    """
    import os

    from datasets import Dataset
    from langchain_openai import ChatOpenAI
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        faithfulness,
    )
    from ragas.run_config import RunConfig

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:  # pragma: no cover - fallback for older stacks
        from langchain_community.embeddings import HuggingFaceEmbeddings

    from app.eval.models import RAGAS_JUDGE_MODEL

    # RAGAS reads OPENAI_API_KEY / OPENAI_BASE_URL directly; OpenRouter accepts
    # the key transparently when the base URL points at their endpoint.
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get(
        "OPENROUTER_API_KEY"
    ):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
    os.environ.setdefault(
        "OPENAI_BASE_URL", "https://openrouter.ai/api/v1"
    )

    judge_model = os.environ.get("RAGAS_JUDGE_MODEL", RAGAS_JUDGE_MODEL)
    embed_model = os.environ.get(
        "RAGAS_EMBED_MODEL", "BAAI/bge-small-en-v1.5"
    )
    judge = LangchainLLMWrapper(
        ChatOpenAI(model=judge_model, temperature=0.0)
    )
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name=embed_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    )

    ds = Dataset.from_list(
        [
            {
                "question": question,
                "answer": answer,
                "contexts": list(context),
                "ground_truth": gold,
            }
        ]
    )
    metric_objs = [faithfulness, answer_relevancy, context_precision]
    run_config = RunConfig(
        max_workers=2, max_retries=15, max_wait=90, timeout=300
    )
    result = evaluate(
        ds,
        metrics=metric_objs,
        llm=judge,
        embeddings=embeddings,
        run_config=run_config,
    )
    df = result.to_pandas()

    def _pick(metric_obj, key: str) -> float | None:
        col = getattr(metric_obj, "name", key)
        if col in df.columns:
            val = df[col].iloc[0]
        elif key in df.columns:
            val = df[key].iloc[0]
        else:
            return None
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        return None if f != f else f  # drop NaN

    return {
        "faithfulness": _pick(faithfulness, "faithfulness"),
        "answer_relevancy": _pick(answer_relevancy, "answer_relevancy"),
        "context_precision": _pick(context_precision, "context_precision"),
    }


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
