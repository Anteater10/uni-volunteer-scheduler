"""Phase 24: volunteer_preferences for reminder opt-out + SMS opt-in storage.

Revision ID: 0016_volunteer_preferences
Revises: 0015_custom_form_fields
Create Date: 2026-04-17

- Create `volunteer_preferences` table keyed by `volunteer_email` (String PK).
- Columns:
    - email_reminders_enabled BOOLEAN NOT NULL DEFAULT true
    - sms_opt_in BOOLEAN NOT NULL DEFAULT false       (Phase 27 will use)
    - phone_e164 VARCHAR(20) NULL                     (Phase 27 storage)
    - created_at, updated_at TIMESTAMPTZ DEFAULT now()
- No FK to volunteers — consent records outlive volunteer rows and the email
  is the stable identity across signups (matches orientation_credits).
- Clean downgrade drops the table (no enum to leak).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_volunteer_preferences"
down_revision = "0015_custom_form_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "volunteer_preferences",
        sa.Column("volunteer_email", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column(
            "email_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "sms_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
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


def downgrade() -> None:
    op.drop_table("volunteer_preferences")
