"""Per-account login failure tracking, so brute force is bounded by account.

BASE-SEC-08. Login was protected by one control: 30 requests per minute per IP
per path (``auth.py`` / ``deps.rate_limit``). Nothing counted failures against
the *account*, so an attacker spreading guesses across many addresses stayed
under the limit on every one of them and was never blocked, while the account
being attacked had no state recording that it was under attack.

Deliberately three columns on ``users`` rather than a Redis counter or a new
table:

* Redis was the obvious reach — the rate limiter already lives there — but that
  limiter **fails open** by design (``deps.py``: better that signup keeps
  working during a Redis outage than that nobody can sign up). A brute-force
  control that switches itself off when a dependency is down is not a control.
  These columns make the lockout survive a Redis outage and a restart.
* A separate table would let us keep per-attempt history, which is genuinely
  more useful for forensics — but it also grows unboundedly on exactly the
  traffic an attacker controls, and the reaper to stop that does not exist yet.
  Three columns cannot be flooded.

``locked_until`` is the load-bearing one: an absolute timestamp, so a lock
outlives a process restart and needs no sweeper to expire.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_login_failure_lockout"
down_revision: Union[str, None] = "0040_refresh_token_family_and_reuse"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Creates no enum types, so this does not extend the known
    # downgrade-then-upgrade DuplicateObject bug documented in CLAUDE.md.
    op.drop_column("users", "locked_until")
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "failed_login_count")
