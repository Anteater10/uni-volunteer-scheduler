"""Phase 17 Plan 01: add type enum + session_count + fix orientation duration

Revision ID: 0013_add_type_session_count_fix_orientation_duration
Revises: 0012_soft_delete_seed_module_templates_and_normalize_audit_kinds
Create Date: 2026-04-16

- Add 'moduletype' enum (seminar, orientation, module) with server_default='module'
- Add 'session_count' integer column with server_default='1'
- Fix orientation template duration_minutes from 60 to 120 (domain rule)
- Backfill orientation row type = 'orientation'
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_add_type_session_count_fix_orientation_duration"
down_revision = "0012_soft_delete_seed_module_templates_and_normalize_audit_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create moduletype enum
    moduletype = sa.Enum("seminar", "orientation", "module", name="moduletype")
    moduletype.create(op.get_bind())

    # 2. Add type column with server_default='module'
    op.add_column(
        "module_templates",
        sa.Column(
            "type",
            sa.Enum("seminar", "orientation", "module", name="moduletype", create_type=False),
            nullable=False,
            server_default="module",
        ),
    )

    # 3. Add session_count column with server_default='1'
    op.add_column(
        "module_templates",
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="1"),
    )

    # 4. Fix orientation duration (60 -> 120) — update regardless of deleted_at status
    op.execute("UPDATE module_templates SET duration_minutes = 120 WHERE slug = 'orientation'")

    # 5. Backfill type for orientation row
    op.execute("UPDATE module_templates SET type = 'orientation' WHERE slug = 'orientation'")


def downgrade() -> None:
    # 1. Revert orientation duration
    op.execute("UPDATE module_templates SET duration_minutes = 60 WHERE slug = 'orientation'")

    # 2. Drop session_count column
    op.drop_column("module_templates", "session_count")

    # 3. Drop type column
    op.drop_column("module_templates", "type")

    # 4. Drop moduletype enum type (fixes latent bug pattern per CLAUDE.md)
    sa.Enum(name="moduletype").drop(op.get_bind())
