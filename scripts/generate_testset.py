"""Plan 32-07 Task 2 — synthetic half of the frozen evaluation testset.

Generates the 15 RAGAS-synthetic questions that pair with the 15
hand-curated questions Andy authors by hand. Output is a JSON array of
``{"id", "source", "question", "ground_truth"}`` objects which the main
harness (``scripts/eval_rerank_lift.py``) consumes verbatim.

OFFLINE ONLY — this is not imported by the FastAPI request path. The
``ragas`` package + a live ``OPENAI_API_KEY`` (pointed at OpenRouter via
``OPENAI_BASE_URL``) are required at runtime; pip-installable from
``backend/requirements-eval.txt``.

Free-tier setup
---------------
The default judge model is ``openai/gpt-oss-120b:free`` on OpenRouter
(no paid credit required). The embedder is a *local* sentence-transformers
BGE model (``BAAI/bge-small-en-v1.5``) that the backend container already
caches for the request-path corpus retriever — so the whole testset
generator runs on free resources. Override the judge with
``--judge-model`` or ``RAGAS_JUDGE_MODEL``.

Usage
-----
::

    pip install -r backend/requirements-eval.txt
    export OPENAI_BASE_URL=https://openrouter.ai/api/v1
    export OPENAI_API_KEY=$OPENROUTER_API_KEY
    python scripts/generate_testset.py \\
        --num-synthetic 15 \\
        --judge-model openai/gpt-oss-120b:free \\
        --output docs/documentation/32-rag-retrieval/eval/testset.json

The script *merges* into the output file: it preserves the 15
hand-curated items (those with ``"source": "hand-curated"``) and only
replaces / adds entries whose ``source`` is ``"ragas-testsetgenerator"``.
Re-runs are idempotent in shape: same total of 30 items, same schema.

Pitfall 4 mitigation
--------------------
RAGAS 0.4.3 hits the judge LLM ~6× per generated row. With OpenRouter
free-tier rate caps that means we generate in batches of 5 with a
``time.sleep(10)`` between batches; see ``BATCH_SIZE`` and ``BATCH_SLEEP``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Heavy imports are deferred until inside main() so `--help` works
# without the eval virtualenv.


# Each batch triggers a full default_transforms pass over the corpus
# (Summary/NER/Themes/Embedding extractors fire concurrently and saturate
# OpenRouter free-tier connection limits). Running the whole testset in a
# single batch means only ONE transform pass, which is the cheapest path
# under the free-tier rate caps. BATCH_SLEEP is only used if we ever fall
# back to multi-batch mode.
BATCH_SIZE = 20
BATCH_SLEEP = 30.0  # seconds between batches to stay under OpenRouter caps


def _load_corpus_documents() -> list[dict]:
    """Pull a small sample of ingested corpus docs to feed the generator.

    RAGAS' ``TestsetGenerator.generate_with_langchain_docs`` wants a list
    of ``langchain_core.documents.Document``. We hydrate them from the
    ``corpus_chunks`` table — same content the request path retrieves
    over, so generated questions live in the actual answer-space.
    """
    # Local imports — keep CLI startup cheap.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.database import SessionLocal  # type: ignore
    from sqlalchemy import text as sa_text  # type: ignore

    session = SessionLocal()
    try:
        rows = session.execute(
            sa_text(
                """
                SELECT cc.content, cd.source_path
                FROM corpus_chunks cc
                JOIN corpus_documents cd ON cd.id = cc.document_id
                WHERE cc.embedding_provider = 'local-bge'
                ORDER BY random()
                LIMIT 25
                """
            )
        ).all()
        return [
            {"content": r.content, "source_path": r.source_path} for r in rows
        ]
    finally:
        session.close()


def _generate_synthetic(num: int, judge_model: str | None = None) -> list[dict]:
    """Drive RAGAS 0.4.x TestsetGenerator in batches of ``BATCH_SIZE``.

    RAGAS 0.4 dropped the ``evolutions`` API. The new pipeline is:

        ChatOpenAI -> LangchainLLMWrapper -> TestsetGenerator
            .generate_with_langchain_docs(docs, testset_size=N)

    Internally that runs ``default_transforms`` over a KnowledgeGraph
    and samples from ``default_query_distribution``. The output Testset
    exposes ``samples`` (list of ``TestsetSample``) and ``to_pandas()``
    with columns ``user_input`` and ``reference`` (and ``reference_contexts``).
    We map those into the legacy ``question`` / ``ground_truth`` schema
    that ``_merge`` and the eval harness expect.
    """
    from langchain_core.documents import Document  # type: ignore
    from langchain_openai import ChatOpenAI  # type: ignore
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore
    from ragas.llms import LangchainLLMWrapper  # type: ignore
    from ragas.run_config import RunConfig  # type: ignore
    from ragas.testset import TestsetGenerator  # type: ignore

    # Default judge: openai/gpt-oss-120b:free on OpenRouter — free tier,
    # JSON-friendly, no paid credit required. Override with --judge-model
    # or RAGAS_JUDGE_MODEL.
    judge_model = (
        judge_model
        or os.environ.get("RAGAS_JUDGE_MODEL")
        or "openai/gpt-oss-120b:free"
    )

    # OpenRouter proxies an OpenAI-shaped API for the judge LLM. The
    # embedder is local: sentence-transformers BGE-small is already cached
    # in the backend image (request-path corpus retriever), so the whole
    # generator stays on free resources. Prefer the new
    # ``langchain_huggingface`` package when present; fall back to the
    # community shim otherwise.
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore
    except ImportError:
        from langchain_community.embeddings import (  # type: ignore
            HuggingFaceEmbeddings,
        )

    embed_model = os.environ.get(
        "RAGAS_EMBED_MODEL", "BAAI/bge-small-en-v1.5"
    )

    generator_llm = LangchainLLMWrapper(
        ChatOpenAI(model=judge_model, temperature=0.0)
    )
    generator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name=embed_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    )

    generator = TestsetGenerator(
        llm=generator_llm,
        embedding_model=generator_embeddings,
    )

    corpus = _load_corpus_documents()
    docs = [
        Document(page_content=r["content"], metadata={"source": r["source_path"]})
        for r in corpus
    ]

    out: list[dict] = []
    remaining = num
    while remaining > 0:
        batch = min(BATCH_SIZE, remaining)
        # ``generate_with_langchain_docs`` builds the KG + applies
        # default_transforms internally. Our corpus chunks are short
        # (markdown paragraphs), so we rely on the default single-hop +
        # multi-hop mix from default_query_distribution rather than
        # hand-rolling a synthesizer list.
        # max_workers=2 throttles RAGAS' default_transforms concurrency so
        # OpenRouter free-tier connection caps don't trigger
        # APIConnectionError mid-run. max_retries=15 + max_wait=90 gives
        # tenacity room to back off through transient 429/503s.
        run_config = RunConfig(max_workers=2, max_retries=15, max_wait=90, timeout=300)
        ts = generator.generate_with_langchain_docs(
            docs, testset_size=batch, run_config=run_config
        )
        rows = _extract_rows(ts)
        for row in rows:
            question = str(row.get("user_input") or row.get("question") or "").strip()
            ground_truth = str(
                row.get("reference") or row.get("ground_truth") or ""
            ).strip()
            if not question:
                continue
            out.append(
                {
                    "id": f"synthetic-{len(out) + 1:02d}",
                    "source": "ragas-testsetgenerator",
                    "question": question,
                    "ground_truth": ground_truth,
                }
            )
        remaining -= batch
        if remaining > 0:
            time.sleep(BATCH_SLEEP)
    return out


def _extract_rows(testset) -> list[dict]:
    """Coerce a RAGAS 0.4 Testset into a list[dict].

    Prefer ``.to_pandas()`` because it flattens the SingleTurnSample
    pydantic model into plain columns. Fall back to walking
    ``.samples`` if pandas is unavailable for some reason.
    """
    try:
        df = testset.to_pandas()
        return df.to_dict(orient="records")
    except Exception:
        rows: list[dict] = []
        for sample in getattr(testset, "samples", []):
            # Each sample wraps an ``eval_sample`` (SingleTurnSample) with
            # ``user_input`` / ``reference`` attributes.
            eval_sample = getattr(sample, "eval_sample", sample)
            rows.append(
                {
                    "user_input": getattr(eval_sample, "user_input", ""),
                    "reference": getattr(eval_sample, "reference", ""),
                }
            )
        return rows


def _merge(existing: list[dict], synthetic: list[dict]) -> list[dict]:
    """Preserve metadata + hand-curated items; replace synthetic items."""
    keep = [
        item
        for item in existing
        if isinstance(item, dict)
        and item.get("source") in ("hand-curated", None)
        or (isinstance(item, dict) and item.get("_section"))
    ]
    return keep + synthetic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-synthetic", type=int, default=15)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/documentation/32-rag-retrieval/eval/testset.json"),
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help=(
            "OpenRouter judge model slug (default: openai/gpt-oss-120b:free "
            "or RAGAS_JUDGE_MODEL env var)."
        ),
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "ERROR: set OPENAI_API_KEY (forwarded to OpenRouter via OPENAI_BASE_URL).",
            file=sys.stderr,
        )
        return 2
    os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    existing: list[dict] = []
    if args.output.exists():
        with args.output.open() as fh:
            existing = json.load(fh)

    synthetic = _generate_synthetic(args.num_synthetic, judge_model=args.judge_model)
    merged = _merge(existing, synthetic)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as fh:
        json.dump(merged, fh, indent=2)
    print(f"wrote {len(merged)} items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
