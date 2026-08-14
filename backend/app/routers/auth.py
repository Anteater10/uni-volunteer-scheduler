# backend/app/routers/auth.py
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models, schemas
from ..database import get_db
from ..deps import (
    verify_password,
    create_access_token,
    hash_password,
    rate_limit,
    log_action,
    get_current_user,
    _account_usable,
)
from ..config import settings
from ..services.password_reset import check_reset_rate_limit, send_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# -------------------------
# Refresh token helpers (auth-router-local)
# These live here rather than in deps.py to keep the full rotation
# logic co-located and avoid cross-module import cycles.
# -------------------------

def _hash_refresh_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token string."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# -------------------------
# Per-account login lockout (BASE-SEC-08)
# -------------------------

def _is_locked(user: models.User) -> bool:
    """Whether ``user`` is inside an active lockout window.

    ``locked_until`` is an absolute timestamp, so the lock expires on its own
    and needs no sweeper — a restart mid-lockout does not release it either.
    """
    locked_until = user.locked_until
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:  # defensive: a naive value from a raw write
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > datetime.now(timezone.utc)


def _record_login_failure(db: Session, user: models.User) -> None:
    """Count a wrong password and lock the account once the threshold is hit.

    Commits, because the caller raises immediately afterwards — the whole point
    is that this survives the failed request. Without the commit the session
    closes unflushed and every attempt looks like the first, which is the
    unbounded-guessing bug this exists to close.

    The response the caller sends stays byte-identical to a wrong password on a
    healthy account. That is deliberate: the endpoint is careful not to reveal
    which accounts exist (see the ``_account_usable`` check below), and a
    distinct "account locked" reply would hand that back by letting an attacker
    tell a real address from a fake one. The cost is that a locked-out member of
    staff sees "Incorrect email or password" and has to wait or ask an admin —
    so the lock is recorded in the audit log, where an admin can see it.
    """
    now = datetime.now(timezone.utc)
    user.failed_login_count = (user.failed_login_count or 0) + 1
    user.last_failed_login_at = now

    if user.failed_login_count >= settings.login_max_failed_attempts:
        user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        # Reset the counter with the lock, so the next window is a fresh N
        # attempts rather than one attempt re-locking the account forever.
        user.failed_login_count = 0
        log_action(db, user, "user_login_locked", "User", str(user.id))
        logger.warning(
            "login_lockout user_id=%s until=%s", user.id, user.locked_until
        )

    db.add(user)
    db.commit()


def _issue_refresh_token(
    db: Session, user: models.User, *, family_id=None
) -> str:
    """
    Generate a cryptographically-random refresh token, store its SHA-256
    hash in the DB, and return the raw token to the caller.
    Does NOT commit — caller controls the transaction.

    ``family_id`` carries rotation lineage: omitted at login (a fresh login
    starts a new family), passed through on refresh so the whole chain can
    be revoked at once if a spent token is ever replayed.
    """
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)
    rt = models.RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires,
        created_at=datetime.now(timezone.utc),
        family_id=family_id or uuid.uuid4(),
    )
    db.add(rt)
    db.flush()
    return raw


def _revoke_refresh_token(db: Session, raw: str) -> None:
    """
    Mark a refresh token as revoked by its hash.
    Does NOT commit — caller controls the transaction.
    """
    token_hash = _hash_refresh_token(raw)
    rt = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        db.add(rt)


