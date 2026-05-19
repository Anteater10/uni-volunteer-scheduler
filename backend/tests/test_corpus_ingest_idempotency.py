"""Phase 31 plan 04 — ingest orchestrator integration tests.

Exercises REQ-31-08 (idempotency), REQ-31-09 (resumable on provider failure),
REQ-31-10 (fallback engages on rate-limit), REQ-31-14 (telemetry columns
populated) plus the dry-run no-write contract.

These tests use a real Postgres connection via the ``corpus_db_session``
fixture (which depends on ``alembic_engine``) so the pgvector ``Vector(1024)``
column round-trips honestly.
"""

from __future__ import annotations

from sqlalchemy import text


def _count(session, table: str) -> int:
    return session.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0


def _latest_run(session):
    return session.execute(
        text(
            "SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 1"
        )
    ).mappings().first()


def test_ingest_idempotent_on_unchanged_repo(
    tiny_markdown_corpus, fake_embedding_provider, corpus_db_session
):
    """REQ-31-08: re-running on the same files emits 0 new documents/chunks."""
    from app.corpus.ingest import run_ingestion

    r1 = run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    r2 = run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    assert r1.files_ingested > 0
    assert r2.files_ingested == 0
    assert r2.files_unchanged == r2.files_scanned == r1.files_scanned
    assert r2.chunks_emitted == 0


def test_ingest_writes_telemetry_columns_populated(
    tiny_markdown_corpus, fake_embedding_provider, corpus_db_session
):
    """REQ-31-14: every paper-grade column on ingestion_runs is set."""
    from app.corpus.ingest import run_ingestion

    run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    row = _latest_run(corpus_db_session)
    assert row is not None
    assert row["git_commit_sha"] is not None and len(row["git_commit_sha"]) == 40
    assert isinstance(row["git_dirty"], bool)
    assert isinstance(row["source_globs"], list) and len(row["source_globs"]) > 0
    assert row["embedding_provider"] == "fake"
    assert row["embedding_model"] == "fake-1024"
    assert row["embedding_dim"] == 1024
    assert row["chunker_version"] == "v1-recursive-char-1024-128"
    assert row["files_scanned"] > 0
    assert row["chunks_emitted"] > 0
    assert row["chunks_embedded"] > 0
    assert row["embedding_api_calls"] >= 0
    assert row["embedding_latency_ms_total"] >= 0
    assert row["status"] == "succeeded"
    assert row["completed_at"] is not None


def test_ingest_resumable_on_provider_failure(
    tiny_markdown_corpus, failing_provider, corpus_db_session
):
    """REQ-31-09: provider raises mid-run → first doc commits, run flagged failed."""
    from app.corpus.ingest import run_ingestion

    result = run_ingestion(
        root=tiny_markdown_corpus,
        provider=failing_provider,
        session=corpus_db_session,
    )
    # First doc was embedded successfully and committed; second raised.
    assert _count(corpus_db_session, "corpus_documents") == 1
    assert _count(corpus_db_session, "corpus_chunks") >= 1
    row = _latest_run(corpus_db_session)
    assert row["status"] == "failed"
    assert row["error_class"] == "RuntimeError"
    assert row["files_ingested"] == 1
    assert row["files_failed"] >= 1
    assert result.status == "failed"


def test_ingest_fallback_provider_engages(
    tiny_markdown_corpus, rate_limited_provider, fake_embedding_provider, corpus_db_session
):
    """REQ-31-10: primary RateLimitError → fallback used; notes records both."""
    from app.corpus.ingest import run_ingestion

    result = run_ingestion(
        root=tiny_markdown_corpus,
        provider=rate_limited_provider,
        fallback_provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    assert result.files_ingested > 0
    # Chunks carry the FALLBACK provider name.
    providers = corpus_db_session.execute(
        text("SELECT DISTINCT embedding_provider FROM corpus_chunks")
    ).scalars().all()
    assert providers == ["fake"]
    row = _latest_run(corpus_db_session)
    assert row["notes"] is not None
    assert "rate-limited" in row["notes"] and "fake" in row["notes"]


def test_ingest_dry_run_writes_nothing(
    tiny_markdown_corpus, fake_embedding_provider, corpus_db_session
):
    """--dry-run: walk + chunk + hash, but zero DB writes anywhere."""
    from app.corpus.ingest import run_ingestion

    before_runs = _count(corpus_db_session, "ingestion_runs")
    before_docs = _count(corpus_db_session, "corpus_documents")
    before_chunks = _count(corpus_db_session, "corpus_chunks")
    result = run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
        dry_run=True,
    )
    assert result.files_scanned > 0
    assert result.files_ingested == 0
    assert _count(corpus_db_session, "ingestion_runs") == before_runs
    assert _count(corpus_db_session, "corpus_documents") == before_docs
    assert _count(corpus_db_session, "corpus_chunks") == before_chunks


