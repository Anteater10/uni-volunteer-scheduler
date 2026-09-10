# backend/app/deps.py
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import redis
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models, schemas

logger = logging.getLogger(__name__)


# -------------------------
# OAuth2 / password hashing
# -------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# auto_error=False: routes using this must work for anonymous callers too.
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token", auto_error=False
)

# Using PBKDF2 (good baseline). If you want Argon2 later, we can switch cleanly.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


# -------------------------
# Redis + rate limiting
# -------------------------

# Timeouts are not optional here. With the defaults, a Redis that is up but
# unreachable blocks the calling worker indefinitely — and this client sits
# in front of the rate limiter, which runs on the public signup path. A
# two-second ceiling turns "Redis is sick" into a logged error rather than
# every worker parked on a socket read.
redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    retry_on_timeout=True,
    health_check_interval=30,
)


def rate_limit(max_requests: int | None = None, window_seconds: int | None = None):
    """
    Simple per-IP + path rate limit using Redis.

    When EXPOSE_TOKENS_FOR_TESTING=1 is set (E2E test environment), the rate
    limit is bypassed so parallel Playwright tests don't trigger 429 errors.
    """
    import os as _os
    max_req = max_requests or settings.rate_limit_max_requests
    window = window_seconds or settings.rate_limit_window_seconds

    async def dependency(request: Request):
        # Bypass rate limiting in E2E test environments
        if _os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1":
            return

        client = request.client
        key = f"rate:{client.host if client else 'unknown'}:{request.url.path}"
        try:
            # Atomic INCR-first: the old GET-then-SET pattern let a concurrent
            # burst all observe "no key" and each reset the counter to 1,
            # blowing past the cap exactly when it matters.
            current = redis_client.incr(key)
            # Self-healing TTL: set on first hit, and restore it if it was ever
            # lost (crash between INCR and EXPIRE) — a TTL-less key would
            # otherwise rate-limit that IP+path forever.
            if current == 1 or redis_client.ttl(key) < 0:
                redis_client.expire(key, window)
        except redis.RedisError:
            # Fail *open*, deliberately. This dependency guards signup,
            # login and the magic-link paths; if Redis is unreachable the
            # choice is between "nobody can sign up" and "the throttle is
            # off for the duration". The throttle is a nuisance control,
            # not an authorization boundary — the boundary is elsewhere and
            # unaffected. The log line is the alert.
            logger.error(
                "rate_limit_backend_unavailable path=%s", request.url.path
            )
            return
        if current > max_req:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, slow down.",
            )

    return dependency


