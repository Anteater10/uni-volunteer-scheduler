# ------------- Phase 31: corpus fixtures -------------
"""Test-local fixtures for Phase 31 (corpus + pgvector ingestion).

This file lives at backend/tests/conftest.py and supplements the
project-root backend/conftest.py (which provides ``engine``, ``db_session``,
``client``, etc.). Pytest discovers and merges both automatically.
"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tiny_markdown_corpus(tmp_path: Path) -> Path:
    """A tiny on-disk fixture directory used by walker/ingest tests."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nAlpha doc.\n")
    (tmp_path / "docs" / "b.md").write_text("# B\n\nBeta doc.\n")
    (tmp_path / "docs" / "node_modules").mkdir()
    (tmp_path / "docs" / "node_modules" / "junk.md").write_text("excluded")
    (tmp_path / "docs" / "test_fixture.py").write_text("# excluded by deny-list")
    return tmp_path


@pytest.fixture
def fake_embedding_provider():
    """Returns a deterministic embedding provider for ingest tests.

    Implementation lands in plan 04. Wave 0 placeholder so tests can import.
    """
    pytest.skip("fake_embedding_provider lands in plan 04")
