"""Phase 0 schema hardening: TZ migration, reminder_sent, slot index, refresh token hash

Revision ID: 0002_phase0_schema_hardening
Revises: b8f0c2e41a9d
Create Date: 2026-04-08

ASSUMPTIONS:
- All existing naive DateTime values were stored as UTC (codebase exclusively used
  datetime.utcnow() prior to this migration). The `AT TIME ZONE 'UTC'` cast is correct.
- T-00-05 (threat register): mis-conversion risk is mitigated by this documented assumption.

PRODUCTION NOTE (T-00-06):
- The ix_slots_start_time index is created with a table lock here.
- For production migrations on large slots tables, replace with:
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_slots_start_time ON slots (start_time)")
  and run outside of a transaction block.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_phase0_schema_hardening"
down_revision: Union[str, Sequence[str], None] = "b8f0c2e41a9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------
    # 1. Migrate DateTime columns to timezone-aware (TIMESTAMPTZ)
    #    Backfill: existing naive values were UTC — cast with AT TIME ZONE 'UTC'
    # -------------------------

    # users
    op.alter_column(
        "users", "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # events
    for col in ("start_date", "end_date", "signup_open_at", "signup_close_at", "created_at"):
        op.alter_column(
            "events", col,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # slots
    for col in ("start_time", "end_time"):
        op.alter_column(
            "slots", col,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # signups
    op.alter_column(
        "signups", "timestamp",
        type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    # notifications
    for col in ("delivered_at", "created_at"):
        op.alter_column(
            "notifications", col,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # refresh_tokens
    for col in ("created_at", "expires_at", "revoked_at"):
        op.alter_column(
            "refresh_tokens", col,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # audit_logs
    op.alter_column(
        "audit_logs", "timestamp",
        type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    # portals
    op.alter_column(
        "portals", "created_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # -------------------------
    # 2. Add Signup.reminder_sent column
    # -------------------------
    op.add_column(
        "signups",
        sa.Column(
            "reminder_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # -------------------------
    # 3. Create btree index on slots.start_time
    #    NOTE: For production, use CREATE INDEX CONCURRENTLY outside a transaction.
    # -------------------------
    op.create_index("ix_slots_start_time", "slots", ["start_time"])

    # -------------------------
    # 4. Rename refresh_tokens.token -> token_hash
    #    T-00-07: Force re-login by deleting all existing refresh tokens.
    #    Raw tokens in DB are invalidated; Plan 03 wires new SHA-256 hash flow.
    # -------------------------
    op.alter_column(
        "refresh_tokens", "token",
        new_column_name="token_hash",
        existing_type=sa.String(length=512),
    )
    # Delete all existing refresh tokens — raw values are no longer valid after rename.
    # Users will be prompted to re-login; no user data is lost.
    op.execute("DELETE FROM refresh_tokens")


def downgrade() -> None:
    # -------------------------
    # 4. Rename token_hash back to token
    # -------------------------
    op.alter_column(
        "refresh_tokens", "token_hash",
        new_column_name="token",
        existing_type=sa.String(length=512),
    )

    # -------------------------
    # 3. Drop slot index
    # -------------------------
    op.drop_index("ix_slots_start_time", table_name="slots")

    # -------------------------
    # 2. Drop reminder_sent column
    # -------------------------
    op.drop_column("signups", "reminder_sent")

    # -------------------------
    # 1. Revert DateTime columns back to naive (TIMESTAMP without TZ)
    #    Note: AT TIME ZONE 'UTC' converts back to naive UTC — acceptable for dev rollbacks.
    # -------------------------

    # portals
    op.alter_column(
        "portals", "created_at",
        type_=sa.DateTime(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    # audit_logs
    op.alter_column(
        "audit_logs", "timestamp",
        type_=sa.DateTime(timezone=False),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    # refresh_tokens
    for col in ("created_at", "expires_at", "revoked_at"):
        op.alter_column(
            "refresh_tokens", col,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # notifications
    for col in ("delivered_at", "created_at"):
        op.alter_column(
            "notifications", col,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # signups
    op.alter_column(
        "signups", "timestamp",
        type_=sa.DateTime(timezone=False),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )

    # slots
    for col in ("start_time", "end_time"):
        op.alter_column(
            "slots", col,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # events
    for col in ("start_date", "end_date", "signup_open_at", "signup_close_at", "created_at"):
        op.alter_column(
            "events", col,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    # users
    op.alter_column(
        "users", "created_at",
        type_=sa.DateTime(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
