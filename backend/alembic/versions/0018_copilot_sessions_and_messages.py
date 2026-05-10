"""Phase 30 (v1.4): copilot_sessions + copilot_messages.

Revision ID: 0018_copilot_sessions_and_messages
Revises: 0017_site_settings_hide_past_events
Create Date: 2026-05-08

Tables introduced for the AI Onboarding Copilot streaming-chat MVP.

`copilot_sessions` — one row per chat thread. Pinned to a user (admin or
organizer only at the router level), records which model + system-prompt
version produced the session so Phase 35 evals can group runs.

`copilot_messages` — one row per turn (user, assistant, system). The
assistant rows additionally record latency, token counts, prompt/response
SHA-256 hashes, the resolved model id (primary or fallback), and any
error class string. This is the canonical research dataset described in
REQUIREMENTS-v1.4.md; column changes after this point require a
milestone-level change request.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_copilot_sessions_and_messages"
down_revision = "0017_site_settings_hide_past_events"
branch_labels = None
depends_on = None


COPILOT_MESSAGE_ROLE = sa.Enum(
    "user", "assistant", "system",
    name="copilot_message_role",
    native_enum=True,
)


def upgrade() -> None:
    # The enum type is created implicitly by ``op.create_table`` below
    # (SqlEnum default ``create_type=True``). Explicit ``.create()`` would
    # double-create within the migration transaction.

    op.create_table(
        "copilot_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("system_prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("system_prompt_version", sa.String(length=32), nullable=False),
    )

    op.create_table(
        "copilot_messages",
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
            index=True,
        ),
        sa.Column("role", COPILOT_MESSAGE_ROLE, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Telemetry — populated for assistant rows; nullable for user/system
        # so the schema is honest about which rows actually came from an LLM.
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_copilot_messages_session_created",
        "copilot_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_messages_session_created", table_name="copilot_messages")
    op.drop_table("copilot_messages")
    op.drop_table("copilot_sessions")
    COPILOT_MESSAGE_ROLE.drop(op.get_bind(), checkfirst=True)
