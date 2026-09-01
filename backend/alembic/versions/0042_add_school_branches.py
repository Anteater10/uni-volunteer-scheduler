"""Classify modules and admins for routed signup notifications."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_add_school_branches"
down_revision: Union[str, None] = "0041_login_failure_lockout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BRANCH_VALUES = ("high_school", "middle_school", "both")


def upgrade() -> None:
    branch_enum = postgresql.ENUM(*BRANCH_VALUES, name="schoolbranch")
    branch_enum.create(op.get_bind(), checkfirst=True)
    column_enum = postgresql.ENUM(
        *BRANCH_VALUES, name="schoolbranch", create_type=False
    )

    op.add_column(
        "modules",
        sa.Column(
            "school_branch",
            column_enum,
            nullable=False,
            server_default=sa.text("'both'::schoolbranch"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("school_branch", column_enum, nullable=True),
    )
    op.execute("UPDATE users SET school_branch = 'both' WHERE role = 'admin'")
    op.create_check_constraint(
        "ck_users_school_branch_admin_only",
        "users",
        "(role = 'admin' AND school_branch IS NOT NULL) OR "
        "(role <> 'admin' AND school_branch IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_school_branch_admin_only", "users", type_="check"
    )
    op.drop_column("users", "school_branch")
    op.drop_column("modules", "school_branch")
    postgresql.ENUM(name="schoolbranch").drop(op.get_bind(), checkfirst=True)
