"""Phase 08 v1.1: schema realignment — volunteers, event/slot columns, signup FK rewire,
magic-link extensions, prereq retirement.

Revision ID: 0009_phase08_v1_1_schema_realignment
Revises: 0008_phase7_user_deleted_at
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_phase08_v1_1_schema_realignment"
down_revision: Union[str, None] = "0008_phase7_user_deleted_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Section 1 — Create `volunteers` table (R08-01)
    # -----------------------------------------------------------------------
    op.create_table(
        "volunteers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_volunteers_email"),
    )
    op.create_index("ix_volunteers_email", "volunteers", ["email"])

    # -----------------------------------------------------------------------
    # Section 2 — Drop dev data that will be orphaned by FK rewire (D-04)
    # Dev data is throwaway per locked decision D-04. Clear signups +
    # magic_link_tokens so the FK rewire and NOT NULL columns don't trip on
    # pre-existing rows.
    # -----------------------------------------------------------------------
    op.execute("DELETE FROM magic_link_tokens")
    op.execute("DELETE FROM signups")

    # -----------------------------------------------------------------------
    # Section 3 — events: new columns + drop module_slug FK (R08-02, D-07)
    # FK constraint name captured 2026-04-09 via `\d events`:
    #   events_module_slug_fkey  (references module_templates.slug)
    # -----------------------------------------------------------------------
    quarter_enum = postgresql.ENUM(
        "winter", "spring", "summer", "fall",
        name="quarter",
        create_type=False,
    )
    quarter_enum.create(op.get_bind(), checkfirst=True)

    # Drop the existing FK from events.module_slug -> module_templates.slug.
    op.drop_constraint("events_module_slug_fkey", "events", type_="foreignkey")

    # Add new structured columns.
    op.add_column(
        "events",
        sa.Column(
            "quarter",
            postgresql.ENUM("winter", "spring", "summer", "fall",
                            name="quarter", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("events", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("week_number", sa.Integer(), nullable=True))
    op.add_column("events", sa.Column("school", sa.String(length=255), nullable=True))
    # events.module_slug column stays — only the FK constraint was dropped.

    # -----------------------------------------------------------------------
    # Section 4 — slots: new columns (R08-03, D-02)
    # Adds slot_type (enum), date (DATE NOT NULL), and location (nullable).
    # start_time and end_time DateTime columns stay — Phase 3 organizer roster uses them.
    # -----------------------------------------------------------------------
    slot_type_enum = postgresql.ENUM(
        "orientation", "period",
        name="slottype",
        create_type=False,
    )
    slot_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "slots",
        sa.Column(
            "slot_type",
            postgresql.ENUM("orientation", "period", name="slottype", create_type=False),
            nullable=False,
            server_default="period",  # harmless default; seed data overrides
        ),
    )
    op.add_column(
        "slots",
        sa.Column(
            "date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),  # per D-02/D-04 dev data is throwaway
        ),
    )
    op.add_column("slots", sa.Column("location", sa.String(length=255), nullable=True))

    # -----------------------------------------------------------------------
    # Section 5 — signups: drop user_id FK, add volunteer_id FK with RESTRICT
    # (R08-04, D-01)
    # RESTRICT per locked decision D-01 — attendance history is the source of
    # truth; forces cancel-then-delete workflow for volunteers.
    # -----------------------------------------------------------------------
    # Drop the old unique constraint that references user_id.
    op.drop_constraint("uq_signups_user_id_slot_id", "signups", type_="unique")
    # Drop the FK column (Postgres drops the FK constraint implicitly with the column).
    op.drop_column("signups", "user_id")

    # Add new FK to volunteers.
    op.add_column(
        "signups",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_signups_volunteer_id",
        "signups", "volunteers",
        ["volunteer_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_signups_volunteer_id_slot_id",
        "signups",
        ["volunteer_id", "slot_id"],
    )

    # -----------------------------------------------------------------------
    # Section 6 — magic_link_tokens: add volunteer_id FK + extend purpose enum
    # (R08-05, D-03)
    # -----------------------------------------------------------------------
    op.add_column(
        "magic_link_tokens",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_magic_link_tokens_volunteer_id",
        "magic_link_tokens", "volunteers",
        ["volunteer_id"], ["id"],
        ondelete="CASCADE",  # tokens are ephemeral; cascade is fine here
    )

    # Extend magiclinkpurpose enum. ALTER TYPE ADD VALUE cannot run inside a
    # transaction, so use an autocommit_block. Postgres cannot remove enum values,
    # so the downgrade of this step is intentionally a no-op (documented below).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_confirm'"
        )
        op.execute(
            "ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'signup_manage'"
        )

    # -----------------------------------------------------------------------
    # Section 7 — Retire prereq_overrides (R08-06, D-05)
    # -----------------------------------------------------------------------
    op.drop_table("prereq_overrides")
    op.drop_column("module_templates", "prereq_slugs")


def downgrade() -> None:
    # -----------------------------------------------------------------------
    # Section 7 reverse — restore prereq_overrides table and prereq_slugs column
    # Column shapes copied exactly from migration
    # 0005_phase4_prereq_module_templates_and_overrides.py
    # -----------------------------------------------------------------------
    op.add_column(
        "module_templates",
        sa.Column(
            "prereq_slugs",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "prereq_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "module_slug",
            sa.String(),
            sa.ForeignKey("module_templates.slug"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(reason) >= 10", name="prereq_overrides_reason_min_len"
        ),
    )

    # -----------------------------------------------------------------------
    # Section 6 reverse
    # NOTE: Postgres has no DROP VALUE. signup_confirm/signup_manage remain in
    # the magiclinkpurpose type after downgrade. This is a known Postgres
    # limitation, not a bug.
    # -----------------------------------------------------------------------
    op.drop_constraint(
        "fk_magic_link_tokens_volunteer_id", "magic_link_tokens", type_="foreignkey"
    )
    op.drop_column("magic_link_tokens", "volunteer_id")

    # -----------------------------------------------------------------------
    # Section 5 reverse
    # -----------------------------------------------------------------------
    op.drop_constraint("uq_signups_volunteer_id_slot_id", "signups", type_="unique")
    op.drop_constraint("fk_signups_volunteer_id", "signups", type_="foreignkey")
    op.drop_column("signups", "volunteer_id")
    # ASSUMPTION: dev data is throwaway (D-04). Any signup rows that were
    # created via the volunteer-keyed schema after upgrade have no user_id
    # to fall back on, so we wipe the table before re-adding the NOT NULL
    # user_id column. This is safe per locked decision D-04.
    op.execute("DELETE FROM signups")
    op.add_column(
        "signups",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    # Re-add the original FK + unique constraint
    op.create_foreign_key(
        "signups_user_id_fkey", "signups", "users",
        ["user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_signups_user_id_slot_id", "signups", ["user_id", "slot_id"],
    )

    # -----------------------------------------------------------------------
    # Section 4 reverse
    # -----------------------------------------------------------------------
    op.drop_column("slots", "location")
    op.drop_column("slots", "date")
    op.drop_column("slots", "slot_type")
    sa.Enum(name="slottype").drop(op.get_bind(), checkfirst=True)

    # -----------------------------------------------------------------------
    # Section 3 reverse
    # -----------------------------------------------------------------------
    op.drop_column("events", "school")
    op.drop_column("events", "week_number")
    op.drop_column("events", "year")
    op.drop_column("events", "quarter")
    sa.Enum(name="quarter").drop(op.get_bind(), checkfirst=True)
    # Recreate the FK on events.module_slug -> module_templates.slug
    op.create_foreign_key(
        "events_module_slug_fkey", "events", "module_templates",
        ["module_slug"], ["slug"],
    )

    # -----------------------------------------------------------------------
    # Section 1 reverse (volunteers table last because signups FK'd into it)
    # -----------------------------------------------------------------------
    op.drop_index("ix_volunteers_email", table_name="volunteers")
    op.drop_table("volunteers")
