# ------------- Phase 31: corpus fixtures -------------
"""Test-local fixtures for Phase 31 (corpus + pgvector ingestion).

This file lives at backend/tests/conftest.py and supplements the
project-root backend/conftest.py (which provides ``engine``, ``db_session``,
``client``, etc.). Pytest discovers and merges both automatically.
"""
import os
from pathlib import Path

import pytest


@pytest.fixture
def tiny_markdown_corpus(tmp_path: Path) -> Path:
    """A tiny on-disk fixture directory used by walker/ingest tests.

    Contains two real markdown documents and two deny-listed paths so the
    walker's filter is exercised end-to-end in the ingest integration tests.

    Files live under ``docs/knowledge-base/`` because that is what the shipped
    ``SOURCE_GLOBS_V1`` allow-lists — the corpus is the curated knowledge base,
    not the codebase. Keeping the fixture on the real default globs means these
    tests break if the allow-list is narrowed further.
    """
    kb = tmp_path / "docs" / "knowledge-base"
    kb.mkdir(parents=True)
    (kb / "a.md").write_text("# A\n\nAlpha doc.\n")
    (kb / "b.md").write_text("# B\n\nBeta doc.\n")
    # Deny-listed even though it matches the allow-list glob.
    (kb / "node_modules").mkdir()
    (kb / "node_modules" / "junk.md").write_text("excluded")
    (kb / "test_fixture.py").write_text("# excluded by deny-list")
    return tmp_path


