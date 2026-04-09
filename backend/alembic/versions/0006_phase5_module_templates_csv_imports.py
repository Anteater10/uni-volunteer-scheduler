"""Phase 5: extend module_templates (capacity, duration, materials, metadata, soft delete) + csv_imports table.

Revision ID: 0006_phase5_module_templates_csv_imports
Revises: 0005_phase4_prereq_module_templates_and_overrides
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0006_phase5_module_templates_csv_imports"
down_revision: Union[str, Sequence[str], None] = "0005_phase4_prereq_module_templates_and_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend module_templates with new columns
    op.add_column(
        "module_templates",
        sa.Column("default_capacity", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "module_templates",
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="90"),
    )
    op.add_column(
        "module_templates",
        sa.Column(
            "materials",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "module_templates",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "module_templates",
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "module_templates",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Create csvimportstatus enum explicitly (and only once) — we reuse the
    # same ENUM instance in the column below with create_type=False so
    # op.create_table does not try to CREATE TYPE a second time.
    csvimportstatus = postgresql.ENUM(
        "pending", "processing", "ready", "committed", "failed",
        name="csvimportstatus",
        create_type=False,
    )
    csvimportstatus.create(op.get_bind(), checkfirst=True)

    # 3. Create csv_imports table
    op.create_table(
        "csv_imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("raw_csv_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            csvimportstatus,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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

    # 4. Seed additional module templates (phase 4 only had 3)
    op.execute("""
    INSERT INTO module_templates (slug, name, prereq_slugs, default_capacity, duration_minutes, materials, description)
    VALUES
      ('intro-physics', 'Intro to Physics', '{orientation}', 20, 90, '{}', 'Physics module -- TODO(data)'),
      ('intro-astro', 'Intro to Astronomy', '{orientation}', 20, 90, '{}', 'Astronomy module -- TODO(data)')
    ON CONFLICT (slug) DO NOTHING;
    """)

    # Update existing templates with descriptions
    op.execute("""
    UPDATE module_templates
    SET description = 'First-time volunteer orientation -- TODO(data)',
        default_capacity = 30,
        duration_minutes = 60
    WHERE slug = 'orientation' AND description IS NULL;
    """)
    op.execute("""
    UPDATE module_templates SET description = 'Biology module -- TODO(data)' WHERE slug = 'intro-bio' AND description IS NULL;
    """)
    op.execute("""
    UPDATE module_templates SET description = 'Chemistry module -- TODO(data)' WHERE slug = 'intro-chem' AND description IS NULL;
    """)


def downgrade() -> None:
    op.drop_table("csv_imports")
    sa.Enum(name="csvimportstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_column("module_templates", "deleted_at")
    op.drop_column("module_templates", "metadata")
    op.drop_column("module_templates", "description")
    op.drop_column("module_templates", "materials")
    op.drop_column("module_templates", "duration_minutes")
    op.drop_column("module_templates", "default_capacity")
    op.execute("DELETE FROM module_templates WHERE slug IN ('intro-physics', 'intro-astro');")
