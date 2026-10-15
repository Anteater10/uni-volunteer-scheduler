"""Reopen slots that 0044 closed on results written before they started.

Kim's week (2026-10-13/15): the old "End event", pressed on Tuesday, wrote
``no_show`` for every confirmed student on Tuesday's *and* Thursday's
sessions. 0044 step 1 closes a slot that has started and has every seated
booking resolved. Run after Thursday's sessions start, it closes them and
keeps the Tuesday-written no-shows. QR check-in then refuses those students
(or, before the 409 guard, failed with a 500).

Nobody can attend, or miss, a session that has not started. Since #165 a slot
can only be closed once it has started (``close_slot`` / ``close_event``), and
every close writes fresh rows, so a result written before its slot's start can
only come from the old code. This migration treats such a result as bogus and
reopens its slot.

1. Find the closed slots to reopen.
   - Shift sessions: any ``session_attendance`` row with status attended /
     no_show whose ``updated_at`` is more than one second before the slot's
     ``start_time``. The second of tolerance keeps a close made at the start
     (start + 0, or the app clock a moment behind the database) genuine.
   - Orientations: signups have no per-row write time, so the evidence is the
     audit trail. For each attended / no_show signup on the slot, take its
     latest ``transition`` audit row. The slot is reopened only when every
     resolved signup has one, that row's ``to`` matches the status the signup
     holds now, and at least one of them was written more than one second
     before the slot started.
     A missing or contradicting audit row means we cannot tell when the result
     was written, so that orientation is left closed for staff to handle
     (reopening it would drop no-shows and could later revoke credit).
2. Reopen them (``closed_at`` / ``closed_by`` cleared), with a ``slot_reopen``
   audit row like the one ``reopen_slot`` writes.
3. Repair every result on a reopened slot, exactly as reopening does and as
   0044 step 2 did, because attended / no_show exist only on a closed slot:
   orientation attended -> checked_in (``checked_in_at`` kept, or now() when
   NULL), no_show -> confirmed (``checked_in_at`` cleared); session attended
   rows -> checked_in (same rule), no_show rows deleted. A result written
   after the start on the same slot is repaired too; staff close the slot
   again. Each change writes a ``transition`` audit row, via
   ``migration_0045``. Orientation credits are not touched, the same as a
   staff reopen: the next close re-syncs them.
4. Recompute ``events.completed_at`` with 0044 step 4's rule, only for the
   events that own a reopened slot. Other events are left exactly as they are.

Downgrade is a no-op: there is no schema change, and the data repair is
one-way (the audit rows record every change).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0045_reopen_premature_closes"
down_revision: Union[str, None] = "0044_slot_closed_at_and_credit_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. The closed slots to reopen.
    op.execute(
        "CREATE TEMPORARY TABLE mig0045_reopen (slot_id uuid PRIMARY KEY) "
        "ON COMMIT DROP"
    )
    # 1a. Sessions: a final row written before the session started.
    op.execute(
        """
        INSERT INTO mig0045_reopen (slot_id)
        SELECT DISTINCT s.id
        FROM slots s
        JOIN session_attendance a ON a.slot_id = s.id
        WHERE s.shift_id IS NOT NULL
          AND s.closed_at IS NOT NULL
          AND a.status IN ('attended', 'no_show')
          AND a.updated_at < s.start_time - interval '1 second'
        """
    )
    # 1b. Orientations: every resolved signup's latest transition audit row
    # matches its status, and at least one predates the slot's start.
    op.execute(
        """
        INSERT INTO mig0045_reopen (slot_id)
        WITH resolved AS (
          SELECT g.id, g.slot_id, g.status::text AS status, s.start_time
          FROM signups g
          JOIN slots s ON s.id = g.slot_id
          WHERE s.shift_id IS NULL
            AND s.closed_at IS NOT NULL
            AND g.status IN ('attended', 'no_show')
        ),
        latest AS (
          SELECT DISTINCT ON (a.entity_id)
                 a.entity_id, a.extra->>'to' AS to_status, a.timestamp
          FROM audit_logs a
          JOIN resolved r ON r.id::text = a.entity_id
          WHERE a.action = 'transition' AND a.entity_type = 'signup'
          ORDER BY a.entity_id, a.timestamp DESC NULLS LAST
        )
        SELECT r.slot_id
        FROM resolved r
        LEFT JOIN latest l ON l.entity_id = r.id::text
        GROUP BY r.slot_id
        HAVING bool_and(COALESCE(l.to_status = r.status, false))
           AND bool_or(l.timestamp < r.start_time - interval '1 second')
        """
    )

    # 2. Reopen, with the audit row reopen_slot writes.
    op.execute(
        """
        WITH reopened AS (
          UPDATE slots s SET closed_at = NULL, closed_by = NULL
          FROM mig0045_reopen m
          WHERE m.slot_id = s.id
          RETURNING s.id, s.event_id
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'slot_reopen', 'slot', r.id::text,
               json_build_object('event_id', r.event_id::text, 'via', 'migration_0045'),
               now()
        FROM reopened r
        """
    )

    # 3a. Orientation signups on reopened slots: attended -> checked_in,
    # no_show -> confirmed. RETURNING sees the new status; the map is 1:1.
    op.execute(
        """
        WITH changed AS (
          UPDATE signups g
          SET status = CASE g.status
                WHEN 'attended' THEN 'checked_in'::signupstatus
                ELSE 'confirmed'::signupstatus END,
              checked_in_at = CASE WHEN g.status = 'attended'
                THEN COALESCE(g.checked_in_at, now()) END
          FROM mig0045_reopen m
          WHERE m.slot_id = g.slot_id
            AND g.status IN ('attended', 'no_show')
          RETURNING g.id, g.status::text AS new_status
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'signup', c.id::text,
               json_build_object(
                 'from', CASE c.new_status WHEN 'checked_in' THEN 'attended'
                         ELSE 'no_show' END,
                 'to', c.new_status,
                 'via', 'migration_0045'),
               now()
        FROM changed c
        """
    )
    # 3b. Session rows on reopened slots: attended -> checked_in.
    op.execute(
        """
        WITH changed AS (
          UPDATE session_attendance a
          SET status = 'checked_in',
              checked_in_at = COALESCE(a.checked_in_at, now()),
              updated_at = now()
          FROM mig0045_reopen m, slots s
          WHERE m.slot_id = a.slot_id AND s.id = a.slot_id
            AND a.status = 'attended'
          RETURNING a.shift_signup_id, a.slot_id, s.shift_id
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'session_attendance',
               c.shift_signup_id::text,
               json_build_object(
                 'from', 'attended', 'to', 'checked_in', 'via', 'migration_0045',
                 'slot_id', c.slot_id::text, 'shift_id', c.shift_id::text),
               now()
        FROM changed c
        """
    )
    # 3c. Session rows on reopened slots: no_show rows deleted.
    op.execute(
        """
        WITH gone AS (
          DELETE FROM session_attendance a
          USING mig0045_reopen m, slots s
          WHERE m.slot_id = a.slot_id AND s.id = a.slot_id
            AND a.status = 'no_show'
          RETURNING a.shift_signup_id, a.slot_id, s.shift_id
        )
        INSERT INTO audit_logs (id, actor_id, action, entity_type, entity_id, extra, timestamp)
        SELECT gen_random_uuid(), NULL, 'transition', 'session_attendance',
               g.shift_signup_id::text,
               json_build_object(
                 'from', 'no_show', 'to', NULL, 'via', 'migration_0045',
                 'slot_id', g.slot_id::text, 'shift_id', g.shift_id::text),
               now()
        FROM gone g
        """
    )

    # 4. events.completed_at, the same two statements as 0044 step 4, but only
    # for events that own a slot this migration reopened: any other event's
    # stamp is not this migration's business, even if it has drifted.
    op.execute(
        """
        CREATE TEMPORARY TABLE mig0045_events ON COMMIT DROP AS
        SELECT DISTINCT s.event_id
        FROM slots s
        JOIN mig0045_reopen m ON m.slot_id = s.id
        """
    )
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
          AND e.id IN (SELECT event_id FROM mig0045_events)
        """
    )
    op.execute(
        """
        UPDATE events e SET completed_at = NULL
        WHERE e.completed_at IS NOT NULL
          AND e.id IN (SELECT event_id FROM mig0045_events)
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
    op.execute("DROP TABLE mig0045_events")
    op.execute("DROP TABLE mig0045_reopen")


def downgrade() -> None:
    # No schema change, and the data repair is one-way (see module docstring).
    pass
