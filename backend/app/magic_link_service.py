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
from uuid import UUID

from sqlalchemy.orm import Session

from .config import settings
from .models import MagicLinkToken, MagicLinkPurpose, Signup, SignupStatus, Slot


# Phase 09 (D-06): 14-day TTL for signup-confirm tokens
SIGNUP_CONFIRM_TTL_MINUTES = 20160  # 14 days * 24h * 60min

# 2026-07-28 spec: promoted-from-waitlist signups get a shorter confirm
# window than fresh signups — a ghost promotee must not block the seat.
PROMOTION_CONFIRM_TTL_MINUTES = 4320  # 3 days * 24h * 60min

# Purposes that make a pending signup confirmable. PROMOTION_CONFIRM is a
# separate purpose so consent stays scoped (see consume_token), but for the
# hourly reap and the stale-token GC a promotion token IS the signup's confirm
# token — keying on SIGNUP_CONFIRM alone would make promotion-pending rows
# invisible to the reap and leak their tokens past the GC. One tuple so no
# consumer can drift.
CONFIRM_PURPOSES = (
    MagicLinkPurpose.SIGNUP_CONFIRM,
    MagicLinkPurpose.PROMOTION_CONFIRM,
)

# Purposes that grant token-gated manage access (manage page, swap, cancel,
# preferences, reminder manage links). Every confirm link doubles as the
# volunteer's manage/cancel page — that is the promotion link's whole point.
MANAGE_PURPOSES = (
    MagicLinkPurpose.SIGNUP_CONFIRM,
    MagicLinkPurpose.SIGNUP_MANAGE,
    MagicLinkPurpose.PROMOTION_CONFIRM,
)


class ConsumeResult(str, Enum):
    ok = "ok"
    expired = "expired"
    used = "used"
    not_found = "not_found"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(
    db: Session,
    signup: Signup,
    email: str,
    *,
    purpose: MagicLinkPurpose = MagicLinkPurpose.SIGNUP_CONFIRM,
    volunteer_id: UUID | None = None,
    ttl_minutes: int | None = None,
) -> str:
    """Create a new magic-link token for a signup. Returns raw token.

    Args:
        db: DB session (caller commits).
        signup: Anchor signup row (signup_id stored on token).
        email: Email address to store on the token (lowercased).
        purpose: Token purpose (default SIGNUP_CONFIRM for Phase 09).
        volunteer_id: Optional volunteer UUID to store on the token; enables batch confirm.
        ttl_minutes: Override TTL in minutes; defaults to settings.magic_link_ttl_minutes.
    """
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    ttl = ttl_minutes if ttl_minutes is not None else settings.magic_link_ttl_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    row = MagicLinkToken(
        token_hash=token_hash,
        signup_id=signup.id,
        email=email.lower(),
        expires_at=expires_at,
        purpose=purpose,
        volunteer_id=volunteer_id,
    )
    db.add(row)
    db.flush()
    return raw


def _lookup_token(db: Session, raw: str) -> Optional[MagicLinkToken]:
    """Hash the raw token and return the MagicLinkToken row without consuming it.

    Returns None if not found. Does NOT flip consumed_at. Used by manage + cancel endpoints.
    """
    token_hash = _hash_token(raw)
    return db.query(MagicLinkToken).filter_by(token_hash=token_hash).first()


def _promotion_pending_exists(db: Session):
    """Correlated EXISTS: does the outer ``Signup`` row carry a promotion
    confirm token?

    Such a signup is only pending because a promotion put it there, so it may
    be confirmed by its own promotion link and by nothing else. Correlation is
    pinned explicitly — a de-correlated subquery would silently degrade to
    "does ANY promotion token exist", which would freeze every batch confirm.
    """
    return (
        db.query(MagicLinkToken.id)
        .filter(
            MagicLinkToken.signup_id == Signup.id,
            MagicLinkToken.purpose == MagicLinkPurpose.PROMOTION_CONFIRM,
        )
        .correlate(Signup)
        .exists()
    )


def _is_promotion_pending(db: Session, signup: Signup) -> bool:
    """True when this pending signup's seat came from a promotion.

    INVARIANT this detection depends on: the marker is token *history*, not
    token liveness — any PROMOTION_CONFIRM row counts, consumed or expired —
    so once a signup has been promoted it is permanently promotion-scoped for
    as long as it stays pending. That is safe only because:

      1. nothing in the codebase returns a confirmed signup to pending (the
         only writers of `pending` are the batch signup path and
         mark_promoted_pending, which requires `waitlisted`), so a consumed
         promotion token can never be shadowing a *fresh* pending seat; and
      2. requiring liveness instead would be strictly worse — an expired
         promotion token would hand the seat back to the batch link's flip,
         i.e. auto-confirm exactly the seat this scoping protects.

    If a future change ever lets a confirmed (or promotion-confirmed) signup
    become pending again, this must switch to a real per-signup marker rather
    than token history.
    """
    if signup.status != SignupStatus.pending:
        return False
    return bool(
        db.query(MagicLinkToken.id)
        .filter(
            MagicLinkToken.signup_id == signup.id,
            MagicLinkToken.purpose == MagicLinkPurpose.PROMOTION_CONFIRM,
        )
        .first()
    )


