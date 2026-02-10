"""add unique constraints for portal_events and signups

Revision ID: b8f0c2e41a9d
Revises: 2465a60b9dbc
Create Date: 2025-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "b8f0c2e41a9d"
down_revision: Union[str, Sequence[str], None] = "2465a60b9dbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # portal_events: prevent duplicate links (portal_id, event_id)
    op.create_unique_constraint(
        "uq_portal_events_portal_id_event_id",
        "portal_events",
        ["portal_id", "event_id"],
    )

    # signups: prevent duplicate signups for same user+slot
    op.create_unique_constraint(
        "uq_signups_user_id_slot_id",
        "signups",
        ["user_id", "slot_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_signups_user_id_slot_id",
        "signups",
        type_="unique",
    )
    op.drop_constraint(
        "uq_portal_events_portal_id_event_id",
        "portal_events",
        type_="unique",
    )
