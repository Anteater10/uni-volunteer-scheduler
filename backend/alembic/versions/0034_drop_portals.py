"""Drop the portals and portal_events tables.

The portals feature (curated public event-collection links) was never
adopted — both tables have 0 rows in the dev DB and no UI entry point
mattered. Its public `GET /portals/{slug}` endpoint also leaked the staff
`EventRead` schema (owner_id + staff-only fields) to anonymous callers, a
security finding fixed by removing the feature outright (router, models,
schemas, frontend pages).

Revision ID: 0034_drop_portals
Revises: 0033_add_event_completed_at
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0034_drop_portals"
down_revision = "0033_add_event_completed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("portal_events")
    op.drop_index(op.f("ix_portals_slug"), table_name="portals")
    op.drop_table("portals")


def downgrade() -> None:
    # Recreate both tables exactly as 2465a60b9dbc (initial schema) built
    # them, with the timezone-aware created_at applied by
    # 0002_phase0_schema_hardening — the two migrations that shaped the
    # live schema before this revision.
    op.create_table(
        "portals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_portals_slug"), "portals", ["slug"], unique=True)

    op.create_table(
        "portal_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portals.id"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "portal_id", "event_id", name="uq_portal_events_portal_id_event_id"
        ),
    )
