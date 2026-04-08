# backend/app/deps.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

import redis
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models, schemas


# -------------------------
# OAuth2 / password hashing
# -------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Using PBKDF2 (good baseline). If you want Argon2 later, we can switch cleanly.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


# -------------------------
# Redis + rate limiting
# -------------------------

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def rate_limit(max_requests: int | None = None, window_seconds: int | None = None):
    """
    Simple per-IP + path rate limit using Redis.
    """
    max_req = max_requests or settings.rate_limit_max_requests
    window = window_seconds or settings.rate_limit_window_seconds

    async def dependency(request: Request):
        key = f"rate:{request.client.host}:{request.url.path}"
        current = redis_client.get(key)
        if current is None:
            redis_client.set(key, 1, ex=window)
        else:
            if int(current) >= max_req:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests, slow down.",
                )
            redis_client.incr(key)

    return dependency


# -------------------------
# Password helpers
# -------------------------

def hash_password(password: str) -> str:
    """
    Hash a password using passlib (PBKDF2-SHA256).

    NOTE:
    - No artificial truncation. Truncation was a bcrypt-specific workaround and
      is not appropriate here.
    """
    if not password:
        raise ValueError("Password must not be empty")
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# -------------------------
# JWT helpers
# -------------------------

def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.access_token_expires_minutes
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


# -------------------------
# Current user dependency
# -------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None:
            raise credentials_exception
        _ = schemas.TokenData(user_id=user_id, role=role)  # validate shape
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


# -------------------------
# Role-based access helper
# -------------------------

def require_role(*roles: models.UserRole):
    def dependency(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return dependency


# -------------------------
# Refresh token helpers
# -------------------------

def create_refresh_token(db: Session, user: models.User) -> str:
    """
    Create a refresh token row, but do NOT commit here.
    Caller controls transaction boundaries.
    """
    token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expires_days)
    rt = models.RefreshToken(
        user_id=user.id,
        token=token,
        expires_at=expires,
    )
    db.add(rt)
    db.flush()
    return token


def revoke_refresh_token(db: Session, token: str) -> None:
    """
    Mark a token revoked, but do NOT commit here.
    """
    rt = db.query(models.RefreshToken).filter(models.RefreshToken.token == token).first()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.utcnow()
        db.add(rt)


def verify_refresh_token(db: Session, token: str) -> models.User:
    rt = db.query(models.RefreshToken).filter(models.RefreshToken.token == token).first()
    if (
        rt is None
        or rt.revoked_at is not None
        or rt.expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user = db.query(models.User).filter(models.User.id == rt.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


# -------------------------
# Audit log helper
# -------------------------

def log_action(
    db: Session,
    actor: models.User | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    extra: Dict[str, Any] | None = None,
):
    """
    Add an audit log entry to the current transaction.
    IMPORTANT: no commit here. Caller controls commit/rollback.
    """
    log = models.AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        extra=extra or {},
    )
    db.add(log)
    return log
