"""Wave 0 stubs - REQ-31-03 / REQ-31-04. Implementation lands in plan 03."""
import pytest


@pytest.mark.xfail(strict=True, reason="REQ-31-03 chunker lands in plan 03")
def test_chunker_deterministic():
    from app.corpus.chunker import chunk_text  # noqa: F401  (will fail until plan 03)
    text = "para 1.\n\npara 2.\n\npara 3."
    a = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    b = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert a == b


@pytest.mark.xfail(strict=True, reason="REQ-31-04 char_start/end invariants land in plan 03")
def test_chunker_offsets_consistent():
    from app.corpus.chunker import chunk_text
    text = "a" * 1024
    chunks = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 1024


@pytest.mark.xfail(strict=True, reason="REQ-31-03 chunker version pin lands in plan 03")
def test_chunker_version_constant():
    from app.corpus.chunker import CHUNKER_VERSION
    assert CHUNKER_VERSION == "v1-recursive-char-1024-128"
