"""Idempotent corpus ingestion orchestrator (Phase 31, plan 04).

Composes :mod:`app.corpus.walker`, :mod:`app.corpus.chunker`, and an
:class:`~app.corpus.embeddings.EmbeddingProvider` into a single function
:func:`run_ingestion` that:

* Walks the allow-listed sources under ``root``.
* Chunks each document deterministically.
* Embeds chunks via the provider (with optional primary→fallback retry on
  :class:`~app.corpus.embeddings.RateLimitError`).
* Upserts on ``(source_path, content_sha256)`` — re-ingesting an unchanged
  repo creates zero new documents and zero new chunks.
* Writes one ``ingestion_runs`` row per invocation, capturing git commit
  sha, source globs, provider/model identity, dim, chunker version, full
  counters, and final status.

Each document is committed in its own transaction so a mid-run provider
failure leaves earlier documents intact (REQ-31-09 resumability).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ..config import settings
from .chunker import chunk_text
from .embeddings import EmbeddingProvider, EmbedMeta, EMBEDDING_DIM, RateLimitError
from .walker import SOURCE_GLOBS_V1, SourceDocument, walk_sources


@dataclass
class IngestionResult:
    """Returned to the CLI; mirrors the run row written to ``ingestion_runs``."""

    run_id: str
    files_scanned: int
    files_unchanged: int
    files_ingested: int
    files_failed: int
    chunks_emitted: int
    chunks_embedded: int
    status: str  # 'succeeded' | 'partial' | 'failed'


def _git_state(root: Path) -> tuple[str, bool]:
    """Return ``(commit_sha, is_dirty)`` for ``root`` — empty SHA on non-repo."""
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(root), stderr=subprocess.DEVNULL
            )
            .strip()
            .decode()
        )
        dirty = (
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(root),
                stderr=subprocess.DEVNULL,
            ).strip()
            != b""
        )
        return sha, dirty
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # ``root`` may be a tmp_path (test fixture) — fabricate a deterministic
        # 40-char placeholder so the NOT NULL column constraint is satisfied.
        return "0" * 40, False


def _document_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _embed_with_fallback(
    texts: list[str],
    primary: EmbeddingProvider,
    fallback: EmbeddingProvider | None,
    notes: list[str],
) -> tuple[list[list[float]], EmbedMeta, EmbeddingProvider]:
    """Try ``primary`` first; on :class:`RateLimitError`, retry on ``fallback``.

    Returns the provider that actually produced the vectors so the caller
    can record per-chunk ``embedding_provider`` / ``embedding_model``.
    """
    try:
        vecs, meta = primary.embed(texts)
        return vecs, meta, primary
    except RateLimitError:
        if fallback is None:
            raise
        note = f"primary={primary.name} rate-limited; fell back to {fallback.name}"
        if note not in notes:
            notes.append(note)
        vecs, meta = fallback.embed(texts)
        return vecs, meta, fallback


def _insert_run(
    session,
    *,
    git_commit_sha: str,
    git_dirty: bool,
    source_globs: list[str],
    provider: EmbeddingProvider,
) -> uuid.UUID:
    """Write the initial ``ingestion_runs`` row with ``status='running'``."""
    run_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO ingestion_runs (
                id, status, git_commit_sha, git_dirty, source_globs,
                embedding_provider, embedding_model, embedding_dim, chunker_version
            ) VALUES (
                :id, 'running', :sha, :dirty, CAST(:globs AS JSONB),
                :ep, :em, :dim, :cv
            )
            """
        ),
        {
            "id": run_id,
            "sha": git_commit_sha,
            "dirty": git_dirty,
            "globs": json.dumps(source_globs),
            "ep": provider.name,
            "em": provider.model_id,
            "dim": EMBEDDING_DIM,
            "cv": settings.corpus_chunker_version,
        },
    )
    session.commit()
    return run_id


