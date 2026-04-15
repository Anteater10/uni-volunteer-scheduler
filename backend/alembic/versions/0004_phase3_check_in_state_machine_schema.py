"""Extends SignupStatus for Phase 3 check-in lifecycle. Existing rows stay confirmed; existing magic link tokens backfill as email_confirm.

Revision ID: 0004_phase3_check_in_state_machine_schema
Revises: 0003_add_pending_status_and_magic_link_tokens
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_phase3_check_in_state_machine_schema"
down_revision: Union[str, Sequence[str], None] = "0003_add_pending_status_and_magic_link_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend the signupstatus Postgres enum (must be outside transaction)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'checked_in'")
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'attended'")
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'no_show'")

    # 2. Add venue_code to events
    op.add_column("events", sa.Column("venue_code", sa.String(4), nullable=True))

    # 3. Add checked_in_at to signups
    op.add_column("signups", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))

    # 4. Create magiclinkpurpose enum type
    magiclinkpurpose = sa.Enum("email_confirm", "check_in", name="magiclinkpurpose")
    magiclinkpurpose.create(op.get_bind(), checkfirst=True)

    # 5. Add purpose column to magic_link_tokens with server default
    op.add_column(
        "magic_link_tokens",
        sa.Column(
            "purpose",
            sa.Enum("email_confirm", "check_in", name="magiclinkpurpose", create_type=False),
            nullable=False,
            server_default="email_confirm",
        ),
    )


def downgrade() -> None:
    # 1. Drop purpose column
    op.drop_column("magic_link_tokens", "purpose")

    # 2. Drop magiclinkpurpose enum type
    sa.Enum(name="magiclinkpurpose").drop(op.get_bind(), checkfirst=True)

    # 3. Drop checked_in_at from signups
    op.drop_column("signups", "checked_in_at")

    # 4. Drop venue_code from events
    op.drop_column("events", "venue_code")

    # 5. Enum value removal (checked_in, attended, no_show) from signupstatus
    #    is not supported by Postgres — intentionally skipped (no-op).
