"""Group volunteer-facing events by the week their title states.

`week_number` is the event's calendar position, derived from start_date. That
is the wrong grouping key for an orientation that runs in week 2 for the week 8
module, so the public browse page now groups by `display_week`, parsed from the
title. The regex below is a frozen copy of `app.event_title.week_from_title`.
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_add_event_display_week"
down_revision: Union[str, None] = "0042_add_school_branches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WEEK_IN_TITLE = re.compile(r"^\s*week\s*(\d{1,2})\b", re.IGNORECASE)


def upgrade() -> None:
    op.add_column("events", sa.Column("display_week", sa.Integer(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, title FROM events WHERE title IS NOT NULL")
    ).fetchall()
    updates = [
        {"event_id": str(row.id), "week": int(match.group(1))}
        for row in rows
        if (match := WEEK_IN_TITLE.match(row.title))
    ]
    if updates:
        # The id is bound as text and cast, so this does not depend on the
        # driver adapting Python UUIDs.
        bind.execute(
            sa.text(
                "UPDATE events SET display_week = :week "
                "WHERE id = CAST(:event_id AS uuid)"
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_column("events", "display_week")
