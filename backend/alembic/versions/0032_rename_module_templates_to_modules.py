"""Rename the module_templates table to modules.

PR #51: the UI has called these "Modules" since Phase 17; the internal
name catches up. The table has no foreign keys in either direction
(events.module_slug is a plain string — the FK was dropped in 0009), so
this is a bare rename plus the primary-key index for tidiness.

Revision ID: 0032_rename_module_templates_to_modules
Revises: 0031_drop_module_template_type
"""

from alembic import op

revision = "0032_rename_module_templates_to_modules"
down_revision = "0031_drop_module_template_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("module_templates", "modules")
    op.execute("ALTER INDEX module_templates_pkey RENAME TO modules_pkey")


def downgrade() -> None:
    op.execute("ALTER INDEX modules_pkey RENAME TO module_templates_pkey")
    op.rename_table("modules", "module_templates")
