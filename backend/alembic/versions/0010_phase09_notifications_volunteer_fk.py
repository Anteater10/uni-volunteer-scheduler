"""Phase 09: notifications.volunteer_id FK + user_id nullable + XOR CHECK constraint

Revision ID: 0010_phase09_notifications_volunteer_fk
Revises: 0009_phase08_v1_1_schema_realignment
Create Date: 2026-04-10

Per D-04 (locked decision): add volunteer_id FK to notifications, make user_id nullable,
enforce CHECK constraint that exactly one of (user_id, volunteer_id) is NOT NULL.
No new enums in this migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0010_phase09_notifications_volunteer_fk"
down_revision = "0009_phase08_v1_1_schema_realignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add volunteer_id column (nullable FK to volunteers)
    op.add_column(
        "notifications",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2. Add FK constraint with CASCADE so deleting a volunteer cleans up notifications
    op.create_foreign_key(
        "fk_notifications_volunteer_id",
        "notifications",
        "volunteers",
        ["volunteer_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3. Add index for query performance on volunteer_id
    op.create_index("ix_notifications_volunteer_id", "notifications", ["volunteer_id"])

    # 4. Make user_id nullable (previously NOT NULL)
    op.alter_column(
        "notifications",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 5. Add CHECK constraint: exactly one of (user_id, volunteer_id) must be NOT NULL
    op.create_check_constraint(
        "ck_notifications_recipient_xor",
        "notifications",
        "(user_id IS NOT NULL AND volunteer_id IS NULL) OR (user_id IS NULL AND volunteer_id IS NOT NULL)",
    )


def downgrade() -> None:
    # Reverse order of upgrade()

    # 1. Drop CHECK constraint
    op.drop_constraint("ck_notifications_recipient_xor", "notifications", type_="check")

    # 2. Make user_id NOT NULL again — delete any rows where user_id IS NULL (dev data only)
    op.execute("DELETE FROM notifications WHERE user_id IS NULL")
    op.alter_column(
        "notifications",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # 3. Drop index
    op.drop_index("ix_notifications_volunteer_id", table_name="notifications")

    # 4. Drop FK
    op.drop_constraint("fk_notifications_volunteer_id", "notifications", type_="foreignkey")

    # 5. Drop volunteer_id column
    op.drop_column("notifications", "volunteer_id")

    # No enums added in this migration — nothing to DROP TYPE.
