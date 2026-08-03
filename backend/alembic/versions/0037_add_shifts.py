"""Add shifts, shift_signups, session_attendance; migrate period slots to shifts.

2026-08-02 shifts design. A *shift* becomes the bookable unit: an
organizer-named, all-or-nothing package of *sessions*. One shift signup covers
every session in the shift, capacity and the waitlist move from the slot to the
shift, and individual sessions stop being separately bookable.

Legacy period slots are migrated into single-session shifts so the app has
exactly one model (spec decision 5) — no legacy code path. A single-session
shift behaves exactly as that slot did: booking it books that one session.
Orientation slots are untouched and stay individually bookable via ``Signup``.

ACCEPTED CASUALTIES — all confined to converted PERIOD signups. Orientation
signups and everything hanging off them are untouched.

1. Outstanding magic-link tokens anchored to a converted period signup die
   with it (FK ondelete CASCADE). Pre-production this costs nothing real; a
   re-send covers any dev/demo case. Tokens anchored to orientation signups
   survive.
2. ``custom_answers`` rows for converted period signups are deleted. That FK
   is NO ACTION, so the signup delete would otherwise fail outright.
   ``custom_answers`` is the legacy pre-Phase-22 answer store, written by no
   live code path (only a test helper references it); the Phase 22 store is
   ``signup_responses``, which is preserved — see below.
3. ``sent_notifications`` rows for converted period signups are deleted (also
   NO ACTION). These are per-signup reminder-dedup markers, not user data;
   the worst case is one duplicate reminder for a signup mid-flight.

NOT a casualty: ``signup_responses`` (Phase 22 custom form answers) are
*repointed* to the new shift signup rather than dropped. The table gains the
same dual anchor as ``magic_link_tokens`` and ``sent_notifications``, because
without it the custom form would stop collecting answers for period signups
altogether — those no longer have a ``Signup`` row to hang off.

Revision ID: 0037_add_shifts
Revises: 0036_add_site_settings_contact_email
"""
import sqlalchemy as sa
from alembic import op

revision = "0037_add_shifts"
down_revision = "0036_add_site_settings_contact_email"
branch_labels = None
depends_on = None


# Display timezone for generated shift names. Slot times are stored UTC; naming
# a shift "Tue 16:00" when the event runs at 9am Pacific would be useless to
# the organizers reading it.
_DISPLAY_TZ = "America/Los_Angeles"

# Statuses that represent a lifecycle position (map 1:1 onto shift_signups)
# versus an attendance outcome (become a confirmed shift signup plus a
# session_attendance row).
_LIFECYCLE = ("pending", "confirmed", "waitlisted", "cancelled")
_OUTCOMES = ("checked_in", "attended", "no_show")


