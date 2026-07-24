"""Add site_settings.show_audit_logs_tab.

Gates the standalone "Audit Logs" admin tab behind a site setting. Off by
default — the Overview page already surfaces recent activity, so the full
log is opt-in. Admins flip it on from the Site settings card when needed.

Revision ID: 0028_add_show_audit_logs_tab
Revises: 0027_orientation_credit_quarter_set_null
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_add_show_audit_logs_tab"
down_revision = "0027_orientation_credit_quarter_set_null"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "site_settings",
        sa.Column(
            "show_audit_logs_tab",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("site_settings", "show_audit_logs_tab")
