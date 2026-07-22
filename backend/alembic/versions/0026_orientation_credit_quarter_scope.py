"""Record the quarter an orientation credit was earned in (issue #30).

Adds ``orientation_credits.quarter_id`` as a NULLABLE FK → quarters. The
quarter is display/filter metadata only ("earned in Winter 2026" on the admin
page) — credit itself is permanent, keyed by (volunteer_email, family_key),
so the existing (email, family) index is untouched. Null means the credit
predates the quarters feature or was earned outside any entered quarter.

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
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("orientation_credits", "quarter_id")
