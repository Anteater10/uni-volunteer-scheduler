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

logger = logging.getLogger(__name__)

INVITE_TOKEN_TTL_DAYS = 7
INVITE_TOKEN_PURPOSE = "invite"


def create_invite_token(user: models.User) -> str:
    """Sign a JWT carrying user_id + invite purpose, valid for INVITE_TOKEN_TTL_DAYS."""
    payload = {
        "sub": str(user.id),
        "purpose": INVITE_TOKEN_PURPOSE,
        "exp": datetime.now(timezone.utc) + timedelta(days=INVITE_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_invite_token(token: str) -> str:
    """Return user_id (str) for a valid invite token; raise JWTError otherwise."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != INVITE_TOKEN_PURPOSE:
        raise JWTError("Wrong token purpose")
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Missing sub")
    return sub


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