def upgrade() -> None:
    # ---- 1. New tables -----------------------------------------------------
    op.create_table(
        "shifts",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("capacity > 0", name="ck_shifts_capacity_positive"),
    )
    op.create_index(
        "ix_shifts_event_id_sort_order", "shifts", ["event_id", "sort_order"]
    )

    op.create_table(
        "shift_signups",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "shift_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shifts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "volunteer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("volunteers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Reuses the existing signupstatus enum — creating a new Postgres enum
        # would extend the known enum-downgrade bug for no benefit.
        sa.Column(
            "status",
            sa.dialects.postgresql.ENUM(name="signupstatus", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "volunteer_id", "shift_id", name="uq_shift_signups_volunteer_id_shift_id"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'waitlisted', 'cancelled')",
            name="ck_shift_signups_status_is_lifecycle",
        ),
    )
    op.create_index(
        "ix_shift_signups_shift_id_status", "shift_signups", ["shift_id", "status"]
    )
    op.create_index(
        "ix_shift_signups_waitlist_order",
        "shift_signups",
        ["shift_id", "timestamp", "id"],
    )

    op.create_table(
        "session_attendance",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "shift_signup_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shift_signups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "slot_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("slots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.dialects.postgresql.ENUM(name="signupstatus", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "shift_signup_id", "slot_id", name="uq_session_attendance_signup_slot"
        ),
        sa.CheckConstraint(
            "status IN ('checked_in', 'attended', 'no_show')",
            name="ck_session_attendance_status_is_outcome",
        ),
    )

    # ---- 2. Slot gains shift membership + naming/ordering -------------------
    op.add_column(
        "slots",
        sa.Column(
            "shift_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shifts.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column("slots", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column(
        "slots",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_slots_shift_id_sort_order", "slots", ["shift_id", "sort_order"]
    )

    # ---- 3. magic_link_tokens: two possible anchors ------------------------
    # A shift-only batch has no Signup row to anchor a confirm token to.
    op.alter_column("magic_link_tokens", "signup_id", nullable=True)
    op.add_column(
        "magic_link_tokens",
        sa.Column(
            "shift_signup_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shift_signups.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_magic_link_tokens_exactly_one_anchor",
        "magic_link_tokens",
        "(signup_id IS NOT NULL AND shift_signup_id IS NULL) OR "
        "(signup_id IS NULL AND shift_signup_id IS NOT NULL)",
    )

    # ---- 3b. sent_notifications: the same two anchors -----------------------
    # The dedup key is (anchor, kind). A shift signup gets reminders and
    # reschedule notices just like a slot signup did, so it needs its own
    # anchor and its own unique index — one partial index per anchor, because
    # a single index over two nullable columns would let (NULL, kind) rows
    # repeat and silently disable dedup.
    op.alter_column("sent_notifications", "signup_id", nullable=True)
    op.add_column(
        "sent_notifications",
        sa.Column(
            "shift_signup_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shift_signups.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_sent_notifications_exactly_one_anchor",
        "sent_notifications",
        "(signup_id IS NOT NULL AND shift_signup_id IS NULL) OR "
        "(signup_id IS NULL AND shift_signup_id IS NOT NULL)",
    )
    op.drop_index("uq_sent_notifications_signup_kind", table_name="sent_notifications")
    op.create_index(
        "uq_sent_notifications_signup_kind",
        "sent_notifications",
        ["signup_id", "kind"],
        unique=True,
        postgresql_where=sa.text("signup_id IS NOT NULL"),
    )
    op.create_index(
        "uq_sent_notifications_shift_signup_kind",
        "sent_notifications",
        ["shift_signup_id", "kind"],
        unique=True,
        postgresql_where=sa.text("shift_signup_id IS NOT NULL"),
    )

    # ---- 3c. signup_responses: the same two anchors -------------------------
    # Phase 22 form answers must follow the commitment, so this anchor is what
    # keeps the custom form working for period signups at all.
    op.alter_column("signup_responses", "signup_id", nullable=True)
    op.add_column(
        "signup_responses",
        sa.Column(
            "shift_signup_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shift_signups.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_signup_responses_exactly_one_anchor",
        "signup_responses",
        "(signup_id IS NOT NULL AND shift_signup_id IS NULL) OR "
        "(signup_id IS NULL AND shift_signup_id IS NOT NULL)",
    )
    op.drop_index("uq_signup_responses_signup_field", table_name="signup_responses")
    op.create_index(
        "uq_signup_responses_signup_field",
        "signup_responses",
        ["signup_id", "field_id"],
        unique=True,
        postgresql_where=sa.text("signup_id IS NOT NULL"),
    )
    op.create_index(
        "uq_signup_responses_shift_signup_field",
        "signup_responses",
        ["shift_signup_id", "field_id"],
        unique=True,
        postgresql_where=sa.text("shift_signup_id IS NOT NULL"),
    )

    # ---- 4. Backfill: one single-session shift per existing period slot -----
    # A temporary provenance column lets the slot → shift mapping be set with
    # plain set-based UPDATEs instead of a row-by-row loop.
    op.add_column(
        "shifts",
        sa.Column(
            "migrated_from_slot_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        f"""
        INSERT INTO shifts (
            event_id, name, sort_order, capacity, current_count,
            migrated_from_slot_id
        )
        SELECT
            s.event_id,
            -- e.g. "Tue 9:00-10:30", in the display timezone
            to_char(s.start_time AT TIME ZONE '{_DISPLAY_TZ}', 'Dy')
                || ' '
                || to_char(s.start_time AT TIME ZONE '{_DISPLAY_TZ}', 'FMHH24:MI')
                || '-'
                || to_char(s.end_time AT TIME ZONE '{_DISPLAY_TZ}', 'FMHH24:MI'),
            row_number() OVER (
                PARTITION BY s.event_id ORDER BY s.date, s.start_time, s.id
            ) - 1,
            GREATEST(s.capacity, 1),
            s.current_count,
            s.id
        FROM slots s
        WHERE s.slot_type = 'period'
        """
    )

    op.execute(
        """
        UPDATE slots
        SET shift_id = sh.id,
            name = sh.name,
            sort_order = 0
        FROM shifts sh
        WHERE sh.migrated_from_slot_id = slots.id
        """
    )

    # ---- 5. Convert period signups ----------------------------------------
    op.add_column(
        "shift_signups",
        sa.Column(
            "migrated_from_signup_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    lifecycle_list = ", ".join(f"'{s}'" for s in _LIFECYCLE)
    outcome_list = ", ".join(f"'{s}'" for s in _OUTCOMES)

    # Lifecycle statuses map 1:1, preserving status and timestamp so waitlist
    # order (timestamp ASC, id ASC) survives the move up a level.
    op.execute(
        f"""
        INSERT INTO shift_signups (
            shift_id, volunteer_id, status, timestamp,
            reminder_24h_sent_at, reminder_1h_sent_at, migrated_from_signup_id
        )
        SELECT
            sl.shift_id, su.volunteer_id, su.status,
            COALESCE(su.timestamp, now()),
            su.reminder_24h_sent_at, su.reminder_1h_sent_at, su.id
        FROM signups su
        JOIN slots sl ON sl.id = su.slot_id
        WHERE sl.slot_type = 'period'
          AND sl.shift_id IS NOT NULL
          AND su.status::text IN ({lifecycle_list})
        """
    )

    # Attendance outcomes become a CONFIRMED shift signup (they were confirmed
    # to have progressed this far) plus a session_attendance row carrying the
    # outcome. Commitment and attendance are separate concerns now.
    op.execute(
        f"""
        INSERT INTO shift_signups (
            shift_id, volunteer_id, status, timestamp,
            reminder_24h_sent_at, reminder_1h_sent_at, migrated_from_signup_id
        )
        SELECT
            sl.shift_id, su.volunteer_id, 'confirmed'::signupstatus,
            COALESCE(su.timestamp, now()),
            su.reminder_24h_sent_at, su.reminder_1h_sent_at, su.id
        FROM signups su
        JOIN slots sl ON sl.id = su.slot_id
        WHERE sl.slot_type = 'period'
          AND sl.shift_id IS NOT NULL
          AND su.status::text IN ({outcome_list})
        """
    )

    op.execute(
        f"""
        INSERT INTO session_attendance (
            shift_signup_id, slot_id, checked_in_at, status
        )
        SELECT ss.id, su.slot_id, su.checked_in_at, su.status
        FROM shift_signups ss
        JOIN signups su ON su.id = ss.migrated_from_signup_id
        WHERE su.status::text IN ({outcome_list})
        """
    )

    # ---- 6. Carry the form answers over, then drop the old signups ---------
    # Phase 22 responses move to the new commitment. This must happen BEFORE
    # the signup delete, which would otherwise cascade them away.
    op.execute(
        """
        UPDATE signup_responses sr
        SET shift_signup_id = ss.id, signup_id = NULL
        FROM shift_signups ss
        WHERE ss.migrated_from_signup_id = sr.signup_id
        """
    )

    # custom_answers and sent_notifications are NO ACTION, so they must go
    # first or the delete fails. magic_link_tokens cascade. See the
    # accepted-casualties note at the top.
    op.execute(
        """
        DELETE FROM custom_answers
        WHERE signup_id IN (
            SELECT migrated_from_signup_id FROM shift_signups
            WHERE migrated_from_signup_id IS NOT NULL
        )
        """
    )
    op.execute(
        """
        DELETE FROM sent_notifications
        WHERE signup_id IN (
            SELECT migrated_from_signup_id FROM shift_signups
            WHERE migrated_from_signup_id IS NOT NULL
        )
        """
    )
    op.execute(
        """
        DELETE FROM signups
        WHERE id IN (
            SELECT migrated_from_signup_id FROM shift_signups
            WHERE migrated_from_signup_id IS NOT NULL
        )
        """
    )

    # ---- 7. Drop provenance columns, then lock the invariant ---------------
    op.drop_column("shift_signups", "migrated_from_signup_id")
    op.drop_column("shifts", "migrated_from_slot_id")

    # Added only now: before the backfill every period slot had a NULL
    # shift_id and this would have failed.
    op.create_check_constraint(
        "ck_slots_shift_membership_matches_type",
        "slots",
        "(slot_type = 'orientation' AND shift_id IS NULL) OR "
        "(slot_type = 'period' AND shift_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Best-effort reverse: rebuild period Signup rows from shift signups.

    Only single-session shifts can be represented as slot signups, so a shift
    that has since gained a second session cannot round-trip — those signups
    are dropped rather than silently duplicated across sessions. Creates no
    Postgres enums, so the known enum-downgrade bug is not extended.
    """
    op.drop_constraint(
        "ck_slots_shift_membership_matches_type", "slots", type_="check"
    )

    # Rebuild slot-level signups for shifts that still have exactly one session.
    op.execute(
        """
        INSERT INTO signups (
            id, volunteer_id, slot_id, status, timestamp,
            reminder_24h_sent_at, reminder_1h_sent_at, checked_in_at
        )
        SELECT
            gen_random_uuid(),
            ss.volunteer_id,
            sole.slot_id,
            COALESCE(sa.status, ss.status),
            ss.timestamp,
            ss.reminder_24h_sent_at,
            ss.reminder_1h_sent_at,
            sa.checked_in_at
        FROM shift_signups ss
        JOIN (
            -- array_agg, not min(): Postgres has no min(uuid) aggregate.
            SELECT shift_id, (array_agg(id))[1] AS slot_id, count(*) AS n
            FROM slots
            WHERE shift_id IS NOT NULL
            GROUP BY shift_id
        ) sole ON sole.shift_id = ss.shift_id AND sole.n = 1
        LEFT JOIN session_attendance sa
               ON sa.shift_signup_id = ss.id AND sa.slot_id = sole.slot_id
        ON CONFLICT (volunteer_id, slot_id) DO NOTHING
        """
    )

    # Repoint the form answers back onto the rebuilt slot signups, matching on
    # (volunteer, sole session). Answers whose shift gained a second session
    # have no slot signup to land on and go with the anchor column.
    op.execute(
        """
        UPDATE signup_responses sr
        SET signup_id = su.id, shift_signup_id = NULL
        FROM shift_signups ss
        JOIN (
            SELECT shift_id, (array_agg(id))[1] AS slot_id, count(*) AS n
            FROM slots WHERE shift_id IS NOT NULL GROUP BY shift_id
        ) sole ON sole.shift_id = ss.shift_id AND sole.n = 1
        JOIN signups su
          ON su.volunteer_id = ss.volunteer_id AND su.slot_id = sole.slot_id
        WHERE sr.shift_signup_id = ss.id
        """
    )
    op.drop_constraint(
        "ck_signup_responses_exactly_one_anchor", "signup_responses", type_="check"
    )
    op.execute("DELETE FROM signup_responses WHERE signup_id IS NULL")
    op.drop_index(
        "uq_signup_responses_shift_signup_field", table_name="signup_responses"
    )
    op.drop_index("uq_signup_responses_signup_field", table_name="signup_responses")
    op.drop_column("signup_responses", "shift_signup_id")
    op.alter_column("signup_responses", "signup_id", nullable=False)
    op.create_index(
        "uq_signup_responses_signup_field",
        "signup_responses",
        ["signup_id", "field_id"],
        unique=True,
    )

    op.drop_constraint(
        "ck_sent_notifications_exactly_one_anchor", "sent_notifications", type_="check"
    )
    # Dedup markers for shift signups have no slot-level equivalent, so they
    # go; the worst case after a downgrade is one duplicate reminder.
    op.execute("DELETE FROM sent_notifications WHERE signup_id IS NULL")
    op.drop_index(
        "uq_sent_notifications_shift_signup_kind", table_name="sent_notifications"
    )
    op.drop_index("uq_sent_notifications_signup_kind", table_name="sent_notifications")
    op.drop_column("sent_notifications", "shift_signup_id")
    op.alter_column("sent_notifications", "signup_id", nullable=False)
    op.create_index(
        "uq_sent_notifications_signup_kind",
        "sent_notifications",
        ["signup_id", "kind"],
        unique=True,
    )

    op.drop_constraint(
        "ck_magic_link_tokens_exactly_one_anchor", "magic_link_tokens", type_="check"
    )
    # Unanchored tokens (shift-only batches) cannot survive a column that is
    # about to become NOT NULL again.
    op.execute("DELETE FROM magic_link_tokens WHERE signup_id IS NULL")
    op.drop_column("magic_link_tokens", "shift_signup_id")
    op.alter_column("magic_link_tokens", "signup_id", nullable=False)

    op.drop_index("ix_slots_shift_id_sort_order", table_name="slots")
    op.drop_column("slots", "sort_order")
    op.drop_column("slots", "name")
    op.drop_column("slots", "shift_id")

    op.drop_table("session_attendance")
    op.drop_index("ix_shift_signups_waitlist_order", table_name="shift_signups")
    op.drop_index("ix_shift_signups_shift_id_status", table_name="shift_signups")
    op.drop_table("shift_signups")
    op.drop_index("ix_shifts_event_id_sort_order", table_name="shifts")
    op.drop_table("shifts")
