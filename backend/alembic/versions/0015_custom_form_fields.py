"""Phase 22: custom form fields

Revision ID: 0015_custom_form_fields
Revises: 0014_orientation_credit
Create Date: 2026-04-17

- Add `module_templates.default_form_schema` JSONB NOT NULL DEFAULT '[]'::jsonb.
- Add `events.form_schema` JSONB nullable (null means "use template default").
- Create `signup_responses` table with UNIQUE(signup_id, field_id) for
  per-signup custom-field answers.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0015_custom_form_fields"
down_revision = "0014_orientation_credit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add default_form_schema to module_templates (JSONB not null default '[]')
    op.add_column(
        "module_templates",
        sa.Column(
            "default_form_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 2. Add form_schema to events (JSONB nullable — null = use template default)
    op.add_column(
        "events",
        sa.Column(
            "form_schema",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("NULL"),
        ),
    )

    # 3. Create signup_responses table
    op.create_table(
        "signup_responses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "signup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_id", sa.String(length=128), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", postgresql.JSONB(), nullable=True),
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
    op.create_index(
        "uq_signup_responses_signup_field",
        "signup_responses",
        ["signup_id", "field_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_signup_responses_signup_field", table_name="signup_responses"
    )
    op.drop_table("signup_responses")
    op.drop_column("events", "form_schema")
    op.drop_column("module_templates", "default_form_schema")
