"""Drop the csv_imports table and csvimportstatus enum.

The CSV import pipeline (Phase 5/18) has been removed from the product —
the admin UI went in PR #51 and the backend (router block, services,
Celery task, model) goes with this revision. Committed events created by
past imports are ordinary events and are untouched.

Revision ID: 0030_drop_csv_imports
Revises: 0029_backfill_orientation_attendance_credits
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects import postgresql

revision = "0030_drop_csv_imports"
down_revision = "0029_backfill_orientation_attendance_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("csv_imports")
    sa.Enum(name="csvimportstatus").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Recreate both the enum and the table exactly as 0006 built them, so a
    # downgrade -> upgrade round-trip stays clean (see CLAUDE.md note about
    # migrations that forget the enum on the way down).
    csvimportstatus = postgresql.ENUM(
        "pending", "processing", "ready", "committed", "failed",
        name="csvimportstatus",
        create_type=False,
    )
    csvimportstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "csv_imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("raw_csv_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            csvimportstatus,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
