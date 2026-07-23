"""Quarter deletion must not be blocked by orientation-credit metadata.

``orientation_credits.quarter_id`` is display metadata only (issue #30) —
the credit is permanent per (email, family) regardless. Migration 0026 added
the FK without an ON DELETE action, so deleting a quarter that credits
reference raised an FK violation (a 500 for the admin) even though
``delete_quarter`` only guards against linked *events*. Recreate the FK as
ON DELETE SET NULL: the delete succeeds and the "earned in" label clears.

Revision ID: 0027_orientation_credit_quarter_set_null
Revises: 0026_orientation_credit_quarter_scope
"""
from alembic import op

revision = "0027_orientation_credit_quarter_set_null"
down_revision = "0026_orientation_credit_quarter_scope"
branch_labels = None
depends_on = None

_FK = "fk_orientation_credits_quarter_id"


def upgrade():
    op.drop_constraint(_FK, "orientation_credits", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "orientation_credits",
        "quarters",
        ["quarter_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(_FK, "orientation_credits", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "orientation_credits",
        "quarters",
        ["quarter_id"],
        ["id"],
    )
