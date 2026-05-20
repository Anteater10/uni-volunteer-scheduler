"""Plan 32-07 — offline RAGAS harness producing the v1.4 "rerank lift" figure.

Runs the Phase 32 retrieval pipeline **twice** over the frozen 30-question
testset — once with the Plan 32-03 cross-encoder reranker ON, once with
it OFF — and reports the lift on three RAGAS metrics (``faithfulness``,
``answer_relevancy``, ``context_relevancy``). Output is the paper figure:

* ``docs/documentation/32-rag-retrieval/rerank-lift.csv`` — locked schema
  ``metric,rerank_off,rerank_on,lift`` (the paper LaTeX imports it
  verbatim; do not rename columns).
* ``docs/documentation/32-rag-retrieval/rerank-lift.png`` — matplotlib
  bar chart, two bars per metric, error bars from ``--repeats`` runs.

OFFLINE ONLY
------------
This script lives in ``scripts/`` and is **never** imported by ``app/``.
CI does not install ``backend/requirements-eval.txt`` and does not run
this harness — only the import-shape smoke test
(``backend/tests/test_eval_script_smoke.py``) ships in CI.

Reproducibility
---------------
1. ``pip install -r backend/requirements-eval.txt``  (ragas==0.4.3 pinned)
2. ``export OPENAI_BASE_URL=https://openrouter.ai/api/v1``
3. ``export OPENAI_API_KEY=$OPENROUTER_API_KEY``
4. Postgres + the Phase 31 corpus must be live; docker compose up.
5. ``python scripts/eval_rerank_lift.py --repeats 3``

Wall-time budget: ~20–40 min on OpenRouter free tier for 30 × 2 × 3
runs (Pitfall 4 in RESEARCH — ragas calls the judge LLM ~5–6× per
row; we batch and sleep between rounds).

Variance bars
-------------
RAGAS 0.4.3 LLM-judge scores are non-deterministic by ~±0.03 even at
temperature 0 (RESEARCH §A4). We run each condition ``--repeats`` times
(default 3) and report mean ± stdev. The PNG carries error bars; the
CSV reports the mean.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Paths (locked — paper LaTeX references these).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTSET_PATH = _REPO_ROOT / "docs/documentation/32-rag-retrieval/eval/testset.json"
_CSV_PATH = _REPO_ROOT / "docs/documentation/32-rag-retrieval/rerank-lift.csv"
_PNG_PATH = _REPO_ROOT / "docs/documentation/32-rag-retrieval/rerank-lift.png"
_LOCKED_HEADER = ["metric", "rerank_off", "rerank_on", "lift"]
_METRICS = ["faithfulness", "answer_relevancy", "context_relevancy"]


# Make `from app.copilot.*` resolve when running from repo root.
sys.path.insert(0, str(_REPO_ROOT / "backend"))


# ---------------------------------------------------------------------------
# Pipeline glue. Imports stay lazy so `--help` works without the eval venv.
# ---------------------------------------------------------------------------
@dataclass
class PipelineConfig:
    rerank_on: bool
    top_k: int = 5


def _pipeline_answer(
    db, query: str, *, cfg: PipelineConfig
) -> tuple[str, list[str]]:
    """Run embed → hybrid → (rerank?) → completion. Returns (answer, contexts).

    Mirrors the production ``app.copilot.router._run_retrieval`` flow but
    swaps the reranker stage for a no-op when ``cfg.rerank_on`` is False.
    The LLM call uses ``stream_completion_blocking`` (added by Plan 32-04
    Task 2b specifically for this harness — see RESEARCH §Code Examples
    and ``backend/app/copilot/llm.py`` docstring).
    """
    # Local imports inside the function so that `python scripts/eval_rerank_lift.py --help`
    # doesn't require the backend stack to be importable.
    from app.copilot.retrieval import hybrid_search, rerank  # type: ignore
    from app.copilot.llm import stream_completion_blocking  # type: ignore
    from app.corpus.embeddings import get_primary_and_fallback  # type: ignore

    provider, _ = get_primary_and_fallback()
    provider_name = getattr(provider, "name", "local-bge")
    vecs, _meta = provider.embed([query])
    qvec = vecs[0]

    hits = hybrid_search(
        db,
        query_text=query,
        query_embedding=qvec,
        provider=provider_name,
        top_n=20,
    )
    candidates = [
        {
            "id": h.id,
            "document_id": h.document_id,
            "content": h.content,
            "char_start": h.char_start,
            "char_end": h.char_end,
            "rrf_score": h.rrf_score,
        }
        for h in hits
    ]
    if cfg.rerank_on and candidates:
        selected = rerank(query, candidates, top_k=cfg.top_k)
    else:
        # Rerank-OFF arm: top-K from RRF directly (no cross-encoder).
        selected = candidates[: cfg.top_k]

    contexts = [c["content"] for c in selected]

    # Build a minimal system prompt for the eval — we deliberately keep
    # this short so the judge measures retrieval quality, not prompt
    # engineering. The real prompt lives in app.copilot.prompts and is
    # measured separately in Plan 32-08.
    system_prompt = (
        "You are an assistant for the SciTrek volunteer scheduler. Answer "
        "the user's question using ONLY the retrieved context. If the "
        "context does not contain the answer, say so plainly."
    )
    context_block = "\n\n".join(
        f"[{i + 1}] {c}" for i, c in enumerate(contexts)
    )
    user_msg = f"{query}\n\n<retrieved_context>\n{context_block}\n</retrieved_context>"

    answer = stream_completion_blocking(
        messages=[{"role": "user", "content": user_msg}],
        system_prompt=system_prompt,
        max_tokens=512,
    )
    return answer, contexts


def _load_testset() -> list[dict]:
    """Load the frozen testset, skipping the metadata header object."""
    with _TESTSET_PATH.open() as fh:
        raw = json.load(fh)
    items = [
        x
        for x in raw
        if isinstance(x, dict) and not x.get("_section")
    ]
    # Drop placeholder rows so a partial-state run still produces a real figure.
    items = [
        x
        for x in items
        if not (
            x.get("question", "").startswith(("TODO", "PLACEHOLDER"))
            or x.get("ground_truth", "").startswith(("TODO", "PLACEHOLDER"))
        )
    ]
    return items


# ---------------------------------------------------------------------------
# RAGAS evaluation.
# ---------------------------------------------------------------------------
def _evaluate_with_ragas(records: list[dict]) -> dict[str, float]:
    """Call RAGAS over an in-memory dataset; return mean per-metric scores."""
    from datasets import Dataset  # type: ignore
    from ragas import evaluate  # type: ignore
    from ragas.metrics import (  # type: ignore
        answer_relevancy,
        context_relevancy,
        faithfulness,
    )

    ds = Dataset.from_list(records)
    result = evaluate(
        ds, metrics=[faithfulness, answer_relevancy, context_relevancy]
    )
    df = result.to_pandas()
    return {m: float(df[m].mean()) for m in _METRICS}


# ---------------------------------------------------------------------------
# Run loop.
# ---------------------------------------------------------------------------
def run(rerank_on: bool, *, repeats: int = 3, limit: int | None = None) -> dict[str, list[float]]:
    """Run ``repeats`` evaluations and return per-metric score lists.

    The same testset is reused across repeats — variance comes from the
    LLM judge, not from question sampling. This isolates RAGAS-judge
    noise (RESEARCH §A4 mitigation).
    """
    from app.db import SessionLocal  # type: ignore

    testset = _load_testset()
    if limit:
        testset = testset[:limit]

    cfg = PipelineConfig(rerank_on=rerank_on)
    scores: dict[str, list[float]] = {m: [] for m in _METRICS}

    for rep in range(repeats):
        records: list[dict] = []
        db = SessionLocal()
        try:
            for item in testset:
                answer, contexts = _pipeline_answer(db, item["question"], cfg=cfg)
                records.append(
                    {
                        "question": item["question"],
                        "answer": answer,
                        "contexts": contexts,
                        "ground_truth": item["ground_truth"],
                    }
                )
        finally:
            db.close()

        round_scores = _evaluate_with_ragas(records)
        for m in _METRICS:
            scores[m].append(round_scores[m])
        # Pitfall 4: breathe between repeats to stay under OpenRouter caps.
        if rep < repeats - 1:
            time.sleep(5)

    return scores


# ---------------------------------------------------------------------------
# Artifact writers.
# ---------------------------------------------------------------------------
def write_csv(off_scores: dict[str, list[float]], on_scores: dict[str, list[float]]) -> None:
    """Emit the locked-shape CSV. Mean across repeats per cell."""
    _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CSV_PATH.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_LOCKED_HEADER)
        for m in _METRICS:
            off = statistics.fmean(off_scores[m]) if off_scores[m] else 0.0
            on = statistics.fmean(on_scores[m]) if on_scores[m] else 0.0
            writer.writerow([m, f"{off:.4f}", f"{on:.4f}", f"{on - off:.4f}"])


def write_png(off_scores: dict[str, list[float]], on_scores: dict[str, list[float]]) -> None:
    """Bar chart with 2 bars per metric and error bars from repeats."""
    import matplotlib.pyplot as plt  # type: ignore
    import numpy as np  # type: ignore

    _PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    metrics = _METRICS
    off_means = [statistics.fmean(off_scores[m]) if off_scores[m] else 0.0 for m in metrics]
    on_means = [statistics.fmean(on_scores[m]) if on_scores[m] else 0.0 for m in metrics]
    off_err = [statistics.pstdev(off_scores[m]) if len(off_scores[m]) > 1 else 0.0 for m in metrics]
    on_err = [statistics.pstdev(on_scores[m]) if len(on_scores[m]) > 1 else 0.0 for m in metrics]

    x = np.arange(len(metrics))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        x - width / 2, off_means, width, yerr=off_err, label="rerank OFF", capsize=4
    )
    ax.bar(
        x + width / 2, on_means, width, yerr=on_err, label="rerank ON", capsize=4
    )
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("RAGAS score (0-1)")
    ax.set_title("Cross-encoder rerank lift — Phase 32 (mean ± stdev over repeats)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(_PNG_PATH, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Subset the testset (debug runs only). Final paper figure uses all 30.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not os.environ.get("OPENAI_API_KEY"):
        # RAGAS reads OPENAI_API_KEY directly; OpenRouter accepts it
        # transparently when OPENAI_BASE_URL points at their endpoint.
        forwarded = os.environ.get("OPENROUTER_API_KEY")
        if forwarded:
            os.environ["OPENAI_API_KEY"] = forwarded
        else:
            print(
                "ERROR: set OPENAI_API_KEY (or OPENROUTER_API_KEY) before running.",
                file=sys.stderr,
            )
            return 2
    os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    print(f"running with rerank=OFF, repeats={args.repeats} …")
    off_scores = run(rerank_on=False, repeats=args.repeats, limit=args.limit)
    print(f"running with rerank=ON,  repeats={args.repeats} …")
    on_scores = run(rerank_on=True, repeats=args.repeats, limit=args.limit)

    write_csv(off_scores, on_scores)
    write_png(off_scores, on_scores)

    print(f"wrote {_CSV_PATH}")
    print(f"wrote {_PNG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
