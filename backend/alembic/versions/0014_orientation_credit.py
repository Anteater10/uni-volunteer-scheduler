"""Phase 21: orientation credit engine

Revision ID: 0014_orientation_credit
Revises: 0013_add_type_session_count_fix_orientation_duration
Create Date: 2026-04-17

- Add nullable `family_key` column to `module_templates`, backfill with `slug`.
- Create `orientationcreditsource` enum (attendance | grant).
- Create `orientation_credits` table with indexes on (volunteer_email, family_key).
- `downgrade()` drops the enum type too (CLAUDE.md — avoid the common enum-leak bug).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0014_orientation_credit"
down_revision = "0013_add_type_session_count_fix_orientation_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add family_key column to module_templates (nullable; backfilled below)
    op.add_column(
        "module_templates",
        sa.Column("family_key", sa.String(), nullable=True),
    )

    # 2. Backfill family_key = slug for all existing rows (including soft-deleted)
    op.execute("UPDATE module_templates SET family_key = slug WHERE family_key IS NULL")

    # 3. Create orientation_credits table. The enum type is created inline by
    # create_table (create_type defaults to True). Explicit pre-creation caused
    # "type already exists" on the implicit re-create, so we keep it simple.
    op.create_table(
        "orientation_credits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("volunteer_email", sa.String(length=255), nullable=False),
        sa.Column("family_key", sa.String(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "attendance",
                "grant",
                name="orientationcreditsource",
            ),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 5. Indexes
    op.create_index(
        "ix_orientation_credits_email_family",
        "orientation_credits",
        ["volunteer_email", "family_key"],
    )
    op.create_index(
        "ix_orientation_credits_email",
        "orientation_credits",
        ["volunteer_email"],
    )


def downgrade() -> None:
    op.drop_index("ix_orientation_credits_email", table_name="orientation_credits")
    op.drop_index(
        "ix_orientation_credits_email_family", table_name="orientation_credits"
    )
    op.drop_table("orientation_credits")
    op.drop_column("module_templates", "family_key")
    # Drop the enum AFTER the table that used it — avoids DependentObjectsStillExist.
    sa.Enum(name="orientationcreditsource").drop(op.get_bind(), checkfirst=True)
