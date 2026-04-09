"""Phase 7: add deleted_at to users for CCPA soft-delete

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "deleted_at")