def _finalize_run(session, run_id: uuid.UUID, *, status: str, counters: dict[str, Any], notes: list[str], error_class: str | None, error_message: str | None) -> None:
    session.execute(
        text(
            """
            UPDATE ingestion_runs SET
                completed_at = now(),
                status = :status,
                files_scanned = :fs,
                files_unchanged = :fu,
                files_ingested = :fi,
                files_failed = :ff,
                chunks_emitted = :ce,
                chunks_embedded = :ceb,
                embedding_api_calls = :api,
                embedding_latency_ms_total = :lat,
                embedding_tokens_total = :tok,
                error_class = :ec,
                error_message = :em,
                notes = :notes
            WHERE id = :id
            """
        ),
        {
            "status": status,
            "fs": counters["files_scanned"],
            "fu": counters["files_unchanged"],
            "fi": counters["files_ingested"],
            "ff": counters["files_failed"],
            "ce": counters["chunks_emitted"],
            "ceb": counters["chunks_embedded"],
            "api": counters["embedding_api_calls"],
            "lat": counters["embedding_latency_ms_total"],
            "tok": counters["embedding_tokens_total"],
            "ec": error_class,
            "em": error_message,
            "notes": "\n".join(notes) if notes else None,
            "id": run_id,
        },
    )
    session.commit()


def _is_unchanged(session, doc: SourceDocument, content_sha: str) -> bool:
    row = session.execute(
        text(
            "SELECT 1 FROM corpus_documents "
            "WHERE source_path = :p AND content_sha256 = :h LIMIT 1"
        ),
        {"p": doc.source_path, "h": content_sha},
    ).first()
    return row is not None