def _consume_refresh_token(db: Session, raw: str) -> tuple[models.User, object]:
    """
    Look up a refresh token by its SHA-256 hash, validate it is not
    expired, revoked or already consumed, mark it consumed, and return
    ``(user, family_id)`` so the caller can mint the replacement into the
    same rotation family.

    Raises HTTP 401 on any invalid state — and on replay of an already
    consumed token, revokes the entire family first.
    """
    token_hash = _hash_refresh_token(raw)
    rt = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
    )

    # Reuse detection. A spent token being presented a second time means the
    # token leaked: either the legitimate holder is replaying (harmless but
    # indistinguishable) or somebody else copied it. We cannot tell which,
    # and the safe reading of "cannot tell" is that the family is
    # compromised — so revoke every token descended from that login and make
    # both parties sign in again. Previously the replay just 401'd, and if
    # an attacker had already rotated the token first, the victim's 401 was
    # the *only* symptom while the attacker's session ran on untouched.
    if rt is not None and rt.consumed_at is not None:
        now = datetime.now(timezone.utc)
        if rt.family_id is not None:
            db.query(models.RefreshToken).filter(
                models.RefreshToken.family_id == rt.family_id,
                models.RefreshToken.revoked_at.is_(None),
            ).update({"revoked_at": now}, synchronize_session=False)
        else:
            # Pre-migration rows have no family; fall back to the account.
            db.query(models.RefreshToken).filter(
                models.RefreshToken.user_id == rt.user_id,
                models.RefreshToken.revoked_at.is_(None),
            ).update({"revoked_at": now}, synchronize_session=False)
        db.commit()
        logger.warning(
            "refresh_token_reuse_detected user_id=%s family_id=%s",
            rt.user_id,
            rt.family_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REFRESH_REUSE",
                "detail": "Refresh token reused; all sessions revoked",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if (
        rt is None
        or rt.revoked_at is not None
        or rt.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REFRESH_INVALID",
                "detail": "Invalid or expired refresh token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(models.User).filter(models.User.id == rt.user_id).first()
    if not user or not _account_usable(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REFRESH_INVALID",
                "detail": "User not found",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Retain, do not delete. The row is what makes a later replay
    # detectable; deleting it threw that evidence away.
    rt.consumed_at = datetime.now(timezone.utc)
    db.add(rt)
    db.flush()
    return user, rt.family_id


# W5.5 / S-04, 2026-08-13: the OIDC client registration and the two /sso/*
# endpoints that used it were deleted here. See tests/test_no_sso_surface.py for
# what they did, why half-wired was worse than absent, and what has to be decided
# before campus SSO is attempted again.

class RefreshRequest(BaseModel):
    refresh_token: str


# -------------------------
# Routes
# -------------------------


class SetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/set-password", response_model=schemas.Token)
def set_password_from_invite(
    payload: SetPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(20, 60)),
):
    """Consume an invite or password-reset JWT, set the user's password,
    return access+refresh tokens. Both token kinds land on the same
    /set-password page; only the purpose claim and TTL differ."""
    from jose import JWTError, ExpiredSignatureError
    from ..services.invite import verify_invite_token
    from ..services.password_reset import verify_reset_token
    from ..services.credential_fingerprint import payload_fingerprint_matches

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        token_payload = verify_invite_token(payload.token)
    except ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")
    except JWTError:
        try:
            token_payload = verify_reset_token(payload.token)
        except ExpiredSignatureError:
            raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")
        except JWTError:
            raise HTTPException(status_code=400, detail="Invalid invite link.")

    user = db.query(models.User).filter(models.User.id == token_payload["sub"]).first()
    if user is None or user.is_active is False:
        raise HTTPException(status_code=400, detail="Invalid invite link.")

    # Single-use enforcement (Task 6): the token was minted with an `fp`
    # claim bound to the credential state (hashed_password) at that time.
    # If the password has since changed — including via this same token on
    # an earlier request — the fingerprint no longer matches and the token
    # is dead, even though its signature and expiry are still fine. Reuses
    # the payload already decoded above instead of decoding the raw token
    # again (avoids a second decode racing an expiry boundary).
    if not payload_fingerprint_matches(token_payload, user):
        raise HTTPException(
            status_code=400,
            detail="This link has already been used or is no longer valid.",
        )

    user.hashed_password = hash_password(payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)

    # Setting a password is the victim's remedy after a session is stolen, so
    # it has to evict every existing session — otherwise the attacker's refresh
    # token keeps rotating for its full 14 days. Matches change_password below.
    db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == user.id
    ).delete()
    db.flush()

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    raw_refresh = _issue_refresh_token(db, user)
    log_action(db, user, "user_set_password", "User", str(user.id))
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": raw_refresh,
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: None = Depends(rate_limit(10, 60)),
):
    """Let a logged-in staff member rotate their own password.

    Requires the current password even though the caller is authenticated —
    a walk-up to an unlocked laptop must not be enough to take the account.
    All refresh tokens are revoked so any other session has to log in again.
    """
    if current_user.hashed_password is None:
        raise HTTPException(
            status_code=409,
            detail="This account has no password yet — use the link from your invite email to set one.",
        )
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    current_user.hashed_password = hash_password(payload.new_password)
    db.add(current_user)
    db.query(models.RefreshToken).filter(
        models.RefreshToken.user_id == current_user.id
    ).delete()
    log_action(db, current_user, "user_change_password", "User", str(current_user.id))
    db.commit()
    return {"status": "ok"}


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/forgot-password", status_code=202)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(10, 60)),
):
    """Email a password-reset link if the address belongs to active staff.

    Always answers 202 with the same body — a different status, error, or
    timing-observable send for unknown addresses would confirm which emails
    have accounts. Participants never have passwords, so they are treated
    exactly like unknown addresses.
    """
    ip = request.client.host if request.client else "unknown"
    from ..deps import redis_client

    if not check_reset_rate_limit(redis_client, payload.email, ip):
        # Rate-limited requests also answer 202: a 429 only for real
        # addresses would leak existence just as loudly as a 404.
        return {"status": "accepted"}

    user = (
        db.query(models.User)
        .filter(
            models.User.email == payload.email.lower().strip(),
            models.User.is_active.is_(True),
            models.User.deleted_at.is_(None),
            models.User.role.in_([models.UserRole.admin, models.UserRole.organizer]),
        )
        .first()
    )
    if user is not None:
        try:
            send_reset_email(user, db)
        except Exception:
            # Logged inside the service; the client still gets 202.
            pass
    return {"status": "accepted"}


