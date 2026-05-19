"""Phase 31 (v1.4): enable pgvector + corpus tables.

Revision ID: 0019_enable_pgvector_corpus_tables
Revises: 0018_copilot_sessions_and_messages
Create Date: 2026-05-11

Enables the ``vector`` extension and creates the three tables that hold the
knowledge corpus for the AI Onboarding Copilot:

- ``ingestion_runs`` — one row per CLI ingest invocation, paper-grade
  telemetry (created first because ``corpus_documents`` and
  ``corpus_chunks`` FK into it).
- ``corpus_documents`` — one row per source file (markdown / python
  docstring / alembic header / frontend top-comment).
- ``corpus_chunks`` — one row per embedding-sized slice with
  ``embedding vector(1024)`` (Jina v3 native dim; BGE fallback is
  right-padded to 1024). HNSW index is intentionally **NOT** built here —
  see RESEARCH D8 / plan 04's ``--build-index`` CLI flag.

Round-trip safety: downgrade drops in FK-reverse order and uses
``DROP EXTENSION IF EXISTS vector``. ``CREATE EXTENSION IF NOT EXISTS`` on
upgrade. This mirrors the CLAUDE.md note on enum-downgrade leakage — same
trap applies to extensions, and we avoid it explicitly.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision = "0019_enable_pgvector_corpus_tables"
down_revision = "0018_copilot_sessions_and_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable the vector extension. Safe to re-run.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. ingestion_runs FIRST — corpus_documents + corpus_chunks FK into it.
    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("git_commit_sha", sa.CHAR(length=40), nullable=False),
        sa.Column(
            "git_dirty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("source_globs", postgresql.JSONB(), nullable=False),
        sa.Column("embedding_provider", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("chunker_version", sa.Text(), nullable=False),
        sa.Column(
            "files_scanned",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "files_unchanged",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "files_ingested",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "files_failed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "chunks_emitted",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "chunks_embedded",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "embedding_api_calls",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "embedding_latency_ms_total",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "embedding_tokens_total",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_class", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # 3. corpus_documents
    op.create_table(
        "corpus_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_path", "content_sha256", name="uq_corpus_documents_path_hash"
        ),
    )

    # 4. corpus_chunks — has the vector(1024) column.
    op.create_table(
        "corpus_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("corpus_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_provider", sa.Text(), nullable=False),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_corpus_chunks_doc_idx"
        ),
    )

    # 5. Indexes (no HNSW on embedding — that lands in plan 04 via
    # the ingest CLI's --build-index flag; building HNSW pre-bulk-load is
    # materially slower per-row. See RESEARCH D8 / Pitfall 5.).
    op.create_index(
        "ix_corpus_documents_source_path",
        "corpus_documents",
        ["source_path"],
    )
    op.create_index(
        "ix_ingestion_runs_started_at",
        "ingestion_runs",
        ["started_at"],
        postgresql_ops={"started_at": "DESC"},
    )


def downgrade() -> None:
    # Drop indexes first, then tables in FK-reverse order, then extension.
    op.drop_index(
        "ix_ingestion_runs_started_at", table_name="ingestion_runs", if_exists=True
    )
    op.drop_index(
        "ix_corpus_documents_source_path",
        table_name="corpus_documents",
        if_exists=True,
    )
    op.drop_table("corpus_chunks")
    op.drop_table("corpus_documents")
    op.drop_table("ingestion_runs")
    # Drop extension last. IF EXISTS prevents round-trip DuplicateObject
    # errors and a re-upgrade restores it cleanly via IF NOT EXISTS above.
    op.execute("DROP EXTENSION IF EXISTS vector")