@pytest.fixture
def fake_embedding_provider():
    """Deterministic in-memory provider producing 1024-dim vectors.

    Hash-derived so identical input texts produce byte-identical vectors,
    which lets idempotency tests assert no spurious re-embeds.
    """
    from app.corpus.embeddings import EmbedMeta

    class FakeProvider:
        name = "fake"
        model_id = "fake-1024"

        def embed(self, texts):
            import hashlib

            vecs = []
            for t in texts:
                h = hashlib.sha256(t.encode()).digest()  # 32 bytes
                vec = [(b - 128) / 128.0 for b in h] * (1024 // 32)  # 32 * 32 = 1024
                vecs.append(vec[:1024])
            return vecs, EmbedMeta(
                provider="fake",
                model_id="fake-1024",
                api_calls=0,
                latency_ms=1,
                tokens=0,
            )

    return FakeProvider()


@pytest.fixture
def failing_provider():
    """Provider that raises ``RuntimeError`` on every call.

    Used by the resumable-on-provider-failure test to force a mid-run
    exception path. Returns a class instance so test code can hold it
    across docs.
    """
    from app.corpus.embeddings import EmbedMeta  # noqa: F401 (kept for parity)

    class FailingProvider:
        name = "failing"
        model_id = "failing-1024"

        def __init__(self):
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            if self.calls == 1:
                # First document embeds normally so we can prove partial
                # progress is committed. Subsequent calls raise.
                import hashlib

                vecs = []
                for t in texts:
                    h = hashlib.sha256(t.encode()).digest()
                    vec = [(b - 128) / 128.0 for b in h] * (1024 // 32)
                    vecs.append(vec[:1024])
                from app.corpus.embeddings import EmbedMeta as _M

                return vecs, _M(
                    provider="failing",
                    model_id="failing-1024",
                    api_calls=0,
                    latency_ms=1,
                    tokens=0,
                )
            raise RuntimeError("simulated provider failure")

    return FailingProvider()


@pytest.fixture
def rate_limited_provider():
    """Provider that always raises ``RateLimitError`` — triggers fallback."""
    from app.corpus.embeddings import RateLimitError

    class RateLimitedProvider:
        name = "rate-limited"
        model_id = "rate-limited-1024"

        def embed(self, texts):
            raise RateLimitError("simulated 429")

    return RateLimitedProvider()


# ------------- Phase 31 plan 02: Alembic migration fixtures -------------


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@db:5432/test_uvs",
    )


def _drop_all_schema(url: str) -> None:
    """Wipe the public schema so Alembic can start from a known-empty DB.

    The session-scoped ``engine`` fixture in ``backend/conftest.py`` calls
    ``Base.metadata.create_all`` which leaves ORM-created tables behind. To
    keep migration round-trip tests hermetic we drop the schema (and the
    ``vector`` extension if installed) before binding Alembic.
    """
    from sqlalchemy import create_engine, text as _text

    eng = create_engine(url, future=True)
    with eng.begin() as conn:
        conn.execute(_text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(_text("CREATE SCHEMA public"))
        conn.execute(_text("GRANT ALL ON SCHEMA public TO postgres"))
        conn.execute(_text("GRANT ALL ON SCHEMA public TO public"))
    eng.dispose()


@pytest.fixture
def alembic_command(monkeypatch):
    """Run Alembic against ``TEST_DATABASE_URL``.

    ``backend/alembic/env.py`` reads ``app.config.settings.database_url``
    rather than the ini file's ``sqlalchemy.url``, so we patch the settings
    object for the duration of the test. We also wipe the schema first so a
    prior session's ``Base.metadata.create_all`` doesn't collide with the
    migration's ``CREATE TABLE`` statements.
    """
    from alembic.config import Config
    from alembic import command as alembic_cmd_mod
    from app.config import settings as app_settings

    url = _test_database_url()
    _drop_all_schema(url)
    monkeypatch.setattr(app_settings, "database_url", url, raising=False)

    # alembic.ini lives at backend/alembic.ini; tests run with cwd=/app
    # (per the docker invocation in CLAUDE.md), so the relative path works.
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    # Bring DB to head so individual tests can downgrade/upgrade from there.
    alembic_cmd_mod.upgrade(cfg, "head")

    class _CmdShim:
        def upgrade(self, rev: str) -> None:
            alembic_cmd_mod.upgrade(cfg, rev)

        def downgrade(self, rev: str) -> None:
            alembic_cmd_mod.downgrade(cfg, rev)

    return _CmdShim()


@pytest.fixture
def alembic_engine(alembic_command):
    """SQLAlchemy engine bound to the freshly-migrated TEST_DATABASE_URL.

    Depends on ``alembic_command`` so the schema is guaranteed to be at
    ``head`` before any query runs.
    """
    from sqlalchemy import create_engine

    eng = create_engine(_test_database_url(), future=True)
    try:
        yield eng
    finally:
        eng.dispose()


# ------------- Phase 32 plan 02: hybrid retrieval fixtures -------------


@pytest.fixture
def corpus_fixture(corpus_db_session):
    """Seed 10 chunks across two providers for hybrid retrieval tests.

    Layout:
      - 6 chunks with ``embedding_provider='local-bge'`` (the "active" provider
        most tests assume).
      - 4 chunks with ``embedding_provider='jina-v3-embeddings'`` (the wrong
        provider — must NEVER appear in same-provider results).

    Content is hand-crafted so FTS (lexical) and dense (random-but-deterministic
    vectors) disagree on some rankings — that's the whole point of hybrid.
    Returns a dict with the inserted chunk ids keyed by tag, plus a
    ``query_embedding`` callable that builds a deterministic 1024-dim vector.
    """
    import hashlib
    import uuid as _uuid

    from pgvector.sqlalchemy import Vector  # noqa: F401  (register psycopg2 adapter)
    from sqlalchemy import text as _text

    _hex64 = "a" * 64
    _sha40 = "0" * 40

    def _vec(seed: str) -> list[float]:
        """Deterministic 1024-dim unit-ish vector derived from a seed string."""
        h = hashlib.sha256(seed.encode()).digest()  # 32 bytes
        raw = [(b - 128) / 128.0 for b in h] * (1024 // 32)
        return raw[:1024]

    # One ingestion_run per provider (FK target)
    run_local = _uuid.uuid4()
    run_jina = _uuid.uuid4()
    corpus_db_session.execute(
        _text(
            "INSERT INTO ingestion_runs (id, status, git_commit_sha, "
            "source_globs, embedding_provider, embedding_model, embedding_dim, "
            "chunker_version) VALUES "
            "(:id, 'succeeded', :sha, '[]'::jsonb, 'local-bge', "
            "'BAAI/bge-large-en-v1.5', 1024, 'v1')"
        ),
        {"id": run_local, "sha": _sha40},
    )
    corpus_db_session.execute(
        _text(
            "INSERT INTO ingestion_runs (id, status, git_commit_sha, "
            "source_globs, embedding_provider, embedding_model, embedding_dim, "
            "chunker_version) VALUES "
            "(:id, 'succeeded', :sha, '[]'::jsonb, 'jina-v3-embeddings', "
            "'jina-embeddings-v3', 1024, 'v1')"
        ),
        {"id": run_jina, "sha": _sha40},
    )

    # 10 chunks. Content overlaps on "volunteer" / "orientation" / "module" so
    # FTS finds chunks across both providers; embeddings derived from a label
    # disjoint from content so dense ordering does NOT match FTS ordering.
    rows = [
        # tag, content, provider, vec_seed
        ("local_orient_1", "Volunteer orientation is required before signing up for any module.", "local-bge", "alpha"),
        ("local_orient_2", "Orientation covers safety, scheduling, and check-in procedures.", "local-bge", "bravo"),
        ("local_module_1", "Module SciTrek-101 has four 50-minute periods plus an orientation slot.", "local-bge", "charlie"),
        ("local_module_2", "Each module template imports quarterly from a CSV file.", "local-bge", "delta"),
        ("local_generic_1", "The scheduler exposes a REST API for organizers.", "local-bge", "echo"),
        ("local_generic_2", "Audit logs record every check-in event.", "local-bge", "foxtrot"),
        ("jina_orient_1", "Orientation is the prerequisite for volunteer signups.", "jina-v3-embeddings", "golf"),
        ("jina_orient_2", "Volunteers receive an orientation reminder email weekly.", "jina-v3-embeddings", "hotel"),
        ("jina_module_1", "Module reminders fire 24 hours before each scheduled period.", "jina-v3-embeddings", "india"),
        ("jina_misc_1", "The frontend is built with React 19 and Vite 7.", "jina-v3-embeddings", "juliet"),
    ]

    ids: dict[str, _uuid.UUID] = {}
    for tag, content, provider, seed in rows:
        chunk_id = _uuid.uuid4()
        doc_id = _uuid.uuid4()
        run_id = run_local if provider == "local-bge" else run_jina
        model_id = (
            "BAAI/bge-large-en-v1.5" if provider == "local-bge" else "jina-embeddings-v3"
        )
        corpus_db_session.execute(
            _text(
                "INSERT INTO corpus_documents "
                "(id, source_path, source_kind, content_sha256, byte_size, "
                "ingestion_run_id) "
                "VALUES (:id, :p, 'markdown', :h, :b, :r)"
            ),
            {
                "id": doc_id,
                "p": f"docs/{tag}.md",
                "h": _hex64,
                "b": len(content),
                "r": run_id,
            },
        )
        corpus_db_session.execute(
            _text(
                "INSERT INTO corpus_chunks "
                "(id, document_id, chunk_index, content, content_sha256, "
                "char_start, char_end, embedding, embedding_provider, "
                "embedding_model, ingestion_run_id) "
                "VALUES (:id, :d, 0, :c, :h, 0, :e, :v, :p, :m, :r)"
            ),
            {
                "id": chunk_id,
                "d": doc_id,
                "c": content,
                "h": _hex64,
                "e": len(content),
                "v": _vec(seed),
                "p": provider,
                "m": model_id,
                "r": run_id,
            },
        )
        ids[tag] = chunk_id
    corpus_db_session.commit()

    return {
        "ids": ids,
        "vec": _vec,
        "session": corpus_db_session,
    }


@pytest.fixture
def corpus_db_session(alembic_engine):
    """Real SQLAlchemy Session bound to a freshly-migrated test DB.

    The corpus ingest tests need a real connection (pgvector adapter, real
    Postgres) — the in-memory ``db_session`` fixture from ``backend/conftest.py``
    runs inside a SAVEPOINT and shares connection state with the FastAPI test
    client, which is not what we want here. Each test gets a clean
    ``ingestion_runs`` / ``corpus_documents`` / ``corpus_chunks`` set thanks to
    ``alembic_command`` wiping public schema before binding.
    """
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=alembic_engine, future=True, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
