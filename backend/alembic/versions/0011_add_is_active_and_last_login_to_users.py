"""Phase 16 Plan 01: Add is_active + last_login_at to users, make hashed_password nullable

Revision ID: 0011_add_is_active_and_last_login_to_users
Revises: 0010_phase09_notifications_volunteer_fk
Create Date: 2026-04-15

Per Phase 16 Wave 0 (ADMIN-01 foundation): admin Users page needs is_active +
last_login_at columns, and hashed_password must become nullable so magic-link-only
invites can create users without a password. No new enum types.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_add_is_active_and_last_login_to_users"
down_revision = "0010_phase09_notifications_volunteer_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_active: NOT NULL DEFAULT TRUE — every existing user becomes active
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # last_login_at: nullable timestamp — NULL for all existing rows
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # hashed_password: was NOT NULL, becomes nullable (magic-link-only users)
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_active")