def consume_token(db: Session, raw: str) -> tuple[ConsumeResult, Optional[Signup], int]:
    """Atomically consume a token, returning (result, signup, confirmed_count).

    For SIGNUP_CONFIRM purpose with volunteer_id set: batch-flips all pending
    signups for that volunteer in the same event as the anchor signup.

    2026-07-29 consent scoping: a promoted seat is only ever confirmed by its
    own PROMOTION_CONFIRM link. So a batch SIGNUP_CONFIRM token skips every
    promotion-pending signup (anchor included — the batch anchor can itself be
    a signup that was waitlisted at signup time and promoted later), and a
    PROMOTION_CONFIRM token confirms its own signup and nothing else. The
    tradeoff: a volunteer whose only signup is promotion-pending can consume
    their original batch link without confirming anything — the promotion
    email is the only message that names the seat being offered, so silently
    confirming here would be exactly the consent violation this scoping
    exists to prevent.

    ``confirmed_count`` (2026-07-29 sweep remediation, Finding #1) is how
    many signups are in the `confirmed` status because of this call: 1 for
    the anchor if it ends this call confirmed (whether flipped just now or
    already confirmed by an earlier action), plus however many batch
    siblings this call newly flipped. It is 0 on every non-ok result.
    ``ConsumeResult.ok`` with ``confirmed_count == 0`` means the token was
    legitimately burned but scoped away from confirming anything — callers
    MUST NOT report success in that case; it is distinct from
    ``ConsumeResult.used``, which means the token itself was already spent.
    """
    token_hash = _hash_token(raw)
    row = db.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
    if row is None:
        return ConsumeResult.not_found, None, 0
    if row.consumed_at is not None:
        return ConsumeResult.used, None, 0
    if row.expires_at < datetime.now(timezone.utc):
        return ConsumeResult.expired, None, 0
    signup = db.query(Signup).filter_by(id=row.signup_id).first()
    if signup is None or signup.status == SignupStatus.cancelled:
        return ConsumeResult.not_found, None, 0
    # Atomic update — if another request beat us, updated == 0
    updated = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.id == row.id, MagicLinkToken.consumed_at.is_(None))
        .update({"consumed_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    if updated != 1:
        return ConsumeResult.used, None, 0
    if signup.status == SignupStatus.pending and (
        row.purpose == MagicLinkPurpose.PROMOTION_CONFIRM
        or not _is_promotion_pending(db, signup)
    ):
        signup.status = SignupStatus.confirmed
    db.flush()

    # Phase 09 (D-06): batch-flip sibling pending signups for same volunteer + event
    sibling_count = 0
    if row.purpose == MagicLinkPurpose.SIGNUP_CONFIRM and row.volunteer_id is not None:
        anchor_slot = db.query(Slot).filter_by(id=signup.slot_id).first()
        if anchor_slot is not None:
            anchor_event_id = anchor_slot.event_id
            sibling_signups = (
                db.query(Signup)
                .join(Slot, Slot.id == Signup.slot_id)
                .filter(
                    Signup.volunteer_id == row.volunteer_id,
                    Signup.status == SignupStatus.pending,
                    Slot.event_id == anchor_event_id,
                    Signup.id != signup.id,
                    ~_promotion_pending_exists(db),
                )
                .all()
            )
            for s in sibling_signups:
                s.status = SignupStatus.confirmed
                sibling_count += 1
            db.flush()

    confirmed_count = sibling_count + (
        1 if signup.status == SignupStatus.confirmed else 0
    )
    return ConsumeResult.ok, signup, confirmed_count


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
    """Issue a token and send the magic-link email. Idempotent within a 60s window.

    2026-07-29 sweep remediation, Finding #2: a promotion-pending signup (see
    _is_promotion_pending) must get its own PROMOTION_CONFIRM token and the
    promotion email — the plain SIGNUP_CONFIRM token this used to mint
    unconditionally can never confirm such a signup (see consume_token's
    scoping), so resending it just handed out a second broken link.
    """
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

    if _is_promotion_pending(db, signup):
        raw = issue_token(
            db,
            signup,
            email,
            purpose=MagicLinkPurpose.PROMOTION_CONFIRM,
            volunteer_id=signup.volunteer_id,
            ttl_minutes=PROMOTION_CONFIRM_TTL_MINUTES,
        )
        from .emails import build_waitlist_promotion_email

        build_waitlist_promotion_email(signup.volunteer, signup, raw, event)
    else:
        raw = issue_token(db, signup, email)
        from .emails import send_magic_link

        send_magic_link(email, raw, event, base_url)
