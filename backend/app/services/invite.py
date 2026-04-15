"""Admin user invite email helper (Phase 16 Plan 02, D-11).

Invite flow for admin/organizer users. A newly-invited user is created with
`hashed_password=NULL` and `is_active=TRUE`, then we send a simple
"you've been invited" email pointing at the frontend login URL. First-login
goes through the normal /auth/token path once the admin sets a password, OR
the operator can distribute a temporary password out-of-band. Full magic-link
admin-invite flow is a follow-up; this helper exists so the invite endpoint
has a single side-effect seam that tests can patch.

Kept intentionally tiny: no token generation here, no template logic, no
retries. Router logs and swallows exceptions so a dead SMTP provider does
not roll back user creation.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)


def send_invite_email(user: models.User, db: Session) -> None:
    """Send a one-off invite email to the newly-created admin/organizer user.

    The caller (router) is responsible for wrapping this in a try/except so
    transient email failures never roll back the user row. Returns None.
    """
    login_url = f"{settings.frontend_base_url.rstrip('/')}/login?invited={user.email}"
    subject = "You've been invited to UCSB SciTrek"
    body = (
        f"Hi {user.name or ''},\n\n"
        f"You've been invited to UCSB SciTrek as a {user.role.value}.\n"
        f"Sign in here to get started: {login_url}\n\n"
        "If you did not expect this invitation, you can ignore this email.\n"
    )
    try:
        from ..celery_app import _send_email_via_sendgrid
        _send_email_via_sendgrid(user.email, subject, body)
    except Exception as e:  # pragma: no cover - network/provider failures
        logger.error("invite email send failed for %s: %s", user.email, e)
        raise
