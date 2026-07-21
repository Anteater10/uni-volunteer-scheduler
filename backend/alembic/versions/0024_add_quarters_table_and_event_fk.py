"""Add quarters table and events.quarter_id FK (issue #24).

Quarters are admin-entered rows — (season, year, label) + inclusive
start/end dates transcribed from the UCSB academic calendar. Summer
Sessions A/B are separate rows distinguished by label. Weeks derive
purely from the stored range.

This migration seeds NOTHING and backfills NOTHING: dates are never
guessed. Entering a quarter through the admin UI links matching events
(quarter_service.relink_events_for_quarter).

Revision ID: 0024_add_quarters_table_and_event_fk
Revises: 0023_add_copilot_feedback_tables
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_add_quarters_table_and_event_fk"
down_revision = "0023_add_copilot_feedback_tables"
branch_labels = None
depends_on = None


def upgrade():
    # The overlap exclusion below is a gist constraint over a daterange —
    # requires btree_gist.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # PG enum type `quarter` normally exists already (0009); checkfirst keeps
    # this idempotent for fresh databases where 0009 created it moments ago.
    quarter_enum = postgresql.ENUM(
        "winter", "spring", "summer", "fall", name="quarter", create_type=False
    )
    quarter_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "quarters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("season", quarter_enum, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("season", "year", "label", name="uq_quarters_season_year_label"),
        sa.CheckConstraint("start_date < end_date", name="ck_quarters_start_before_end"),
    )
    # end_date is inclusive, hence the '[]' bounds.
    op.execute(
        "ALTER TABLE quarters ADD CONSTRAINT ex_quarters_no_overlap "
        "EXCLUDE USING gist (daterange(start_date, end_date, '[]') WITH &&)"
    )

    op.add_column(
        "events",
        sa.Column("quarter_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_events_quarter_id", "events", "quarters", ["quarter_id"], ["id"]
    )
    op.create_index("ix_events_quarter_id", "events", ["quarter_id"])


def downgrade():
    op.drop_index("ix_events_quarter_id", table_name="events")
    op.drop_constraint("fk_events_quarter_id", "events", type_="foreignkey")
    op.drop_column("events", "quarter_id")
    op.drop_table("quarters")
    # The `quarter` enum type is shared with events.quarter — do not drop.
    # btree_gist is left installed; other objects may rely on it.
