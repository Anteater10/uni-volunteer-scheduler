"""Refresh-token rotation lineage, so a replayed token is detectable.

BASE-SEC-25 from the pre-deployment audit.

Rotation was already correct in the narrow sense — each refresh minted a new
token and got rid of the old one — but it got rid of it by DELETING the row.
That threw away the only evidence that a token had ever existed, so a
replayed token was indistinguishable from a forged one: both 401. If an
attacker refreshed a stolen token before the victim did, the victim's next
refresh failed and the attacker's freshly-rotated session continued, with
nothing anywhere recording that two parties had held the same token.

``consumed_at`` retains the spent row so the second use is visible.
``family_id`` groups every token descended from one login so the whole chain
can be revoked in a single statement when that happens.

Both columns are nullable. Tokens issued before this migration have no
family; ``_consume_refresh_token`` falls back to revoking by user_id for
those, so the guarantee holds for existing sessions too without forcing a
fleet-wide logout on deploy.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_refresh_token_family_and_reuse"
down_revision = "0039_add_missing_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "refresh_tokens",
        sa.Column("family_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"]
    )
    # Give every live token its own family, so a session that predates this
    # migration is still individually revocable rather than falling back to
    # the account-wide sweep.
    op.execute(
        "UPDATE refresh_tokens SET family_id = gen_random_uuid() "
        "WHERE family_id IS NULL"
    )


def downgrade():
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "consumed_at")
    op.drop_column("refresh_tokens", "family_id")
