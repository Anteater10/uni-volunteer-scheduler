# backend/app/routers/auth.py
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
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
)
from ..config import settings
from ..services.password_reset import check_reset_rate_limit, send_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()


# -------------------------
# Refresh token helpers (auth-router-local)
# These live here rather than in deps.py to keep the full rotation
# logic co-located and avoid cross-module import cycles.
# -------------------------

def _hash_refresh_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token string."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _issue_refresh_token(db: Session, user: models.User) -> str:
    """
    Generate a cryptographically-random refresh token, store its SHA-256
    hash in the DB, and return the raw token to the caller.
    Does NOT commit — caller controls the transaction.
    """
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_refresh_token(raw)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)
    rt = models.RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires,
        created_at=datetime.now(timezone.utc),
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


def _consume_refresh_token(db: Session, raw: str) -> models.User:
    """
    Look up a refresh token by its SHA-256 hash, validate it is not
    expired or revoked, and return the owning User.

    The caller is responsible for rotating (deleting/revoking) the old
    token and issuing a new one.

    Raises HTTP 401 on any invalid state.
    """
    token_hash = _hash_refresh_token(raw)
    rt = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == token_hash)
        .first()
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
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REFRESH_INVALID",
                "detail": "User not found",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Delete (rotate) the consumed token so it cannot be replayed
    db.delete(rt)
    db.flush()
    return user


# -------------------------
# OIDC / SSO setup
# -------------------------

class RefreshRequest(BaseModel):
    refresh_token: str


if settings.oidc_client_id and settings.oidc_client_secret and settings.oidc_issuer:
    oauth.register(
        name="university_sso",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


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

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        user_id = verify_invite_token(payload.token)
    except ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")
    except JWTError:
        try:
            user_id = verify_reset_token(payload.token)
        except ExpiredSignatureError:
            raise HTTPException(status_code=400, detail="This link has expired. Request a new one.")
        except JWTError:
            raise HTTPException(status_code=400, detail="Invalid invite link.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or user.is_active is False:
        raise HTTPException(status_code=400, detail="Invalid invite link.")

    user.hashed_password = hash_password(payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)

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
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

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
    # _consume_refresh_token validates, deletes the old row, and returns the user
    user = _consume_refresh_token(db, payload.refresh_token)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_raw_refresh = _issue_refresh_token(db, user)

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


@router.get("/sso/login")
async def sso_login(request: Request):
    if "university_sso" not in oauth:
        raise HTTPException(status_code=503, detail="SSO not configured")
    redirect_uri = settings.oidc_redirect_uri
    return await oauth.university_sso.authorize_redirect(request, redirect_uri)


@router.get("/sso/callback")
async def sso_callback(request: Request, db: Session = Depends(get_db)):
    if "university_sso" not in oauth:
        raise HTTPException(status_code=503, detail="SSO not configured")

    token = await oauth.university_sso.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    email = userinfo.get("email")
    name = userinfo.get("name") or email

    if not email:
        raise HTTPException(status_code=400, detail="No email in SSO response")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(
            name=name,
            email=email,
            role=models.UserRole.participant,
            hashed_password=hash_password(str(uuid.uuid4())),
        )
        db.add(user)
        db.flush()
        log_action(db, user, "sso_register", "User", str(user.id))

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    raw_refresh = _issue_refresh_token(db, user)

    log_action(db, user, "sso_login", "User", str(user.id))

    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": raw_refresh,
    }
