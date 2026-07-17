"""Add quarters.archived_at (issue #33).

Explicit admin archiving of past quarters: a nullable timestamp, set by
POST /admin/quarters/{id}/archive and cleared by /restore. Archived rows
stay listed and deep-linkable; current-week resolution skips them.

Revision ID: 0025_add_quarters_archived_at
Revises: 0024_add_quarters_table_and_event_fk
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_add_quarters_archived_at"
down_revision = "0024_add_quarters_table_and_event_fk"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "quarters",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("quarters", "archived_at")
