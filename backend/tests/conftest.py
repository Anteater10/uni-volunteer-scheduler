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
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nAlpha doc.\n")
    (tmp_path / "docs" / "b.md").write_text("# B\n\nBeta doc.\n")
    (tmp_path / "docs" / "node_modules").mkdir()
    (tmp_path / "docs" / "node_modules" / "junk.md").write_text("excluded")
    (tmp_path / "docs" / "test_fixture.py").write_text("# excluded by deny-list")
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