def test_build_hnsw_index_is_idempotent(alembic_engine, corpus_db_session):
    """REQ-31-12: index creation is ``IF NOT EXISTS`` — safe to re-run."""
    from app.corpus.ingest import build_hnsw_index

    build_hnsw_index(session=corpus_db_session)
    build_hnsw_index(session=corpus_db_session)
    rows = corpus_db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename='corpus_chunks' AND indexname='ix_corpus_chunks_embedding_hnsw'"
        )
    ).all()
    assert len(rows) == 1


def test_git_state_happy_and_dirty_paths(monkeypatch, tmp_path):
    """``_git_state`` returns sha + dirty flag from the git CLI.

    The test container does NOT have the ``git`` binary on PATH, so we
    monkeypatch ``subprocess.check_output`` to simulate a real repo. Two
    invocations exercise both the clean and the dirty branches so the
    success path (post-FileNotFoundError fallback) is fully covered.
    """
    from app.corpus import ingest as ingest_mod

    fake_sha = "a" * 40
    calls: list[list[str]] = []

    def fake_check_output(cmd, cwd=None, stderr=None):
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return (fake_sha + "\n").encode()
        if cmd[:2] == ["git", "status"]:
            # Toggle dirty/clean by counting prior status calls.
            status_calls = sum(1 for c in calls if c[:2] == ["git", "status"])
            return b"" if status_calls == 1 else b" M file.txt\n"
        raise AssertionError(f"unexpected git cmd: {cmd}")

    monkeypatch.setattr(ingest_mod.subprocess, "check_output", fake_check_output)

    sha, dirty = ingest_mod._git_state(tmp_path)
    assert sha == fake_sha and dirty is False
    sha2, dirty2 = ingest_mod._git_state(tmp_path)
    assert sha2 == fake_sha and dirty2 is True


def test_git_state_fallback_on_missing_git(monkeypatch, tmp_path):
    """``git`` not on PATH (or non-repo root) → deterministic placeholder."""
    from app.corpus import ingest as ingest_mod

    def boom(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(ingest_mod.subprocess, "check_output", boom)
    sha, dirty = ingest_mod._git_state(tmp_path)
    assert sha == "0" * 40 and dirty is False


def test_embed_with_fallback_reraises_when_no_fallback(rate_limited_provider):
    """If primary rate-limits and fallback is None, the error propagates."""
    from app.corpus.embeddings import RateLimitError
    from app.corpus.ingest import _embed_with_fallback
    import pytest as _pytest

    with _pytest.raises(RateLimitError):
        _embed_with_fallback(["x"], rate_limited_provider, None, [])


def test_ingest_marks_failed_when_every_doc_fails(
    tiny_markdown_corpus, corpus_db_session
):
    """If the provider fails on the very first batch, run status is 'failed'."""
    from app.corpus.ingest import run_ingestion
    from app.corpus.embeddings import EmbedMeta  # noqa: F401

    class AlwaysFail:
        name = "always-fail"
        model_id = "always-fail-1024"

        def embed(self, texts):
            raise RuntimeError("boom")

    result = run_ingestion(
        root=tiny_markdown_corpus,
        provider=AlwaysFail(),
        session=corpus_db_session,
    )
    assert result.status == "failed"
    assert result.files_ingested == 0
    assert result.files_failed > 0


def test_ingest_rebuild_truncates_existing_rows(
    tiny_markdown_corpus, fake_embedding_provider, corpus_db_session
):
    """``rebuild=True`` truncates corpus tables before the new run."""
    from app.corpus.ingest import run_ingestion

    run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
    )
    pre = _count(corpus_db_session, "corpus_chunks")
    assert pre > 0
    run_ingestion(
        root=tiny_markdown_corpus,
        provider=fake_embedding_provider,
        session=corpus_db_session,
        rebuild=True,
    )
    # After rebuild, only the new run's chunks remain (same count as a single ingest).
    assert _count(corpus_db_session, "corpus_chunks") == pre
    # And only the most recent docs remain (ingestion_runs row count grew however).
    assert _count(corpus_db_session, "corpus_documents") == 2
