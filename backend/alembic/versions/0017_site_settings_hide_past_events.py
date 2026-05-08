"""Phase 29 (HIDE-01): add site_settings.hide_past_events_from_public flag.

Revision ID: 0017_site_settings_hide_past_events
Revises: 0016_volunteer_preferences
Create Date: 2026-04-17

- Adds the ``hide_past_events_from_public`` Boolean column (default true)
  to the existing single-row ``site_settings`` table.
- Seeds the singleton row (id=1) if it's not already present so callers
  can assume ``get_app_settings(db)`` always returns a row.
- Deviation note: CONTEXT.md called for ``0019_app_settings`` as a new
  singleton table. The project already has ``site_settings`` — we reuse
  it rather than introducing a parallel table.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0017_site_settings_hide_past_events"
down_revision = "0016_volunteer_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column(
            "hide_past_events_from_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Ensure the singleton row exists so get_app_settings() always returns one.
    op.execute(
        """
        INSERT INTO site_settings (id, default_privacy_mode, allowed_email_domain, hide_past_events_from_public)
        VALUES (1, 'full', NULL, true)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("site_settings", "hide_past_events_from_public")
