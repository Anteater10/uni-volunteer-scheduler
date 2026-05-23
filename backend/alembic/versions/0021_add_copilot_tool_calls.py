"""add copilot_tool_calls audit table

Revision ID: 0021_add_copilot_tool_calls
Revises: 0020_add_corpus_chunk_fts_column
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_add_copilot_tool_calls"
down_revision = "0020_add_corpus_chunk_fts_column"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "copilot_tool_calls",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "caller_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(length=128), nullable=False, index=True),
        sa.Column("args_json", postgresql.JSONB, nullable=False),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("redactions_applied", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "confirmation_status",
            sa.String(length=24),
            nullable=False,
            server_default="not_required",
        ),
        sa.Column("call_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_copilot_tool_calls_session_created",
        "copilot_tool_calls",
        ["session_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_copilot_tool_calls_session_created", table_name="copilot_tool_calls")
    op.drop_table("copilot_tool_calls")
