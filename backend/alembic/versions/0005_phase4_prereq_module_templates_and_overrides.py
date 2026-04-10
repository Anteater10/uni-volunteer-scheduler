"""Phase 4: prereq stub schema. module_templates is a minimal stub; phase 5 will ADD columns (never rename). Forward compatible.

Revision ID: 0005_phase4_prereq_module_templates_and_overrides
Revises: 0004_phase3_check_in_state_machine_schema
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "0005_phase4_prereq_module_templates_and_overrides"
down_revision: Union[str, Sequence[str], None] = "0004_phase3_check_in_state_machine_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create module_templates stub table
    op.create_table(
        "module_templates",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "prereq_slugs",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # 2. Create prereq_overrides table
    op.create_table(
        "prereq_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
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
            UUID(as_uuid=True),
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

    # 3. Add module_slug FK to events
    op.add_column(
        "events",
        sa.Column(
            "module_slug",
            sa.String(),
            sa.ForeignKey("module_templates.slug"),
            nullable=True,
        ),
    )

    # 4. Seed placeholder module templates
    # TODO(data): replace with real Sci Trek modules
    module_templates = sa.table(
        "module_templates",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("prereq_slugs", sa.ARRAY(sa.String)),
    )
    op.bulk_insert(
        module_templates,
        [
            {"slug": "orientation", "name": "Orientation", "prereq_slugs": []},
            {
                "slug": "intro-bio",
                "name": "Intro to Biology",
                "prereq_slugs": ["orientation"],
            },
            {
                "slug": "intro-chem",
                "name": "Intro to Chemistry",
                "prereq_slugs": ["orientation"],
            },
        ],
    )


def downgrade() -> None:
    op.drop_column("events", "module_slug")
    op.drop_table("prereq_overrides")
    op.drop_table("module_templates")
