"""Drop module_templates.type and the moduletype enum.

PR #51: there is only one kind of module now. The seminar value was never
read by any code path, and orientation stopped being a *template* concept
when the CSV import pipeline was removed — orientation lives on slots
(SlotType.ORIENTATION) and credit grouping lives on family_key. Existing
orientation-typed rows keep their family_key, so credit resolution
(family_for_event) is unaffected.

Revision ID: 0031_drop_module_template_type
Revises: 0030_drop_csv_imports
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_drop_module_template_type"
down_revision = "0030_drop_csv_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("module_templates", "type")
    sa.Enum(name="moduletype").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Recreate the enum and the column as 0013 built them. The per-row type
    # values are gone for good — every row comes back as 'module'.
    moduletype = postgresql.ENUM(
        "seminar", "orientation", "module",
        name="moduletype",
        create_type=False,
    )
    moduletype.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "module_templates",
        sa.Column("type", moduletype, nullable=False, server_default="module"),
    )