# -------------------------
# CSRF (double-submit cookie)
# -------------------------

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def verify_csrf(request: Request) -> None:
    """Double-submit cookie check for the routes that authenticate by cookie.

    The refresh cookie is HttpOnly and sent automatically by the browser on
    any cross-site request, so without this a malicious page could trigger a
    refresh. The csrf_token cookie is readable by JS on purpose — proving the
    caller can read a cookie our own origin set is what rules out a blind
    cross-site request.

    Two layers, because the double-submit half alone assumes an attacker
    cannot write cookies for this site. A sibling subdomain (XSS there, or a
    stale CNAME taken over) breaks that assumption: a cookie set with
    ``Domain=.example.org`` from ``evil.example.org`` is also sent to the
    parent host, Starlette's parser is last-wins, and browsers order
    equal-path cookies oldest-first — so the attacker's pair would be the one
    read here, and they know their own value. The Origin check is what
    actually stops that, since a browser always sends Origin on a
    cross-origin POST and cannot be made to forge it.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins_list:
        # Absent Origin is not treated as failure: non-browser callers (curl,
        # the test client, health probes) legitimately omit it, and browsers
        # always send it on the cross-site POSTs this guards against.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF origin rejected",
        )

    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if (
        not cookie_value
        or not header_value
        # compare_digest over ==: the value is a 256-bit nonce so a timing
        # oracle is not a practical attack, but there is no reason to leak
        # the comparison either.
        or not secrets.compare_digest(cookie_value, header_value)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )


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

# Session tokens carry purpose="access". Invite and password-reset tokens are
# signed with the same secret but carry their own purpose (see services/invite.py
# and services/password_reset.py), so without this claim an emailed set-password
# link is replayable as a bearer token. Missing purpose fails closed.
ACCESS_TOKEN_PURPOSE = "access"


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expires_minutes
    )
    to_encode.update({
        "exp": expire,
        "purpose": ACCESS_TOKEN_PURPOSE,
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
    })
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


# -------------------------
# Current user dependency
# -------------------------

def _account_usable(user: models.User) -> bool:
    """Offboarding gate. A token stays cryptographically valid for its full TTL
    and a refresh token for 14 days, so deactivating or deleting a staff account
    only takes effect if every auth path re-checks the row on each request.
    """
    if getattr(user, "is_active", True) is False:
        return False
    if getattr(user, "deleted_at", None) is not None:
        return False
    return True


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
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            # require_* is not the default: python-jose's _validate_aud
            # returns early (i.e. ACCEPTS) when the token carries no `aud` at
            # all, so without this the audience check is decorative and only
            # `iss` is load-bearing. Requiring both means a token that simply
            # omits them fails, instead of passing whichever half is absent.
            options={"require_aud": True, "require_iss": True, "require_exp": True},
        )
        if payload.get("purpose") != ACCESS_TOKEN_PURPOSE:
            raise credentials_exception
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None:
            raise credentials_exception
        _ = schemas.TokenData(user_id=user_id, role=role)  # validate shape
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not _account_usable(user):
        raise credentials_exception
    return user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Best-effort caller identification for routes that serve both a public
    surface and a staff surface from the same endpoint (e.g. GET /slots).

    Missing, malformed, or invalid tokens all resolve to None (treat the
    caller as anonymous) rather than raising — this must only be used where
    anonymous access is an accepted outcome, never where authentication is
    mandatory (use get_current_user / require_role for that).
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            # require_* is not the default: python-jose's _validate_aud
            # returns early (i.e. ACCEPTS) when the token carries no `aud` at
            # all, so without this the audience check is decorative and only
            # `iss` is load-bearing. Requiring both means a token that simply
            # omits them fails, instead of passing whichever half is absent.
            options={"require_aud": True, "require_iss": True, "require_exp": True},
        )
        if payload.get("purpose") != ACCESS_TOKEN_PURPOSE:
            return None
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is not None and not _account_usable(user):
        return None
    return user


def is_staff(user: Optional[models.User]) -> bool:
    """Admin/organizer check usable with get_optional_user's Optional result.

    Not redundant with `require_staff`: this is for endpoints anonymous users may
    reach, where staff simply see more. A dependency cannot express that.
    """
    return user is not None and user.role in STAFF_ROLES


# -------------------------
# Role-based access helper
# -------------------------

def ensure_event_staff_access(event: models.Event, user: models.User) -> None:
    """Canonical staff access check for a single event.

    Admins and organizers may operate any event. All routers import this from
    app.deps — do not redefine locally.

    This used to require organizers to *own* the event, which broke the shared
    admin shell rather than protecting anything: the staff event list is global
    (every organizer-visible tab lists all events), so an organizer would open
    an event, read its details fine, and then get a 403 on its roster, its
    attendance summary and its check-in screen. Nothing in the product could
    transfer ownership either — owner_id is set to the creator and there is no
    UI or field to reassign it — so an organizer could only ever operate events
    they had personally created. Organizers are a trusted staff role, so the
    gate is role-based; the boundary that matters is the set of admin-only
    routes (user management, audit logs, quarter config, exports).

    `event` is kept in the signature: callers have already loaded it, and a
    future per-event rule belongs here rather than in 40-odd call sites.
    """
    if user.role in STAFF_ROLES:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not allowed for this event",
    )


def require_role(*roles: models.UserRole):
    """Build a role guard. Prefer the named guards below over calling this.

    S-03: the W5 sweep found six different spellings of "admin or organizer"
    across the routers, because every endpoint constructed its own dependency
    inline — arg order, import style (`UserRole` vs `models.UserRole`) and role
    set all drifted per call site. No single grep covered the surface, which is
    how K33 stayed hidden and how the sweep's own first pass mis-scoped its
    target list by 20 endpoints. Constructing this at a call site is what
    multiplies spellings, so `tests/test_staff_guard_canonical.py` fails on
    `Depends(require_role(...))` anywhere outside this module.
    """
    def dependency(current_user: models.User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return dependency


# The one definition of "staff". Everything that means "admin or organizer" —
# route guards, the copilot's own guard, and the queries that ask *which users
# are staff* — reads it from here.
STAFF_ROLES = (models.UserRole.admin, models.UserRole.organizer)

require_admin = require_role(models.UserRole.admin)
require_staff = require_role(*STAFF_ROLES)


# Refresh tokens deliberately have NO helpers here. The full rotation +
# reuse-detection logic lives in routers/auth.py (_issue_refresh_token /
# _consume_refresh_token / _revoke_refresh_token) so it stays co-located.
# Three unused helpers used to sit here — create_refresh_token,
# revoke_refresh_token and a verify_refresh_token that validated a token
# WITHOUT rotating it or detecting reuse. Nothing called them, and a
# plausible-looking verify in a shared module is exactly what a future
# caller reaches for by mistake, bypassing the rotation the real path
# enforces. Deleted in Phase L3 rather than left as a footgun.


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
