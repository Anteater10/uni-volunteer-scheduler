"""Add events.completed_at — the explicit "event ended" stamp.

Completion used to be a frontend-only derivation over signup statuses, so
the events list couldn't distinguish an ended event from an upcoming one
and there was nothing to undo. The resolve endpoints now stamp this column
when the last expected signup lands on attended/no_show, and the new
reopen endpoint clears it.

Backfill: events whose signups are already fully resolved get stamped now
(with now() — the true resolution time was never recorded).

Revision ID: 0033_add_event_completed_at
Revises: 0032_rename_module_templates_to_modules
"""

import sqlalchemy as sa
from alembic import op

revision = "0033_add_event_completed_at"
down_revision = "0032_rename_module_templates_to_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Stamp events that were already fully resolved before this column
    # existed: at least one terminal signup and no expected one left.
    op.execute(
        """
        UPDATE events e
        SET completed_at = now()
        WHERE EXISTS (
            SELECT 1 FROM signups s
            JOIN slots sl ON sl.id = s.slot_id
            WHERE sl.event_id = e.id
              AND s.status IN ('attended', 'no_show')
        )
        AND NOT EXISTS (
            SELECT 1 FROM signups s
            JOIN slots sl ON sl.id = s.slot_id
            WHERE sl.event_id = e.id
              AND s.status IN ('pending', 'confirmed', 'checked_in')
        )
        """
    )


def downgrade() -> None:
    op.drop_column("events", "completed_at")
