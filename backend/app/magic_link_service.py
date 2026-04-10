"""Magic-link token lifecycle: issue, consume, rate-limit, dispatch.

Tokens are 32-byte URL-safe base64 strings (~43 chars). Only the SHA-256
hash is stored in the DB; the raw token appears exclusively in the email
link and is never logged.
"""
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from .config import settings
from .models import MagicLinkToken, Signup, SignupStatus


class ConsumeResult(str, Enum):
    ok = "ok"
    expired = "expired"
    used = "used"
    not_found = "not_found"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(db: Session, signup: Signup, email: str) -> str:
    """Create a new magic-link token for a signup. Returns raw token."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.magic_link_ttl_minutes)
    row = MagicLinkToken(
        token_hash=token_hash,
        signup_id=signup.id,
        email=email.lower(),
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return raw


def consume_token(db: Session, raw: str) -> tuple[ConsumeResult, Optional[Signup]]:
    """Atomically consume a token, returning (result, signup)."""
    token_hash = _hash_token(raw)
    row = db.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
    if row is None:
        return ConsumeResult.not_found, None
    if row.consumed_at is not None:
        return ConsumeResult.used, None
    if row.expires_at < datetime.now(timezone.utc):
        return ConsumeResult.expired, None
    signup = db.query(Signup).filter_by(id=row.signup_id).first()
    if signup is None or signup.status == SignupStatus.cancelled:
        return ConsumeResult.not_found, None
    # Atomic update — if another request beat us, updated == 0
    updated = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.id == row.id, MagicLinkToken.consumed_at.is_(None))
        .update({"consumed_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    if updated != 1:
        return ConsumeResult.used, None
    if signup.status == SignupStatus.pending:
        signup.status = SignupStatus.confirmed
    db.flush()
    return ConsumeResult.ok, signup


def _hour_epoch() -> int:
    return int(time.time() // 3600)


def check_rate_limit(redis_client, email: str, ip: str) -> bool:
    """Return True if within limits, False if rate-limited. Increments counters."""
    email_lower = email.lower()
    email_hash = hashlib.sha256(email_lower.encode()).hexdigest()
    hour = _hour_epoch()
    email_key = f"magic:email:{email_hash}:{hour}"
    ip_key = f"magic:ip:{ip}:{hour}"
    pipe = redis_client.pipeline()
    pipe.incr(email_key)
    pipe.expire(email_key, 3600)
    pipe.incr(ip_key)
    pipe.expire(ip_key, 3600)
    email_count, _, ip_count, _ = pipe.execute()
    if email_count > settings.magic_link_max_per_email_per_hour:
        return False
    if ip_count > settings.magic_link_max_per_ip_per_hour:
        return False
    return True


def dispatch_email(db: Session, signup: Signup, event, base_url: str) -> None:
    """Issue a token and send the magic-link email. Idempotent within a 60s window."""
    # Phase 09: signup.user removed; use signup.volunteer
    email = signup.volunteer.email if signup.volunteer else None
    if not email:
        return

    # Idempotency: reuse recent un-consumed non-expired token if present
    recent_cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    existing = (
        db.query(MagicLinkToken)
        .filter(
            MagicLinkToken.signup_id == signup.id,
            MagicLinkToken.consumed_at.is_(None),
            MagicLinkToken.expires_at > datetime.now(timezone.utc),
            MagicLinkToken.created_at >= recent_cutoff,
        )
        .first()
    )
    if existing is not None:
        return  # A token was just issued; skip duplicate send

    raw = issue_token(db, signup, email)
    from .emails import send_magic_link

    send_magic_link(email, raw, event, base_url)
