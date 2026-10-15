"""Give slots a real open/closed switch, and tie auto-granted credit to its signup.

Before this, "this slot is over" was inferred from every expected booking
holding attended/no_show, and those statuses were terminal per person. A slot
could not be reopened, and one pending signup left a slot half-closed: locked
for everyone who had been resolved, but still showing "End slot".

`slots.closed_at` / `closed_by` make closing an explicit, reversible act.
`orientation_credits.source_signup_id` records which orientation signup earned
an auto-granted credit, so re-closing a reopened orientation with that person
marked no-show can revoke exactly that credit and nothing granted by hand.

Backfill, in order:

1. Close every slot that has already started (start_time <= now()) and would
   have rendered as "ENDED" under the old rule: every seated booking holds
   attended / no_show and at least one does. Orientation: no signup left at
   pending / confirmed / checked_in. Session: every pending / confirmed shift
   commitment has an attended / no_show row for that session.
2. Repair every slot still open, because attended / no_show now exist only on
   a closed slot: orientation signups attended -> checked_in (checked_in_at
   kept, or now() when it was NULL), no_show -> confirmed (checked_in_at
   cleared); session rows attended -> checked_in (same rule), no_show rows
   deleted. Each change writes an
   audit_logs "transition" row with via "migration_0044". This is what
   un-does the old "End event" marking Thursday's volunteers no-show on
   Tuesday, and the stray no-shows a half-closed slot left behind.

3. Link existing auto-granted credits (source 'attendance') to the signup
   that earned them, from the grant's audit row (extra.signup_id), while that
   signup still exists — so re-closing a reopened orientation with that
   person no-show revokes the right credit. Hand grants, and auto-grants
   whose audit row or signup is gone, keep source_signup_id NULL and are
   never auto-revoked.
4. Recompute events.completed_at with refresh_event_completion's rule:
   stamped (if unset) when every slot with a seated booking is closed and
   there is at least one; cleared otherwise.

Downgrade drops the three columns only. Steps 2 and 4 are one-way: the
statuses and completion stamps they changed are not put back (the audit rows
record the status changes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_slot_closed_at_and_credit_source"
down_revision: Union[str, None] = "0043_add_event_display_week"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "slots", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "slots",
        sa.Column(
            "closed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "orientation_credits",
        sa.Column(
            "source_signup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_orientation_credits_source_signup_id",
        "orientation_credits",
        ["source_signup_id"],
    )

    # 1a. Orientation slots: bookings live on signups.
    op.execute(
        """
        UPDATE slots s SET closed_at = now()
        WHERE s.shift_id IS NULL
          AND s.start_time <= now()
          AND EXISTS (
            SELECT 1 FROM signups g
            WHERE g.slot_id = s.id AND g.status IN ('attended', 'no_show'))
          AND NOT EXISTS (
            SELECT 1 FROM signups g
            WHERE g.slot_id = s.id
              AND g.status IN ('pending', 'confirmed', 'checked_in'))
        """
    )
    # 1b. Shift sessions: every seated commitment needs a final attendance row
    # for this session, and at least one seated commitment has one.
    op.execute(
        """
        UPDATE slots s SET closed_at = now()
        WHERE s.shift_id IS NOT NULL
          AND s.start_time <= now()
          AND EXISTS (
            SELECT 1 FROM session_attendance a
            JOIN shift_signups ss ON ss.id = a.shift_signup_id
            WHERE a.slot_id = s.id AND a.status IN ('attended', 'no_show')
              AND ss.status IN ('pending', 'confirmed'))
          AND NOT EXISTS (
            SELECT 1 FROM shift_signups ss
            WHERE ss.shift_id = s.shift_id
              AND ss.status IN ('pending', 'confirmed')
              AND NOT EXISTS (
                SELECT 1 FROM session_attendance a
                WHERE a.shift_signup_id = ss.id AND a.slot_id = s.id
                  AND a.status IN ('attended', 'no_show')))
        """
    )

    # 2a. Open orientation slots: attended -> checked_in (checked_in_at kept,
    # or stamped now when there was none), no_show -> confirmed.
    # RETURNING sees the new status; the mapping back to the old one is 1:1.
    op.execute(
        """
        WITH changed AS (
          UPDATE signups g
          SET status = CASE g.status
                WHEN 'attended' THEN 'checked_in'::signupstatus
                ELSE 'confirmed'::signupstatus END,
              checked_in_at = CASE WHEN g.status = 'attended'
                THEN COALESCE(g.checked_in_at, now()) END
          FROM slots s
          WHERE s.id = g.slot_id AND s.closed_at IS NULL
            AND g.status IN ('attended', 'no_show')
          RETURNING g.id, g.status::text AS new_status
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'signup', c.id::text,
               json_build_object(
                 'from', CASE c.new_status WHEN 'checked_in' THEN 'attended'
                         ELSE 'no_show' END,
                 'to', c.new_status,
                 'via', 'migration_0044'),
               now()
        FROM changed c
        """
    )
    # 2b. Open sessions: attended rows -> checked_in (checked_in_at kept, or
    # stamped now when the row never had one).
    op.execute(
        """
        WITH changed AS (
          UPDATE session_attendance a
          SET status = 'checked_in',
              checked_in_at = COALESCE(a.checked_in_at, now()),
              updated_at = now()
          FROM slots s
          WHERE s.id = a.slot_id AND s.closed_at IS NULL AND a.status = 'attended'
          RETURNING a.shift_signup_id, a.slot_id, s.shift_id
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'session_attendance',
               c.shift_signup_id::text,
               json_build_object(
                 'from', 'attended', 'to', 'checked_in', 'via', 'migration_0044',
                 'slot_id', c.slot_id::text, 'shift_id', c.shift_id::text),
               now()
        FROM changed c
        """
    )
    # 2c. Open sessions: no_show rows deleted ("no row" = not checked in).
    op.execute(
        """
        WITH gone AS (
          DELETE FROM session_attendance a
          USING slots s
          WHERE s.id = a.slot_id AND s.closed_at IS NULL AND a.status = 'no_show'
          RETURNING a.shift_signup_id, a.slot_id, s.shift_id
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'session_attendance',
               g.shift_signup_id::text,
               json_build_object(
                 'from', 'no_show', 'to', NULL, 'via', 'migration_0044',
                 'slot_id', g.slot_id::text, 'shift_id', g.shift_id::text),
               now()
        FROM gone g
        """
    )

    # 3. Link auto-granted credits to the signup that earned them. The grant
    # wrote an audit row (action orientation_credit_grant, entity_id = the
    # credit id) carrying extra.signup_id; use it while that signup exists.
    op.execute(
        """
        UPDATE orientation_credits c
        SET source_signup_id = g.id
        FROM audit_logs a
        JOIN signups g ON g.id::text = a.extra->>'signup_id'
        WHERE c.source = 'attendance'
          AND c.source_signup_id IS NULL
          AND a.action = 'orientation_credit_grant'
          AND a.entity_id = c.id::text
        """
    )

    # 4. events.completed_at from the closed switches, same rule as
    # check_in_service.refresh_event_completion: set (if unset) when every slot
    # with a seated booking is closed and there is at least one; clear when any
    # such slot is open. Step 2 reopened slots, so a "completed" event whose
    # Thursday was repaired goes back to not completed.
    op.execute(
        """
        WITH seated AS (
          SELECT s.event_id, s.closed_at
          FROM slots s
          WHERE EXISTS (
                  SELECT 1 FROM signups g
                  WHERE g.slot_id = s.id
                    AND g.status IN ('pending', 'confirmed', 'checked_in',
                                     'attended', 'no_show'))
             OR EXISTS (
                  SELECT 1 FROM shift_signups ss
                  WHERE ss.shift_id = s.shift_id
                    AND ss.status IN ('pending', 'confirmed'))
        ),
        verdict AS (
          SELECT event_id, bool_and(closed_at IS NOT NULL) AS complete
          FROM seated GROUP BY event_id
        )
        UPDATE events e
        SET completed_at = CASE
              WHEN v.complete THEN COALESCE(e.completed_at, now())
              ELSE NULL END
        FROM verdict v
        WHERE v.event_id = e.id
        """
    )
    op.execute(
        """
        UPDATE events e SET completed_at = NULL
        WHERE e.completed_at IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM slots s
            WHERE s.event_id = e.id
              AND (EXISTS (
                     SELECT 1 FROM signups g
                     WHERE g.slot_id = s.id
                       AND g.status IN ('pending', 'confirmed', 'checked_in',
                                        'attended', 'no_show'))
                OR EXISTS (
                     SELECT 1 FROM shift_signups ss
                     WHERE ss.shift_id = s.shift_id
                       AND ss.status IN ('pending', 'confirmed'))))
        """
    )


def downgrade() -> None:
    # Schema only: the step-2 status repair is one-way (see module docstring).
    op.drop_index(
        "ix_orientation_credits_source_signup_id", table_name="orientation_credits"
    )
    op.drop_column("orientation_credits", "source_signup_id")
    op.drop_column("slots", "closed_by")
    op.drop_column("slots", "closed_at")
