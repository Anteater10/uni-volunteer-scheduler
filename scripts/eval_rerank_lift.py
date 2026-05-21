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

# Checkpoint paths — resumable eval state (see Plan 32-07 Task 3 resilience).
_CHECKPOINT_DIR = _REPO_ROOT / "docs/documentation/32-rag-retrieval/eval/.eval-checkpoint"
_ANSWERS_PATH = _CHECKPOINT_DIR / "answers.jsonl"
_SCORES_PATH = _CHECKPOINT_DIR / "scores.json"


# ---------------------------------------------------------------------------
# Checkpoint helpers — keep on-disk state so a 2-hour crash loses minutes.
# ---------------------------------------------------------------------------
def _checkpoint_dir() -> Path:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR


def _load_answer_checkpoint() -> dict[tuple, dict]:
    """Return ``{(rerank_on, repeat, question_id): record}`` from the JSONL log.

    Tolerates partial last lines (a crash mid-write); silently skips junk.
    """
    out: dict[tuple, dict] = {}
    if not _ANSWERS_PATH.exists():
        return out
    with _ANSWERS_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (
                bool(rec.get("rerank_on")),
                int(rec.get("repeat", 0)),
                str(rec.get("question_id", "")),
            )
            out[key] = rec
    return out


def _append_answer(record: dict) -> None:
    """Append a record to answers.jsonl + fsync so a crash doesn't corrupt."""
    _checkpoint_dir()
    with _ANSWERS_PATH.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _load_scores_checkpoint() -> dict[str, dict]:
    if not _SCORES_PATH.exists():
        return {}
    try:
        with _SCORES_PATH.open() as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_scores_checkpoint(scores: dict[str, dict]) -> None:
    _checkpoint_dir()
    tmp = _SCORES_PATH.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(scores, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(_SCORES_PATH)


def _reset_checkpoint() -> None:
    import shutil

    if _CHECKPOINT_DIR.exists():
        shutil.rmtree(_CHECKPOINT_DIR)


# ---------------------------------------------------------------------------
# Resilience helpers (eval-only — keeps production llm.py untouched).
# OpenRouter free tier occasionally drops streaming connections mid-response;
# the eval should not abort because of one flaky question.
# ---------------------------------------------------------------------------
def _transient_stream_exceptions() -> tuple[type[BaseException], ...]:
    """Lazily resolve the connection-class exceptions we treat as retryable.

    Lazy so ``--help`` works without httpx/openai installed.
    """
    excs: list[type[BaseException]] = []
    try:
        import httpx  # type: ignore

        excs.extend(
            [
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.ConnectTimeout,
            ]
        )
    except Exception:
        pass
    try:
        import openai  # type: ignore

        excs.extend([openai.APIConnectionError, openai.APITimeoutError])
    except Exception:
        pass
    if not excs:
        # Fallback so the except clause is still legal.
        excs.append(ConnectionError)
    return tuple(excs)


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
def _make_judge_and_embeddings():
    """Build the free-tier judge LLM + local BGE embedder for RAGAS.

    Mirrors ``scripts/generate_testset.py``: OpenRouter-routed
    ``openai/gpt-oss-120b:free`` for the judge (no paid credit) and the
    locally-cached ``BAAI/bge-small-en-v1.5`` sentence-transformer for
    embeddings used by metrics like answer_relevancy.
    """
    import os as _os
    from langchain_openai import ChatOpenAI  # type: ignore
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore
    from ragas.llms import LangchainLLMWrapper  # type: ignore

    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore
    except ImportError:
        from langchain_community.embeddings import (  # type: ignore
            HuggingFaceEmbeddings,
        )

    judge_model = _os.environ.get(
        "RAGAS_JUDGE_MODEL", "openai/gpt-oss-120b:free"
    )
    embed_model = _os.environ.get(
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
    return judge, embeddings


def _evaluate_with_ragas(records: list[dict]) -> dict[str, float]:
    """Call RAGAS over an in-memory dataset; return mean per-metric scores.

    Metric-name note: RAGAS 0.4.3 removed the legacy ``context_relevancy``
    metric. The closest semantic equivalent is
    ``LLMContextPrecisionWithoutReference`` (judges whether each retrieved
    context is relevant to the question, without needing a reference
    answer). We store its score under the locked CSV column
    ``context_relevancy`` to keep the paper LaTeX header stable.
    """
    from datasets import Dataset  # type: ignore
    from ragas import evaluate  # type: ignore
    from ragas.run_config import RunConfig  # type: ignore
    from ragas.metrics import (  # type: ignore
        answer_relevancy,
        faithfulness,
        LLMContextPrecisionWithoutReference,
    )

    context_precision_metric = LLMContextPrecisionWithoutReference()
    metric_objs = [faithfulness, answer_relevancy, context_precision_metric]

    # Map CSV column name -> dataframe column name produced by RAGAS.
    # RAGAS uses ``metric.name`` as the dataframe column header.
    column_map = {
        "faithfulness": getattr(faithfulness, "name", "faithfulness"),
        "answer_relevancy": getattr(answer_relevancy, "name", "answer_relevancy"),
        "context_relevancy": getattr(
            context_precision_metric, "name", "llm_context_precision_without_reference"
        ),
    }

    judge, embeddings = _make_judge_and_embeddings()
    ds = Dataset.from_list(records)
    run_config = RunConfig(max_workers=2, max_retries=15, max_wait=90, timeout=300)
    transient = _transient_stream_exceptions()
    try:
        result = evaluate(
            ds,
            metrics=metric_objs,
            llm=judge,
            embeddings=embeddings,
            run_config=run_config,
        )
    except transient as exc:  # type: ignore[misc]
        print(
            f"[retry] RAGAS evaluate() raised {type(exc).__name__}: {exc} — "
            f"sleeping 30s then retrying once",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(30)
        try:
            result = evaluate(
                ds,
                metrics=metric_objs,
                llm=judge,
                embeddings=embeddings,
                run_config=run_config,
            )
        except transient as exc2:  # type: ignore[misc]
            print(
                f"[give-up] RAGAS evaluate() failed twice "
                f"({type(exc2).__name__}: {exc2}); re-raising so the outer "
                f"loop can resume from checkpoint next run.",
                file=sys.stderr,
                flush=True,
            )
            raise
    df = result.to_pandas()
    out: dict[str, float] = {}
    for csv_col, df_col in column_map.items():
        if df_col in df.columns:
            out[csv_col] = float(df[df_col].mean())
        else:
            # Fallback: try the locked CSV name itself, else NaN.
            if csv_col in df.columns:
                out[csv_col] = float(df[csv_col].mean())
            else:
                out[csv_col] = float("nan")
    return out


# ---------------------------------------------------------------------------
# Run loop.
# ---------------------------------------------------------------------------
def run(
    rerank_on: bool,
    *,
    repeats: int = 3,
    limit: int | None = None,
    answer_checkpoint: dict[tuple, dict] | None = None,
    scores_checkpoint: dict[str, dict] | None = None,
    progress: dict | None = None,
) -> dict[str, list[float]]:
    """Run ``repeats`` evaluations and return per-metric score lists.

    The same testset is reused across repeats — variance comes from the
    LLM judge, not from question sampling. This isolates RAGAS-judge
    noise (RESEARCH §A4 mitigation).
    """
    from app.database import SessionLocal  # type: ignore

    testset = _load_testset()
    if limit:
        testset = testset[:limit]

    cfg = PipelineConfig(rerank_on=rerank_on)
    scores: dict[str, list[float]] = {m: [] for m in _METRICS}

    answer_ckpt = answer_checkpoint if answer_checkpoint is not None else _load_answer_checkpoint()
    scores_ckpt = scores_checkpoint if scores_checkpoint is not None else _load_scores_checkpoint()
    progress = progress if progress is not None else {"answer_done": 0, "answer_total": 0}

    for rep in range(repeats):
        round_key = f"{rerank_on}-{rep}"
        cached_round = scores_ckpt.get(round_key)

        records: list[dict] = []
        # We still need records (for question/answer/contexts/ground_truth)
        # even when the round is cached, because future code may want them.
        # But if the round is cached, we don't have to RUN the pipeline for
        # any missing answer — we just use the cached score.
        # To keep things simple: if round is cached, skip building records.
        if cached_round is not None:
            print(
                f"[skip] round cached (rerank={'ON' if rerank_on else 'OFF'} "
                f"rep={rep}): {cached_round}",
                flush=True,
            )
            for m in _METRICS:
                scores[m].append(float(cached_round.get(m, float("nan"))))
            continue

        db = SessionLocal()
        try:
            transient = _transient_stream_exceptions()
            backoffs = [5, 10, 20, 40, 80]  # 5 attempts → up to ~2.5 min/question
            for idx, item in enumerate(testset):
                qid = item.get("id", f"q-{idx:04d}")
                key = (bool(rerank_on), int(rep), str(qid))
                progress["answer_done"] = progress.get("answer_done", 0) + 1

                cached = answer_ckpt.get(key)
                if cached is not None:
                    records.append(
                        {
                            "question": cached.get("question", item["question"]),
                            "answer": cached.get("answer", ""),
                            "contexts": cached.get("contexts", []),
                            "ground_truth": cached.get(
                                "ground_truth", item["ground_truth"]
                            ),
                        }
                    )
                    continue

                answer: str = ""
                contexts: list[str] = []
                last_err: BaseException | None = None
                failed = False
                for attempt in range(len(backoffs)):
                    try:
                        answer, contexts = _pipeline_answer(
                            db, item["question"], cfg=cfg
                        )
                        last_err = None
                        break
                    except transient as exc:  # type: ignore[misc]
                        last_err = exc
                        wait = backoffs[attempt]
                        print(
                            f"[retry] rerank={'ON' if rerank_on else 'OFF'} "
                            f"rep={rep} q={qid} attempt={attempt + 1}/"
                            f"{len(backoffs)} err={type(exc).__name__}: {exc} — "
                            f"sleeping {wait}s",
                            file=sys.stderr,
                            flush=True,
                        )
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        time.sleep(wait)
                if last_err is not None:
                    failed = True
                    print(
                        f"[give-up] rerank={'ON' if rerank_on else 'OFF'} "
                        f"rep={rep} q={qid} — substituting placeholder answer "
                        f"after {len(backoffs)} attempts. last_err="
                        f"{type(last_err).__name__}: {last_err}",
                        file=sys.stderr,
                        flush=True,
                    )

                record = {
                    "question": item["question"],
                    "answer": answer,
                    "contexts": contexts,
                    "ground_truth": item["ground_truth"],
                }
                # Persist to checkpoint immediately so we don't redo this work.
                ckpt_line = {
                    "rerank_on": bool(rerank_on),
                    "repeat": int(rep),
                    "question_id": str(qid),
                    **record,
                }
                if failed:
                    ckpt_line["failed"] = True
                _append_answer(ckpt_line)
                answer_ckpt[key] = ckpt_line
                records.append(record)

                done = progress.get("answer_done", 0)
                total = progress.get("answer_total", 0)
                print(
                    f"answer {done}/{total} (rerank="
                    f"{'ON' if rerank_on else 'OFF'} rep={rep} q={qid})",
                    flush=True,
                )
        finally:
            db.close()

        round_scores = _evaluate_with_ragas(records)
        for m in _METRICS:
            scores[m].append(round_scores[m])
        scores_ckpt[round_key] = {m: round_scores[m] for m in _METRICS}
        _save_scores_checkpoint(scores_ckpt)
        progress["rounds_done"] = progress.get("rounds_done", 0) + 1
        print(
            f"round {progress.get('rounds_done', 0)}/"
            f"{progress.get('rounds_total', 0)} done (rerank="
            f"{'ON' if rerank_on else 'OFF'} rep={rep}): "
            + " ".join(f"{m}={round_scores[m]:.4f}" for m in _METRICS),
            flush=True,
        )
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
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Nuke .eval-checkpoint/ before starting (clean re-run).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.reset_checkpoint:
        _reset_checkpoint()
        print("reset checkpoint: .eval-checkpoint/ cleared", flush=True)

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

    # Shared checkpoint state across both arms — gives us an accurate
    # resume summary and joint progress counters.
    testset_for_count = _load_testset()
    if args.limit:
        testset_for_count = testset_for_count[: args.limit]
    n_questions = len(testset_for_count)
    total_answers = n_questions * 2 * args.repeats  # 2 conditions
    total_rounds = 2 * args.repeats

    answer_ckpt = _load_answer_checkpoint()
    scores_ckpt = _load_scores_checkpoint()
    if answer_ckpt or scores_ckpt:
        print(
            f"resuming from checkpoint: {len(answer_ckpt)}/{total_answers} "
            f"answers, {len(scores_ckpt)}/{total_rounds} rounds complete",
            flush=True,
        )
    else:
        print("starting fresh", flush=True)

    progress = {
        "answer_done": 0,
        "answer_total": total_answers,
        "rounds_done": len(scores_ckpt),
        "rounds_total": total_rounds,
    }

    print(f"running with rerank=OFF, repeats={args.repeats} …")
    off_scores = run(
        rerank_on=False,
        repeats=args.repeats,
        limit=args.limit,
        answer_checkpoint=answer_ckpt,
        scores_checkpoint=scores_ckpt,
        progress=progress,
    )
    print(f"running with rerank=ON,  repeats={args.repeats} …")
    on_scores = run(
        rerank_on=True,
        repeats=args.repeats,
        limit=args.limit,
        answer_checkpoint=answer_ckpt,
        scores_checkpoint=scores_ckpt,
        progress=progress,
    )

    write_csv(off_scores, on_scores)
    write_png(off_scores, on_scores)

    print(f"wrote {_CSV_PATH}")
    print(f"wrote {_PNG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
