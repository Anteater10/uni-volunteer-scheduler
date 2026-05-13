"""Phase 31 plan 04 — CLI entry-point tests for app.corpus.__main__.

Covers REQ-31-12 (build-index path) plus the argparse surface itself:
``--help``, mutually-exclusive ``--commit / --dry-run``, ``--provider``
override, and the ``--build-index`` early-exit.

The tests stub :class:`app.database.SessionLocal` and the embedding
provider classes so no network IO or model loading happens. They also
patch :func:`app.corpus.ingest.run_ingestion` and
:func:`app.corpus.ingest.build_hnsw_index` so we test the wiring, not
the orchestrator (which has its own coverage in
``test_corpus_ingest_idempotency.py``).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def stub_session(monkeypatch):
    """Replace ``SessionLocal`` with a no-op session factory."""
    from app import database as db_mod

    closed: dict[str, bool] = {"closed": False}

    class _Sess:
        def close(self):
            closed["closed"] = True

    monkeypatch.setattr(db_mod, "SessionLocal", lambda: _Sess())
    return closed


def test_cli_help_prints_all_flags(capsys):
    """``--help`` exits 0 and mentions every documented flag."""
    from app.corpus.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--source", "--commit", "--dry-run", "--provider", "--rebuild", "--build-index"):
        assert flag in out


def test_cli_commit_and_dry_run_are_mutually_exclusive():
    """argparse refuses both flags together (SystemExit code != 0)."""
    from app.corpus.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["--commit", "--dry-run"])
    assert exc.value.code != 0


def test_cli_build_index_short_circuits(monkeypatch, stub_session, capsys):
    """``--build-index`` calls build_hnsw_index and exits 0 without ingesting."""
    from app.corpus import __main__ as cli_mod
    import app.corpus.ingest as ingest_mod

    calls: list[str] = []

    def _bhi(*, session):
        calls.append("build_hnsw_index")

    def _run_ingestion(**kwargs):  # pragma: no cover - must not be called
        calls.append("run_ingestion")
        raise AssertionError("run_ingestion must not be called when --build-index is set")

    monkeypatch.setattr(ingest_mod, "build_hnsw_index", _bhi)
    monkeypatch.setattr(ingest_mod, "run_ingestion", _run_ingestion)

    rc = cli_mod.main(["--build-index"])
    assert rc == 0
    assert calls == ["build_hnsw_index"]
    assert "HNSW index ensured." in capsys.readouterr().out
    assert stub_session["closed"] is True


def test_cli_local_provider_skips_jina_and_succeeds(monkeypatch, stub_session, capsys):
    """``--provider local`` instantiates only LocalBgeEmbeddingProvider, no fallback."""
    from app.corpus import __main__ as cli_mod
    from app.corpus import embeddings as emb_mod
    import app.corpus.ingest as ingest_mod

    instantiated: list[str] = []

    class _LocalStub:
        def __init__(self, model):
            instantiated.append(f"local:{model}")

    class _JinaStub:
        def __init__(self, *a, **kw):  # pragma: no cover
            instantiated.append("jina")
            raise AssertionError("Jina must not be instantiated under --provider local")

    monkeypatch.setattr(emb_mod, "LocalBgeEmbeddingProvider", _LocalStub)
    monkeypatch.setattr(emb_mod, "JinaEmbeddingProvider", _JinaStub)

    def _run_ingestion(*, root, provider, session, fallback_provider, dry_run, rebuild):
        # Wiring assertions:
        assert isinstance(provider, _LocalStub)
        assert fallback_provider is None
        assert dry_run is True
        assert rebuild is False
        return SimpleNamespace(
            run_id="r-local",
            files_scanned=1,
            files_unchanged=0,
            files_ingested=0,
            files_failed=0,
            chunks_emitted=2,
            chunks_embedded=0,
            status="succeeded",
        )

    monkeypatch.setattr(ingest_mod, "run_ingestion", _run_ingestion)

    rc = cli_mod.main(["--source", "/tmp/x", "--dry-run", "--provider", "local"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "succeeded"
    assert payload["chunks_emitted"] == 2
    assert any(s.startswith("local:") for s in instantiated)


def test_cli_jina_provider_wires_primary_and_fallback(monkeypatch, stub_session):
    """``--provider jina`` instantiates Jina primary + Local fallback."""
    from app.corpus import __main__ as cli_mod
    from app.corpus import embeddings as emb_mod
    import app.corpus.ingest as ingest_mod
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "jina_api_key", "test-key", raising=False)

    class _JinaStub:
        def __init__(self, *, api_key, model):
            self.api_key = api_key
            self.model = model

    class _LocalStub:
        def __init__(self, model):
            self.model = model

    monkeypatch.setattr(emb_mod, "JinaEmbeddingProvider", _JinaStub)
    monkeypatch.setattr(emb_mod, "LocalBgeEmbeddingProvider", _LocalStub)

    captured: dict[str, object] = {}

    def _run_ingestion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="r-jina",
            files_scanned=0,
            files_unchanged=0,
            files_ingested=0,
            files_failed=0,
            chunks_emitted=0,
            chunks_embedded=0,
            status="succeeded",
        )

    monkeypatch.setattr(ingest_mod, "run_ingestion", _run_ingestion)

    rc = cli_mod.main(["--source", "/tmp/x", "--provider", "jina", "--rebuild"])
    assert rc == 0
    assert isinstance(captured["provider"], _JinaStub)
    assert isinstance(captured["fallback_provider"], _LocalStub)
    assert captured["rebuild"] is True


def test_cli_returns_1_when_run_failed(monkeypatch, stub_session, capsys):
    """When the orchestrator reports status='failed', the CLI exits 1."""
    from app.corpus import __main__ as cli_mod
    from app.corpus import embeddings as emb_mod
    import app.corpus.ingest as ingest_mod

    class _LocalStub:
        def __init__(self, model):
            pass

    monkeypatch.setattr(emb_mod, "LocalBgeEmbeddingProvider", _LocalStub)

    def _run_ingestion(**kwargs):
        return SimpleNamespace(
            run_id="r-fail",
            files_scanned=1,
            files_unchanged=0,
            files_ingested=0,
            files_failed=1,
            chunks_emitted=0,
            chunks_embedded=0,
            status="failed",
        )

    monkeypatch.setattr(ingest_mod, "run_ingestion", _run_ingestion)

    rc = cli_mod.main(["--provider", "local"])
    assert rc == 1
    out = capsys.readouterr().out
    assert json.loads(out)["status"] == "failed"


def test_cli_default_provider_falls_back_to_settings(monkeypatch, stub_session):
    """When ``--provider`` is omitted, settings.corpus_embedding_primary is used."""
    from app.corpus import __main__ as cli_mod
    from app.corpus import embeddings as emb_mod
    import app.corpus.ingest as ingest_mod
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "corpus_embedding_primary", "local", raising=False)

    instantiated: list[str] = []

    class _LocalStub:
        def __init__(self, model):
            instantiated.append("local")

    monkeypatch.setattr(emb_mod, "LocalBgeEmbeddingProvider", _LocalStub)

    monkeypatch.setattr(
        ingest_mod,
        "run_ingestion",
        lambda **kw: SimpleNamespace(
            run_id="r",
            files_scanned=0,
            files_unchanged=0,
            files_ingested=0,
            files_failed=0,
            chunks_emitted=0,
            chunks_embedded=0,
            status="succeeded",
        ),
    )

    rc = cli_mod.main([])
    assert rc == 0
    assert instantiated == ["local"]