def _persist_document(
    session,
    *,
    doc: SourceDocument,
    content_sha: str,
    chunks,
    vectors: list[list[float]],
    provider: EmbeddingProvider,
    run_id: uuid.UUID,
) -> None:
    """Insert one CorpusDocument + N CorpusChunks atomically."""
    doc_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO corpus_documents (
                id, source_path, source_kind, title, content_sha256,
                byte_size, ingestion_run_id
            ) VALUES (:id, :p, :k, :t, :h, :bs, :rid)
            """
        ),
        {
            "id": doc_id,
            "p": doc.source_path,
            "k": doc.source_kind,
            "t": doc.title,
            "h": content_sha,
            "bs": doc.byte_size,
            "rid": run_id,
        },
    )
    # Insert chunks with pgvector adapter — bind via SQLAlchemy's parametrized
    # statement; psycopg2 + pgvector codec handles list[float] → vector().
    from pgvector.sqlalchemy import Vector  # noqa: F401 (ensures adapter is registered)

    for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
        chunk_sha = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
        session.execute(
            text(
                """
                INSERT INTO corpus_chunks (
                    document_id, chunk_index, content, content_sha256,
                    char_start, char_end, token_estimate, embedding,
                    embedding_model, embedding_provider, ingestion_run_id
                ) VALUES (
                    :did, :ci, :c, :h, :s, :e, :tok, :emb, :em, :ep, :rid
                )
                """
            ),
            {
                "did": doc_id,
                "ci": idx,
                "c": chunk.content,
                "h": chunk_sha,
                "s": chunk.char_start,
                "e": chunk.char_end,
                "tok": max(1, len(chunk.content) // 4),
                "emb": vec,
                "em": provider.model_id,
                "ep": provider.name,
                "rid": run_id,
            },
        )


def run_ingestion(
    *,
    root: Path,
    provider: EmbeddingProvider,
    session,
    fallback_provider: EmbeddingProvider | None = None,
    dry_run: bool = False,
    rebuild: bool = False,
) -> IngestionResult:
    """Walk ``root``, chunk + embed each document, upsert into the corpus tables.

    Args:
        root: Repo-root style directory to walk.
        provider: Primary embedding provider.
        session: SQLAlchemy Session bound to the corpus database.
        fallback_provider: Optional provider used when ``primary`` raises
            :class:`RateLimitError`. The fallback is recorded in
            ``ingestion_runs.notes``.
        dry_run: If True, walk + chunk + hash but skip all DB writes
            (including the ``ingestion_runs`` row).
        rebuild: If True, TRUNCATE ``corpus_chunks`` + ``corpus_documents``
            before the new run. Explicit only — never the default.

    Returns:
        :class:`IngestionResult` mirroring the persisted run row.
    """
    counters: dict[str, Any] = {
        "files_scanned": 0,
        "files_unchanged": 0,
        "files_ingested": 0,
        "files_failed": 0,
        "chunks_emitted": 0,
        "chunks_embedded": 0,
        "embedding_api_calls": 0,
        "embedding_latency_ms_total": 0,
        "embedding_tokens_total": 0,
    }
    notes: list[str] = []

    docs = walk_sources(root=root)
    counters["files_scanned"] = len(docs)

    if dry_run:
        # Walk + chunk + hash to populate counters, but skip every DB write.
        for doc in docs:
            content_sha = _document_hash(doc.content)  # noqa: F841 — runs hash
            pieces = chunk_text(doc.content)
            counters["chunks_emitted"] += len(pieces)
        return IngestionResult(
            run_id="dry-run",
            files_scanned=counters["files_scanned"],
            files_unchanged=0,
            files_ingested=0,
            files_failed=0,
            chunks_emitted=counters["chunks_emitted"],
            chunks_embedded=0,
            status="succeeded",
        )

    if rebuild:
        session.execute(
            text(
                "TRUNCATE corpus_chunks, corpus_documents RESTART IDENTITY CASCADE"
            )
        )
        session.commit()

    git_sha, git_dirty = _git_state(root)
    run_id = _insert_run(
        session,
        git_commit_sha=git_sha,
        git_dirty=git_dirty,
        source_globs=list(SOURCE_GLOBS_V1),
        provider=provider,
    )

    error_class: str | None = None
    error_message: str | None = None

    for doc in docs:
        content_sha = _document_hash(doc.content)
        if _is_unchanged(session, doc, content_sha):
            counters["files_unchanged"] += 1
            continue
        chunks = chunk_text(doc.content)
        try:
            vecs, meta, used_provider = _embed_with_fallback(
                [c.content for c in chunks], provider, fallback_provider, notes
            )
            _persist_document(
                session,
                doc=doc,
                content_sha=content_sha,
                chunks=chunks,
                vectors=vecs,
                provider=used_provider,
                run_id=run_id,
            )
            session.commit()
            counters["files_ingested"] += 1
            counters["chunks_emitted"] += len(chunks)
            counters["chunks_embedded"] += len(vecs)
            counters["embedding_api_calls"] += meta.api_calls
            counters["embedding_latency_ms_total"] += meta.latency_ms
            counters["embedding_tokens_total"] += meta.tokens
        except Exception as exc:  # noqa: BLE001 — recorded, not silenced
            session.rollback()
            counters["files_failed"] += 1
            if error_class is None:
                error_class = exc.__class__.__name__
                error_message = str(exc)

    if counters["files_failed"] == 0:
        status = "succeeded"
    elif counters["files_ingested"] == 0:
        status = "failed"
    else:
        status = "partial"

    # `failed` per the test contract: any failure flips to 'failed' even with
    # partial commits, so REQ-31-09 reads cleanly. RESEARCH §Step 2 lists
    # 'partial' as a status, kept here for completeness.
    if counters["files_failed"] > 0 and counters["files_ingested"] > 0:
        status = "failed"

    _finalize_run(
        session,
        run_id,
        status=status,
        counters=counters,
        notes=notes,
        error_class=error_class,
        error_message=error_message,
    )

    return IngestionResult(
        run_id=str(run_id),
        files_scanned=counters["files_scanned"],
        files_unchanged=counters["files_unchanged"],
        files_ingested=counters["files_ingested"],
        files_failed=counters["files_failed"],
        chunks_emitted=counters["chunks_emitted"],
        chunks_embedded=counters["chunks_embedded"],
        status=status,
    )


def build_hnsw_index(*, session) -> None:
    """Idempotently create the HNSW cosine index on ``corpus_chunks.embedding``.

    ``IF NOT EXISTS`` makes the operation safe to re-run, and an ``ANALYZE``
    refreshes pg_statistics so the planner picks the index up on the next
    EXPLAIN. RESEARCH D7/D8: HNSW with ``vector_cosine_ops`` is the right
    default for the <1M-row corpus this project will ever hold.
    """
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw "
            "ON corpus_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )
    session.commit()
    # ANALYZE cannot run inside a transaction block.
    session.execute(text("COMMIT"))
    session.execute(text("ANALYZE corpus_chunks"))


__all__ = ["IngestionResult", "run_ingestion", "build_hnsw_index"]
