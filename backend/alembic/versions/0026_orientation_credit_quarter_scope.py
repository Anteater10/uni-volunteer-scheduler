"""Scope orientation credits to the quarter they were earned in (issue #30).

Adds ``orientation_credits.quarter_id`` (NOT NULL FK → quarters) and replaces
the (email, family) index with (email, family, quarter). The table has never
held rows in any environment (the explicit-grant path was unexercised — see
the #30 investigation), so the column is added NOT NULL directly; if rows
somehow exist the migration fails loudly rather than guessing a quarter.

Revision ID: 0026_orientation_credit_quarter_scope
Revises: 0025_add_quarters_archived_at
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0026_orientation_credit_quarter_scope"
down_revision = "0025_add_quarters_archived_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orientation_credits",
        sa.Column(
            "quarter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("quarters.id", name="fk_orientation_credits_quarter_id"),
            nullable=False,
        ),
    )
    op.drop_index(
        "ix_orientation_credits_email_family", table_name="orientation_credits"
    )
    op.create_index(
        "ix_orientation_credits_email_family_quarter",
        "orientation_credits",
        ["volunteer_email", "family_key", "quarter_id"],
    )


def downgrade():
    op.drop_index(
        "ix_orientation_credits_email_family_quarter",
        table_name="orientation_credits",
    )
    op.create_index(
        "ix_orientation_credits_email_family",
        "orientation_credits",
        ["volunteer_email", "family_key"],
    )
    op.drop_column("orientation_credits", "quarter_id")
