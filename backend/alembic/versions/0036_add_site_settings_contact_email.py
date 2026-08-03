"""Add site_settings.contact_email.

2026-08-02 read-only volunteer signups: schedule changes are coordinated
with the SciTrek organizers by email, so the address is admin-editable
site configuration surfaced in email copy and the public manage page.

Revision ID: 0036_add_site_settings_contact_email
Revises: 0035_add_promotion_confirm_purpose
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_add_site_settings_contact_email"
down_revision = "0035_add_promotion_confirm_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("contact_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "contact_email")
