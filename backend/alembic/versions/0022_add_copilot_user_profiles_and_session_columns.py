"""add copilot_user_profiles table and session memory columns

Revision ID: 0022_add_copilot_user_profiles_and_session_columns
Revises: 0021_add_copilot_tool_calls
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022_add_copilot_user_profiles_and_session_columns"
down_revision = "0021_add_copilot_tool_calls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "copilot_user_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profile_text", sa.Text, nullable=False, server_default=""),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.add_column(
        "copilot_sessions",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "copilot_sessions",
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "copilot_sessions",
        sa.Column("profile_extracted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_copilot_sessions_idle_sweep",
        "copilot_sessions",
        ["last_message_at", "closed_at"],
    )


def downgrade():
    op.drop_index("ix_copilot_sessions_idle_sweep", table_name="copilot_sessions")
    op.drop_column("copilot_sessions", "profile_extracted_at")
    op.drop_column("copilot_sessions", "last_message_at")
    op.drop_column("copilot_sessions", "closed_at")
    op.drop_table("copilot_user_profiles")
