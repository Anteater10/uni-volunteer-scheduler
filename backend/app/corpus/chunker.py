"""Deterministic recursive character chunker (Phase 31, plan 03).

Hand-rolled LangChain-style recursive character splitter with a fixed,
seed-free policy: same input bytes → same chunks every run. No external
dependencies — no LangChain, no tiktoken, no random, no time, no I/O.

Public surface:
    chunk_text(text, *, chunk_size=1024, chunk_overlap=128, separators=...) -> list[Chunk]
    Chunk(content: str, char_start: int, char_end: int)
    CHUNKER_VERSION, CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS

Invariants (load-bearing for Phase 32 citations):
    * Determinism — identical input bytes produce byte-identical output across runs.
    * Substring — for every emitted Chunk c, text[c.char_start:c.char_end] == c.content.
    * Overlap — on long flat input, adjacent chunks overlap by exactly
      ``chunk_overlap`` characters at the absolute-offset level.
"""

from __future__ import annotations

from dataclasses import dataclass

CHUNKER_VERSION = "v1-recursive-char-1024-128"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
# Separators tried in order, coarsest → finest. Empty string is the
# char-level fallback that guarantees forward progress on any input.
SEPARATORS: list[str] = ["\n\n", "\n", ". ", " ", ""]


@dataclass(frozen=True)
class Chunk:
    """One chunked slice of a source document, with absolute offsets."""

    content: str
    char_start: int
    char_end: int


def _split_recursive(
    text: str,
    abs_start: int,
    separators: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[tuple[str, int, int]]:
    """Recursively split ``text`` until every piece is ≤ ``chunk_size``.

    Returns a list of ``(content, abs_start, abs_end)`` tuples. The
    ``abs_*`` offsets are positions into the ORIGINAL (top-level) input,
    not the slice we're recursing into — this is the invariant that lets
    chunk_text round-trip ``text[chunk.char_start:chunk.char_end] == chunk.content``.

    Separators are skipped in the output (they are structural, not content).
    The char-level fallback (``sep == ""``) slices the residual text into
    fixed ``chunk_size`` windows so the algorithm always terminates.
    """
    if len(text) <= chunk_size:
        return [(text, abs_start, abs_start + len(text))]

    sep = separators[0]
    rest = separators[1:]

    if sep == "":
        # Char-level fallback: hard-slice into small windows whose size
        # divides naturally into chunk_size with the requested overlap.
        # Using a piece-size of ``chunk_overlap`` (when set) gives the
        # merge stage enough granularity to retain a precise overlap tail.
        # When ``chunk_overlap`` is 0, falling back to ``chunk_size`` is
        # fine because no overlap needs to be preserved.
        piece_size = chunk_overlap if chunk_overlap > 0 else chunk_size
        piece_size = max(1, piece_size)
        pieces: list[tuple[str, int, int]] = []
        i = 0
        n = len(text)
        while i < n:
            end = min(i + piece_size, n)
            pieces.append((text[i:end], abs_start + i, abs_start + end))
            i = end
        return pieces

    # Split by sep, dropping the separator itself from output pieces.
    raw_pieces: list[tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i <= n:
        j = text.find(sep, i)
        if j == -1:
            seg = text[i:]
            if seg:
                raw_pieces.append((seg, abs_start + i, abs_start + i + len(seg)))
            break
        seg = text[i:j]
        if seg:
            raw_pieces.append((seg, abs_start + i, abs_start + j))
        i = j + len(sep)

    # If the separator never matched, recurse straight into the next one.
    if len(raw_pieces) <= 1 and raw_pieces and len(raw_pieces[0][0]) > chunk_size:
        return _split_recursive(text, abs_start, rest, chunk_size, chunk_overlap)

    result: list[tuple[str, int, int]] = []
    for content, s, e in raw_pieces:
        if len(content) <= chunk_size:
            result.append((content, s, e))
        else:
            result.extend(_split_recursive(content, s, rest, chunk_size, chunk_overlap))
    return result


def _merge(
    pieces: list[tuple[str, int, int]],
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Greedy windowing pass over leaf pieces.

    Forms chunks of span ≤ ``chunk_size`` (span = last_end - first_start).
    After each emitted chunk, retains a trailing tail of pieces such that
    the tail's span ≤ ``chunk_overlap`` so the next chunk overlaps the
    previous one. If the next piece can't fit even with overlap dropped,
    the overlap is sacrificed (separator-split case).

    Chunk content is taken from ``text[start:end]`` so the substring
    invariant ``text[start:end] == chunk.content`` holds by construction —
    even when separators are stripped between pieces.
    """
    chunks: list[Chunk] = []
    buf: list[tuple[str, int, int]] = []

    def flush() -> None:
        start = buf[0][1]
        end = buf[-1][2]
        chunks.append(Chunk(content=text[start:end], char_start=start, char_end=end))

    for piece in pieces:
        _, _, e = piece
        if not buf:
            buf.append(piece)
            continue
        new_span = e - buf[0][1]
        if new_span <= chunk_size:
            buf.append(piece)
            continue

        # Adding this piece would overflow → flush current buffer.
        flush()

        # Build overlap tail from the just-flushed buf: keep the trailing
        # pieces whose combined span is ≤ chunk_overlap.
        tail: list[tuple[str, int, int]] = []
        for p in reversed(buf):
            if not tail:
                tail.insert(0, p)
                continue
            candidate_span = tail[-1][2] - p[1]
            if candidate_span <= chunk_overlap:
                tail.insert(0, p)
            else:
                break

        # If adding the new piece on top of the tail still overflows
        # chunk_size, the overlap is unusable for this transition → drop it.
        if tail and (e - tail[0][1]) > chunk_size:
            tail = []

        buf = tail
        buf.append(piece)

    if buf:
        flush()
    return chunks


def chunk_text(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    separators: list[str] = SEPARATORS,
) -> list[Chunk]:
    """Split ``text`` into overlapping chunks of ≤ ``chunk_size`` characters.

    Deterministic and pure: no randomness, no time, no I/O, no env reads.
    The same ``text`` always produces the same ``[Chunk(...)]`` output,
    byte-for-byte.

    Args:
        text: The source text. May be empty.
        chunk_size: Maximum chunk span (end - start) in characters.
        chunk_overlap: Target number of overlap characters between
            adjacent chunks. May be sacrificed across hard separator
            boundaries when overlap-with-next-piece would still overflow.
        separators: Ordered list of separators to try, coarsest first.
            Must end with ``""`` (the char-level fallback).

    Returns:
        List of :class:`Chunk`. Empty when ``text`` is empty.
    """
    if not text:
        return []
    pieces = _split_recursive(text, 0, separators, chunk_size, chunk_overlap)
    return _merge(pieces, text, chunk_size, chunk_overlap)
