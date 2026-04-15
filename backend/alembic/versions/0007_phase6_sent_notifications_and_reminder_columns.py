"""Phase 6: sent_notifications dedup table + reminder columns on signups + reminder_1h_enabled on events.

Revision ID: 0007_phase6_sent_notifications
Revises: 0006_phase5_module_templates_csv_imports
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0007_phase6_sent_notifications"
down_revision: Union[str, None] = "0006_phase5_module_templates_csv_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- sent_notifications dedup table --
    op.create_table(
        "sent_notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("signup_id", UUID(as_uuid=True), sa.ForeignKey("signups.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("provider_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "uq_sent_notifications_signup_kind",
        "sent_notifications",
        ["signup_id", "kind"],
        unique=True,
    )

    # -- Signup reminder columns --
    op.add_column("signups", sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("signups", sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True))

    # -- Event reminder toggle --
    op.add_column("events", sa.Column("reminder_1h_enabled", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("events", "reminder_1h_enabled")
    op.drop_column("signups", "reminder_1h_sent_at")
    op.drop_column("signups", "reminder_24h_sent_at")
    op.drop_index("uq_sent_notifications_signup_kind", table_name="sent_notifications")
    op.drop_table("sent_notifications")
