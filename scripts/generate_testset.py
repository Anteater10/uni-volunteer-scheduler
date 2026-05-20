"""Plan 32-07 Task 2 — synthetic half of the frozen evaluation testset.

Generates the 15 RAGAS-synthetic questions that pair with the 15
hand-curated questions Andy authors by hand. Output is a JSON array of
``{"id", "source", "question", "ground_truth"}`` objects which the main
harness (``scripts/eval_rerank_lift.py``) consumes verbatim.

OFFLINE ONLY — this is not imported by the FastAPI request path. The
``ragas`` package + a live ``OPENAI_API_KEY`` (pointed at OpenRouter via
``OPENAI_BASE_URL``) are required at runtime; pip-installable from
``backend/requirements-eval.txt``.

Usage
-----
::

    pip install -r backend/requirements-eval.txt
    export OPENAI_BASE_URL=https://openrouter.ai/api/v1
    export OPENAI_API_KEY=$OPENROUTER_API_KEY
    python scripts/generate_testset.py \\
        --num-synthetic 15 \\
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


BATCH_SIZE = 5
BATCH_SLEEP = 10.0  # seconds between batches to stay under OpenRouter caps


def _load_corpus_documents() -> list[dict]:
    """Pull a small sample of ingested corpus docs to feed the generator.

    RAGAS' ``TestsetGenerator.generate_with_langchain_docs`` wants a list
    of ``langchain_core.documents.Document``. We hydrate them from the
    ``corpus_chunks`` table — same content the request path retrieves
    over, so generated questions live in the actual answer-space.
    """
    # Local imports — keep CLI startup cheap.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.db import SessionLocal  # type: ignore
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
                LIMIT 60
                """
            )
        ).all()
        return [
            {"content": r.content, "source_path": r.source_path} for r in rows
        ]
    finally:
        session.close()


def _generate_synthetic(num: int) -> list[dict]:
    """Drive RAGAS TestsetGenerator in batches of ``BATCH_SIZE``."""
    from datasets import Dataset  # type: ignore  # noqa: F401
    from langchain_core.documents import Document  # type: ignore
    from ragas.testset.generator import TestsetGenerator  # type: ignore
    from ragas.testset.evolutions import simple, multi_context, reasoning  # type: ignore
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # type: ignore

    judge_model = os.environ.get(
        "RAGAS_JUDGE_MODEL", "anthropic/claude-3.5-sonnet"
    )
    embed_model = os.environ.get(
        "RAGAS_EMBED_MODEL", "openai/text-embedding-3-small"
    )

    generator_llm = ChatOpenAI(model=judge_model, temperature=0.0)
    critic_llm = ChatOpenAI(model=judge_model, temperature=0.0)
    embeddings = OpenAIEmbeddings(model=embed_model)

    generator = TestsetGenerator.from_langchain(
        generator_llm=generator_llm,
        critic_llm=critic_llm,
        embeddings=embeddings,
    )

    corpus = _load_corpus_documents()
    docs = [
        Document(page_content=r["content"], metadata={"source": r["source_path"]})
        for r in corpus
    ]

    distributions = {simple: 0.5, reasoning: 0.25, multi_context: 0.25}

    out: list[dict] = []
    remaining = num
    while remaining > 0:
        batch = min(BATCH_SIZE, remaining)
        ts = generator.generate_with_langchain_docs(
            docs, test_size=batch, distributions=distributions
        )
        df = ts.to_pandas()
        for _, row in df.iterrows():
            out.append(
                {
                    "id": f"synthetic-{len(out) + 1:02d}",
                    "source": "ragas-testsetgenerator",
                    "question": str(row.get("question", "")),
                    "ground_truth": str(row.get("ground_truth", "")),
                }
            )
        remaining -= batch
        if remaining > 0:
            time.sleep(BATCH_SLEEP)
    return out


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

    synthetic = _generate_synthetic(args.num_synthetic)
    merged = _merge(existing, synthetic)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as fh:
        json.dump(merged, fh, indent=2)
    print(f"wrote {len(merged)} items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
