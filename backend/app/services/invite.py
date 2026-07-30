"""Admin user invite email helper (Phase 16 Plan 02, D-11).

Invite flow: a newly-invited admin/organizer is created with
`hashed_password=NULL` and `is_active=TRUE`. We then issue a 7-day JWT
invite token and email a `/set-password?token=...` link. The user lands on
that page, sets a password, and is auto-logged-in.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .credential_fingerprint import credential_fingerprint

logger = logging.getLogger(__name__)

INVITE_TOKEN_TTL_DAYS = 7
INVITE_TOKEN_PURPOSE = "invite"


def create_invite_token(user: models.User) -> str:
    """Sign a JWT carrying user_id + invite purpose, valid for INVITE_TOKEN_TTL_DAYS.

    Also binds an `fp` claim to the user's current hashed_password (see
    credential_fingerprint.py — NULL/no-password uses a stable sentinel) so
    the token is single-use: setting the first password invalidates this
    and every other outstanding invite/reset token for the user.
    """
    payload = {
        "sub": str(user.id),
        "purpose": INVITE_TOKEN_PURPOSE,
        "fp": credential_fingerprint(user),
        "exp": datetime.now(timezone.utc) + timedelta(days=INVITE_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_invite_token(token: str) -> dict:
    """Validate an invite token's signature, purpose, and expiry; return the
    full decoded payload. Raise JWTError/ExpiredSignatureError otherwise.

    Does NOT check the `fp` claim — see verify_reset_token's docstring in
    password_reset.py for why, and why the full payload is returned rather
    than just user_id.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != INVITE_TOKEN_PURPOSE:
        raise JWTError("Wrong token purpose")
    if not payload.get("sub"):
        raise JWTError("Missing sub")
    return payload


def send_invite_email(user: models.User, db: Session) -> None:
    """Send the invite email with a set-password link. Caller wraps try/except."""
    token = create_invite_token(user)
    set_password_url = f"{settings.frontend_base_url.rstrip('/')}/set-password?token={token}"
    subject = "You've been invited to UCSB SciTrek"
    body = (
        f"Hi {user.name or ''},\n\n"
        f"You've been invited to UCSB SciTrek as a {user.role.value}.\n"
        f"Click here to set your password and sign in (link expires in {INVITE_TOKEN_TTL_DAYS} days):\n"
        f"{set_password_url}\n\n"
        "If you did not expect this invitation, you can ignore this email.\n"
    )
    try:
        from ..celery_app import _send_email_via_sendgrid
        _send_email_via_sendgrid(user.email, subject, body)
    except Exception as e:  # pragma: no cover - network/provider failures
        logger.error("invite email send failed for %s: %s", user.email, e)
        raise
