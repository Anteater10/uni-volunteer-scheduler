"""Phase 32 (v1.4): add corpus_chunks.fts tsvector + GIN index.

Revision ID: 0020_add_corpus_chunk_fts_column
Revises: 0019_enable_pgvector_corpus_tables
Create Date: 2026-05-19

Adds the lexical retrieval substrate Phase 32 hybrid search depends on:

- ``corpus_chunks.fts`` — ``tsvector`` GENERATED ALWAYS AS
  ``to_tsvector('english', coalesce(content, ''))`` STORED. The stored
  generated column populates every existing row at ALTER TABLE time, so
  no application backfill is required for the 4,731-chunk corpus.
- ``ix_corpus_chunks_fts`` — GIN index on the new column. GIN is the
  read-heavy default for tsvector (PG docs: textsearch-indexes); GiST is
  rejected because corpus chunks are append-mostly and read-heavy.

Strictly additive — no edits to existing columns, indexes, or rows. The
Phase 31 corpus schema is frozen (31-SUMMARY handoff rule). Downgrade
drops the index and column in reverse order; round-trip is clean.

The ORM (``backend/app/models.py``) is intentionally NOT updated.
Phase 32 retrieval reads ``fts`` via ``sqlalchemy.text`` only, which keeps
the frozen Phase 31 ORM contract intact and avoids accidental SELECT *
fetches dragging tsvector bytes into Python.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0020_add_corpus_chunk_fts_column"
down_revision = "0019_enable_pgvector_corpus_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE corpus_chunks "
        "ADD COLUMN fts tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_corpus_chunks_fts ON corpus_chunks USING GIN (fts)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_fts")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN IF EXISTS fts")
