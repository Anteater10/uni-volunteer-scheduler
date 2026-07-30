"""CLI entry for corpus ingestion (Phase 31, plan 04).

Canonical invocation (inside the compose network)::

    docker run --rm --network uni-event-scheduler_default --env-file backend/.env \
      -v $PWD/backend:/app -v $PWD/docs:/repo/docs:ro -w /app \
      uni-event-scheduler-backend \
      python -m app.corpus.ingest --source /repo --commit --rebuild
    # then, once, to (re)create the vector index:
    #   ... python -m app.corpus.ingest --build-index

``--source`` must be the **repo root**, not ``docs/``: :data:`SOURCE_GLOBS_V1`
matches ``docs/knowledge-base/**/*.md`` relative to the root you pass, so a
root of ``docs/`` matches nothing. The walker reports ``files_scanned: 0`` and
``status: "succeeded"`` in that case, which reads as a successful no-op — so
always check ``files_ingested`` rather than the exit code.

``docker compose run --rm backend`` cannot ingest at all: the ``backend``
service declares no volumes, so ``docs/`` is not present in the image. Hence
the explicit ``docker run`` with the repo mounted above.

Prefer ``--rebuild`` when re-ingesting changed files. Without it,
``_persist_document`` inserts a fresh document/chunk set while the previous
rows for that ``source_path`` remain, and retrieval has no latest-per-path
filter — so stale and corrected text stay retrievable side by side.

Two module paths reach the same ``main()`` function:

* ``python -m app.corpus`` — Python loads this file directly because it's
  named ``__main__.py``.
* ``python -m app.corpus.ingest`` — :mod:`app.corpus.ingest` re-exports
  ``main`` and runs it via its own ``if __name__ == "__main__"`` guard.

Both are documented in the plan so contributors can pick whichever feels
natural. The argparse parser is shared.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    """Return the shared argparse parser used by both entry points.

    Factored out so tests can call ``main(["--help"])`` without spawning
    a subprocess and so :mod:`app.corpus.ingest`'s ``__name__ ==
    "__main__"`` guard can reuse the exact same surface.
    """
    p = argparse.ArgumentParser(prog="python -m app.corpus.ingest")
    p.add_argument(
        "--source",
        type=Path,
        default=Path("."),
        help="root directory to walk (default: cwd)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--commit", action="store_true", help="write to DB (default if neither flag set)"
    )
    mode.add_argument(
        "--dry-run", action="store_true", help="walk + chunk + hash, no DB writes"
    )
    p.add_argument(
        "--provider",
        choices=["jina", "local"],
        default=None,
        help="override settings.corpus_embedding_primary",
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="TRUNCATE corpus_chunks + corpus_documents before this run",
    )
    p.add_argument(
        "--build-index",
        action="store_true",
        help="CREATE INDEX … USING hnsw (idempotent); skips ingestion",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Argparse → run_ingestion or build_hnsw_index → JSON to stdout.

    Returns an int exit code suitable for ``sys.exit``: ``0`` on
    ``succeeded`` / ``partial``, ``1`` on ``failed``.
    """
    # Local imports so ``--help`` works even if optional deps aren't installed.
    from app.config import settings
    from app.corpus.embeddings import (
        JinaEmbeddingProvider,
        LocalBgeEmbeddingProvider,
    )
    from app.corpus.ingest import build_hnsw_index, run_ingestion
    from app.database import SessionLocal

    args = _build_parser().parse_args(argv)
    session = SessionLocal()
    try:
        if args.build_index:
            build_hnsw_index(session=session)
            print("HNSW index ensured.")
            return 0

        provider_name = args.provider or settings.corpus_embedding_primary
        if provider_name == "jina":
            primary = JinaEmbeddingProvider(
                api_key=settings.jina_api_key, model=settings.jina_embedding_model
            )
            fallback = LocalBgeEmbeddingProvider(model=settings.local_embedding_model)
        else:
            primary = LocalBgeEmbeddingProvider(model=settings.local_embedding_model)
            fallback = None

        result = run_ingestion(
            root=args.source,
            provider=primary,
            fallback_provider=fallback,
            session=session,
            dry_run=args.dry_run,
            rebuild=args.rebuild,
        )
        print(json.dumps(result.__dict__, indent=2, default=str))
        return 0 if result.status in ("succeeded", "partial") else 1
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - process boundary
    sys.exit(main())