@router.post("/token", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit(30, 60)),
):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    # Phase 16 Plan 01: hashed_password may be NULL for magic-link-only users
    if not user or user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    # BASE-SEC-08: refuse while the account is locked, BEFORE verifying the
    # password. Checking after would let an attacker keep testing candidates
    # against a locked account and learn from the timing of the bcrypt work
    # whether they had guessed right, which defeats the point of locking.
    if _is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not verify_password(form_data.password, user.hashed_password):
        _record_login_failure(db, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    # Deactivated / soft-deleted staff must not be able to log back in. Kept
    # indistinguishable from a bad password so the endpoint is not an oracle
    # for which accounts exist.
    if not _account_usable(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # The password was right, so this is the legitimate holder (or someone who
    # already has it — in which case a stale counter is the least of it).
    user.failed_login_count = 0
    user.locked_until = None

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    raw_refresh = _issue_refresh_token(db, user)

    # Phase 16 Plan 02 (D-37): stamp last_login_at on successful login so the
    # admin Users page can show "last seen" per user. Application-code driven,
    # NOT a DB trigger, for portability.
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)

    log_action(db, user, "user_login", "User", str(user.id))

    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": raw_refresh,
    }


# ✅ SECURITY FIX: refresh token must be in request body (not query string)
# ✅ SECURITY FIX: token is rotated on every successful refresh (T-00-13)
@router.post("/refresh", response_model=schemas.Token)
def refresh_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    # _consume_refresh_token validates, marks the old row consumed, and
    # returns the user plus the rotation family the new token must join.
    user, family_id = _consume_refresh_token(db, payload.refresh_token)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_raw_refresh = _issue_refresh_token(db, user, family_id=family_id)

    log_action(db, user, "token_refresh", "User", str(user.id))
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": new_raw_refresh,
    }


# ✅ SECURITY FIX: logout refresh token must be in request body (not query string)
@router.post("/logout")
def logout(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _revoke_refresh_token(db, payload.refresh_token)
    log_action(db, current_user, "user_logout", "User", str(current_user.id))
    db.commit()
    return {"detail": "Logged out"}


