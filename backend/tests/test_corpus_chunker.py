"""Phase 31 plan 03 — deterministic recursive char chunker tests.

REQ-31-03 (determinism), REQ-31-04 (char_start/char_end invariants),
plus three boundary tests added in plan 03 (separator-first split,
substring invariant, exact overlap on flat input).
"""

from app.corpus.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKER_VERSION,
    chunk_text,
)


def test_chunker_deterministic():
    text = "para 1.\n\npara 2.\n\npara 3."
    a = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    b = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert a == b


def test_chunker_offsets_consistent():
    text = "a" * 1024
    chunks = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 1024


def test_chunker_version_constant():
    assert CHUNKER_VERSION == "v1-recursive-char-1024-128"


def test_chunker_splits_on_double_newline_first():
    # With chunk_size=10, the merged span "para1\n\npara2" (12 chars) exceeds
    # the limit, so the chunker MUST split at the \n\n boundary — not mid-word.
    text = "para1\n\npara2"
    chunks = chunk_text(text, chunk_size=10, chunk_overlap=2)
    assert len(chunks) >= 2
    # The first chunk ends at or before the start of the separator,
    # the second begins at or after the end of the separator.
    assert chunks[0].char_end <= 5  # "para1" ends at offset 5
    assert chunks[1].char_start >= 7  # "para2" starts at offset 7


def test_chunker_preserves_substring_invariant():
    # Mixed input: markdown prefix + many short lines (no \n\n, so the \n
    # separator path activates and produces small pieces that exercise the
    # multi-piece overlap-tail branch) + a long flat run for the char fallback.
    short_lines = "\n".join(f"line {i:03d}" for i in range(400))
    text = (
        "# Heading\n\n"
        "Paragraph one with some words.\n\n"
        + short_lines
        + "\n\n"
        + ("x" * 2500)
    )
    chunks = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert chunks, "expected at least one chunk for a multi-KB input"
    for c in chunks:
        assert text[c.char_start : c.char_end] == c.content

    # Empty input must return an empty list (deterministic edge case).
    assert chunk_text("", chunk_size=1024, chunk_overlap=128) == []


def test_chunker_overlap_is_chunk_overlap_chars():
    # On a flat input with no separators, adjacent chunks must overlap by
    # exactly CHUNK_OVERLAP characters at the absolute-offset level.
    text = "x" * 3000
    chunks = chunk_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    assert len(chunks) >= 2
    for i in range(len(chunks) - 1):
        assert chunks[i + 1].char_start == chunks[i].char_end - CHUNK_OVERLAP


def test_chunker_handles_runs_of_separators():
    """Consecutive separators produce empty segments — exercise the skip path.

    Three blank lines in a row create empty `text[i:j]` slices in the
    `_split_recursive` loop. Branch coverage for the "if seg" gate
    requires hitting the empty-segment case at least once.
    """
    from app.corpus.chunker import chunk_text

    text = "alpha\n\n\n\nbeta\n\n\n\ngamma"
    chunks = chunk_text(text, chunk_size=1024, chunk_overlap=128)
    assert chunks
    joined = " ".join(c.content for c in chunks)
    assert "alpha" in joined and "beta" in joined and "gamma" in joined
