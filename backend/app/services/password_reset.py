"""Self-service password reset for staff (PR #51).

Same shape as the invite flow (services/invite.py) with a different token
purpose and a much shorter TTL. The email links to the existing
/set-password page, whose endpoint accepts both purposes.

Forgot-password must never confirm whether an address exists, so the
router always answers 202 and this module logs failures instead of
raising them to the client.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger(__name__)

RESET_TOKEN_TTL_MINUTES = 60
RESET_TOKEN_PURPOSE = "password_reset"

# Per-hour ceilings, mirroring the magic-link limiter: the per-email cap is
# what stops one target address being flooded, the per-IP cap is what stops
# one attacker enumerating many addresses.
RESET_MAX_PER_EMAIL_PER_HOUR = 3
RESET_MAX_PER_IP_PER_HOUR = 10


def create_reset_token(user: models.User) -> str:
    """Sign a JWT carrying user_id + reset purpose, valid for one hour."""
    payload = {
        "sub": str(user.id),
        "purpose": RESET_TOKEN_PURPOSE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_reset_token(token: str) -> str:
    """Return user_id (str) for a valid reset token; raise JWTError otherwise."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != RESET_TOKEN_PURPOSE:
        raise JWTError("Wrong token purpose")
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Missing sub")
    return sub


def check_reset_rate_limit(redis_client, email: str, ip: str) -> bool:
    """Return True if within limits, False if rate-limited. Increments counters."""
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
    hour = int(time.time() // 3600)
    email_key = f"pwreset:email:{email_hash}:{hour}"
    ip_key = f"pwreset:ip:{ip}:{hour}"
    pipe = redis_client.pipeline()
    pipe.incr(email_key)
    pipe.expire(email_key, 3600)
    pipe.incr(ip_key)
    pipe.expire(ip_key, 3600)
    email_count, _, ip_count, _ = pipe.execute()
    return (
        email_count <= RESET_MAX_PER_EMAIL_PER_HOUR
        and ip_count <= RESET_MAX_PER_IP_PER_HOUR
    )


def send_reset_email(user: models.User, db: Session) -> None:
    """Send the reset email with a set-password link. Caller wraps try/except."""
    token = create_reset_token(user)
    reset_url = f"{settings.frontend_base_url.rstrip('/')}/set-password?token={token}"
    subject = "Reset your UCSB SciTrek password"
    body = (
        f"Hi {user.name or ''},\n\n"
        "Someone (hopefully you) asked to reset the password for this "
        "UCSB SciTrek staff account.\n"
        f"Click here to choose a new password (link expires in "
        f"{RESET_TOKEN_TTL_MINUTES} minutes):\n"
        f"{reset_url}\n\n"
        "If this wasn't you, ignore this email — your password is unchanged.\n"
    )
    try:
        from ..celery_app import _send_email_via_sendgrid
        _send_email_via_sendgrid(user.email, subject, body)
    except Exception as e:  # pragma: no cover - network/provider failures
        logger.error("password reset email send failed for %s: %s", user.email, e)
        raise
