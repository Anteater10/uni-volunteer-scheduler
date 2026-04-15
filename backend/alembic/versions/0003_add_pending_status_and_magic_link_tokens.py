"""Add pending status and magic_link_tokens table.

Existing signup rows predate magic-link and are grandfathered as 'confirmed'.
New rows default to 'pending' at the service layer, not at the DB column default.

Revision ID: 0003_add_pending_status_and_magic_link_tokens
Revises: 0002_phase0_schema_hardening
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0003_add_pending_status_and_magic_link_tokens"
down_revision: Union[str, Sequence[str], None] = "0002_phase0_schema_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add 'pending' to the signupstatus enum (must be outside transaction)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'pending'")

    # 2. Create the magic_link_tokens table
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "signup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. Create composite index for rate-limit lookups
    op.create_index(
        "ix_magic_link_tokens_email_created_at",
        "magic_link_tokens",
        ["email", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("magic_link_tokens")
    # Note: removing enum value 'pending' from signupstatus is not supported
    # by Postgres; intentionally skipped.
