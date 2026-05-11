"""Phase 31 (v1.4): Knowledge corpus + pgvector ingestion.

Subpackage layout:
- ``chunker``: deterministic recursive character splitter (LangChain-style
  algorithm, hand-rolled, no LangChain dep). Public surface: ``chunk_text``,
  ``Chunk``, ``CHUNKER_VERSION``, ``CHUNK_SIZE``, ``CHUNK_OVERLAP``.
- ``walker``: allow-list filesystem walker over the trusted source set
  (markdown, alembic migrations, python docstrings, frontend leading
  comments). Opens zero DB connections; reads zero JSON/CSV. Public
  surface: ``walk_sources``, ``SourceDocument``, ``SOURCE_GLOBS_V1``,
  ``DENY_LIST``.

Both modules are pure-Python building blocks consumed by the ingest CLI
(plan 04). The 100% coverage gate mirrors the Phase 30 invariant on
``app.copilot.*``.
"""

from app.corpus.chunker import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKER_VERSION,
    Chunk,
    chunk_text,
)

__all__ = [
    "CHUNK_OVERLAP",
    "CHUNK_SIZE",
    "CHUNKER_VERSION",
    "Chunk",
    "chunk_text",
]
