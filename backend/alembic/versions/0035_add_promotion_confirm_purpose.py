"""Add magiclinkpurpose 'promotion_confirm'.

A waitlist promotion is a system/staff action, never volunteer intent, so the
promoted seat's confirm link needs a purpose of its own. Sharing
``signup_confirm`` let the original batch confirm link's sibling flip confirm
a promoted seat the volunteer had never acted on (and let a promotion link
confirm the volunteer's unrelated pending signups). Consumers that treat a
promotion token as a confirm token — the hourly reap, the stale-token GC, the
token-gated manage/swap/preferences surfaces — key on the two purposes
together via ``magic_link_service.CONFIRM_PURPOSES`` / ``MANAGE_PURPOSES``.

Revision ID: 0035_add_promotion_confirm_purpose
Revises: 0034_drop_portals
"""

from alembic import op

revision = "0035_add_promotion_confirm_purpose"
down_revision = "0034_drop_portals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block, so use
    # an autocommit_block (same pattern as 0009's signup_confirm/signup_manage
    # additions). IF NOT EXISTS keeps a re-run idempotent.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE magiclinkpurpose ADD VALUE IF NOT EXISTS 'promotion_confirm'"
        )


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type, so this is
    # intentionally a no-op — same as 0009's enum extension. Any rows still
    # holding 'promotion_confirm' would keep a value the ORM no longer knows
    # about, which is why the downgrade does not try to rewrite them either.
    pass
