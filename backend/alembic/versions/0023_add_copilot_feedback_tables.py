"""add copilot_message_ratings and copilot_session_ratings

Revision ID: 0023_add_copilot_feedback_tables
Revises: 0022_add_copilot_user_profiles_and_session_columns
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023_add_copilot_feedback_tables"
down_revision = "0022_add_copilot_user_profiles_and_session_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "copilot_message_ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("value IN ('up', 'down')", name="ck_message_rating_value"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_rating_per_user"),
    )
    op.create_index(
        "ix_copilot_message_ratings_message_id",
        "copilot_message_ratings",
        ["message_id"],
    )
    op.execute(
        "CREATE INDEX ix_copilot_message_ratings_value_down "
        "ON copilot_message_ratings (created_at DESC) WHERE value = 'down'"
    )

    op.create_table(
        "copilot_session_ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "value BETWEEN 1 AND 5", name="ck_session_rating_value_range"
        ),
        sa.UniqueConstraint("session_id", "user_id", name="uq_session_rating_per_user"),
    )
    op.create_index(
        "ix_copilot_session_ratings_session_id",
        "copilot_session_ratings",
        ["session_id"],
    )
    op.execute(
        "CREATE INDEX ix_copilot_session_ratings_value_low "
        "ON copilot_session_ratings (created_at DESC) WHERE value <= 2"
    )


def downgrade():
    op.drop_index(
        "ix_copilot_session_ratings_value_low",
        table_name="copilot_session_ratings",
    )
    op.drop_index(
        "ix_copilot_session_ratings_session_id",
        table_name="copilot_session_ratings",
    )
    op.drop_table("copilot_session_ratings")
    op.drop_index(
        "ix_copilot_message_ratings_value_down",
        table_name="copilot_message_ratings",
    )
    op.drop_index(
        "ix_copilot_message_ratings_message_id",
        table_name="copilot_message_ratings",
    )
    op.drop_table("copilot_message_ratings")
