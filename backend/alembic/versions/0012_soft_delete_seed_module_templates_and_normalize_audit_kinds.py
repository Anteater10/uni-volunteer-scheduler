"""Phase 16 Plan 01: soft-delete seed module templates + normalize audit kinds

Revision ID: 0012_soft_delete_seed_module_templates_and_normalize_audit_kinds
Revises: 0011_add_is_active_and_last_login_to_users
Create Date: 2026-04-15

Per Phase 16 Wave 0 (D-20, D-35):
- Retire the 5 seed module templates (intro-physics/astro/bio/chem + orientation) by
  setting deleted_at on each. The Templates page will use deleted_at IS NULL going
  forward, so these rows disappear from the active list without losing audit history.
- Normalize audit_logs.action: rewrite legacy 'signup_cancel' rows to 'signup_cancelled'
  so the humanization layer only has to know one canonical form. Downgrade leaves
  the renamed audit rows alone (data integrity over round-trip symmetry).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_soft_delete_seed_module_templates_and_normalize_audit_kinds"
down_revision = "0011_add_is_active_and_last_login_to_users"
branch_labels = None
depends_on = None


SEED_SLUGS = ("intro-physics", "intro-astro", "intro-bio", "intro-chem", "orientation")


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE module_templates
            SET deleted_at = NOW()
            WHERE deleted_at IS NULL
              AND slug IN ('intro-physics','intro-astro','intro-bio','intro-chem','orientation')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE audit_logs
            SET action = 'signup_cancelled'
            WHERE action = 'signup_cancel'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE module_templates
            SET deleted_at = NULL
            WHERE deleted_at IS NOT NULL
              AND slug IN ('intro-physics','intro-astro','intro-bio','intro-chem','orientation')
            """
        )
    )
    # Intentionally do NOT reverse the audit kind rename — data integrity over
    # round-trip symmetry. The new canonical form is correct.
