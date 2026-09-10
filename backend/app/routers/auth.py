# backend/app/routers/auth.py
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models, schemas
from ..database import get_db
from ..deps import (
    STAFF_ROLES,
    verify_password,
    create_access_token,
    hash_password,
    rate_limit,
    log_action,
    get_current_user,
    get_optional_user,
    _account_usable,
    verify_csrf,
    CSRF_COOKIE_NAME,
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


# How long after a rotation a replay of the spent token is read as this
# user's own tabs racing rather than as a stolen token. Short on purpose:
# long enough to cover concurrent page loads and a slow round trip, far too
# short to be useful to somebody replaying a captured cookie later.
REPLAY_GRACE_SECONDS = 15


# -------------------------
# Auth cookies (Phase L3)
#
# The refresh token moves out of the JSON body into an HttpOnly cookie so
# XSS in the app can no longer read it; the browser attaches it
# automatically for us. A second, JS-readable csrf_token cookie is set
# alongside it — verify_csrf (deps.py) checks it against an X-CSRF-Token
# header on /auth/refresh, since HttpOnly cookies are sent even on
# cross-site requests and a CSRF check is what rules those out.
# The two cookies deliberately get DIFFERENT paths; see below.
# -------------------------

# The refresh cookie's Path must match the path the browser actually
# requests, not this router's own prefix — main.py mounts it under
# app.include_router(..., prefix="/api/v1"), and the frontend's API_BASE
# always includes /api/v1 too (see frontend/src/lib/apiBase.js), so every
# request lands on /api/v1/auth/*. A cookie scoped to plain "/auth" would
# never be sent back. Scoping it this narrowly keeps the refresh token off
# every other request in the app.
REFRESH_COOKIE_PATH = "/api/v1/auth"

# The CSRF cookie, by contrast, MUST be Path=/ — it is read by JS via
# document.cookie from whatever route the SPA happens to be on
# (/admin/events, /login, ...), and document.cookie only exposes cookies
# whose Path prefix-matches the *current page*. Scoped to /api/v1/auth it is
# invisible to every page in the app, so no X-CSRF-Token header can ever be
# built and every refresh 403s — verified in chromium and firefox, where the
# cookie is stored yet document.cookie comes back empty. Widening the path
# costs nothing: this value is a random nonce, not a credential. Proving the
# caller could READ a cookie our origin set is the whole mechanism, so it has
# to be readable.
CSRF_COOKIE_PATH = "/"


def _cookie_secure(request: Request) -> bool:
    """Whether to mark the auth cookies Secure.

    Outside development this is unconditionally True — it must not depend on
    correctly reading the scheme through a proxy. `request.url.scheme` only
    says "https" behind Caddy because uvicorn is started with
    `--proxy-headers --forwarded-allow-ips=172.16.0.0/12` in
    docker-compose.prod.yml, and BOTH halves of that are outside this code:
    the image's own Dockerfile CMD has no `--proxy-headers`, and the trusted
    range assumes Docker's default address pool. Either one drifting would
    silently ship non-Secure auth cookies over HTTPS, with nothing failing.
    So the scheme check is kept only as the dev escape hatch (plain-http
    localhost, where a Secure cookie would be accepted and then never sent
    back). `environment` is a Literal, so a typo is a startup error.
    """
    if settings.environment != "development":
        return True
    return request.url.scheme == "https"


def _set_auth_cookies(request: Request, response: Response, raw_refresh: str) -> None:
    secure = _cookie_secure(request)
    max_age = settings.refresh_token_expires_days * 24 * 60 * 60
    response.set_cookie(
        "refresh_token",
        raw_refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=max_age,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(32),
        httponly=False,
        secure=secure,
        samesite="lax",
        path=CSRF_COOKIE_PATH,
        max_age=max_age,
    )


def _clear_auth_cookies(request: Request, response: Response) -> None:
    # Paths must match what was set, or the browser treats these as different
    # cookies and leaves the originals in place. The other attributes are
    # restated for the same reason a scanner would want them: Starlette's
    # delete_cookie defaults to secure=False/httponly=False, so a bare call
    # emits a non-Secure Set-Cookie over HTTPS. Deletion works either way
    # today (browsers match on name+domain+path), but it would break outright
    # under a __Host- prefix, and it looks like a regression in a report.
    secure = _cookie_secure(request)
    response.delete_cookie(
        "refresh_token",
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=CSRF_COOKIE_PATH,
        httponly=False,
        secure=secure,
        samesite="lax",
    )


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
        # Phase L3: SELECT ... FOR UPDATE. Without the lock this was a
        # TOCTOU — two requests could both read consumed_at IS NULL and both
        # mint a successor into the same family, so the mechanism failed
        # *open*, handing out two live tokens where the design promises one.
        # Prod runs `uvicorn --workers 4`, and refresh is now on the boot
        # path of every page load, so concurrent arrivals are routine rather
        # than theoretical. The lock serializes them: the loser then sees
        # consumed_at set and takes the replay path below.
        .with_for_update()
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

        # ...except when the replay is plainly this user's own browser racing
        # itself. Moving the access token into memory (Phase L3) made every
        # page load call /auth/refresh, so two tabs reloaded together — an
        # admin cross-checking a roster against an event page, or a restored
        # session — both send the same cookie. One wins and rotates; the
        # other arrives moments later holding a value that is now consumed.
        # Treating that as theft revoked the family and hard-logged the user
        # out of every tab and device, which is a self-inflicted outage
        # triggered by ordinary use.
        #
        # A replay is read as benign only when it is (a) within a few seconds
        # of the rotation and (b) followed by a live, unconsumed successor in
        # the same family — i.e. the rotation it lost to is still the head of
        # the chain, so nothing has been used since. It still fails the
        # request (401, no new session minted): weakening rotation for
        # convenience is the wrong trade, and the client serializes refreshes
        # across tabs so the correct path is to retry, which will pick up the
        # rotated cookie. What this buys is not nuking the family.
        grace_cutoff = now - timedelta(seconds=REPLAY_GRACE_SECONDS)
        consumed_at = rt.consumed_at
        if consumed_at.tzinfo is None:
            # Defensive: a value written without tzinfo (a raw SQL fixup, or a
            # driver handing back naive datetimes) must not break the compare.
            consumed_at = consumed_at.replace(tzinfo=timezone.utc)
        if consumed_at >= grace_cutoff and rt.family_id is not None:
            # Specifically the IMMEDIATE successor, not "any live token in the
            # family". There is normally exactly one live head per family, so
            # an "any" check would match nearly every replay inside the window
            # and silently widen this far past a tab race. Asking whether the
            # rotation this token lost to is *itself* still unused is what
            # makes it a race: a genuine second tab replays a value one
            # rotation behind. If the chain has moved on since, this is not a
            # race any more and falls through to reuse detection.
            #
            # No replaced_by column exists, so lineage comes from created_at
            # ordering within the family. A tie (same microsecond) fails the
            # strict `>` and falls through to reuse — the safe direction.
            successor = (
                db.query(models.RefreshToken)
                .filter(
                    models.RefreshToken.family_id == rt.family_id,
                    models.RefreshToken.created_at > rt.created_at,
                )
                .order_by(models.RefreshToken.created_at.asc())
                .first()
            )
            successor_is_live = (
                successor is not None
                and successor.consumed_at is None
                and successor.revoked_at is None
                and successor.expires_at.replace(
                    tzinfo=successor.expires_at.tzinfo or timezone.utc
                )
                > now
            )
            if successor_is_live:
                logger.info(
                    "refresh_token_replay_within_grace user_id=%s family_id=%s",
                    rt.user_id,
                    rt.family_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "AUTH_REFRESH_RACE",
                        "detail": "Refresh already rotated; retry",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )
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


# -------------------------
# Routes
# -------------------------


class SetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/set-password", response_model=schemas.Token)
def set_password_from_invite(
    request: Request,
    response: Response,
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

    _set_auth_cookies(request, response, raw_refresh)

    return {
        "access_token": access_token,
        "token_type": "bearer",
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
            models.User.role.in_(STAFF_ROLES),
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
    request: Request,
    response: Response,
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

    _set_auth_cookies(request, response, raw_refresh)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ✅ SECURITY FIX: refresh token is read from an HttpOnly cookie, never JS-visible
# ✅ SECURITY FIX: token is rotated on every successful refresh (T-00-13)
@router.post(
    "/refresh",
    response_model=schemas.Token,
    # 120/min, not the 30/min the other auth routes use. This endpoint is on
    # the boot path of every page load (the access token is in memory now, so
    # a reload has to re-mint it), and rate_limit keys on IP+path — every
    # member of staff behind one campus NAT shares this bucket. At 30 a
    # handful of people reloading would 429 each other out of their sessions.
    # It is still a bound: the refresh token rotates per use, so a stolen
    # cookie gets one use, not 120.
    dependencies=[Depends(rate_limit(120, 60)), Depends(verify_csrf)],
)
def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REFRESH_INVALID", "detail": "Missing refresh token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # _consume_refresh_token validates, marks the old row consumed, and
    # returns the user plus the rotation family the new token must join.
    user, family_id = _consume_refresh_token(db, raw_refresh)

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_raw_refresh = _issue_refresh_token(db, user, family_id=family_id)

    log_action(db, user, "token_refresh", "User", str(user.id))
    db.commit()

    _set_auth_cookies(request, response, new_raw_refresh)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ✅ SECURITY FIX: logout refresh token is read from an HttpOnly cookie
#
# Deliberately does NOT require a valid access token. It used to depend on
# get_current_user, which was safe while the access token sat in
# localStorage and outlived the page — but the token now lives in memory and
# is routinely absent or expired at exactly the moment somebody logs out (any
# reload, or any session older than ACCESS_TOKEN_EXPIRES_MINUTES). The
# dependency would then 401 *before* the body ran, so nothing was revoked and
# nothing was cleared, while the frontend cleared its memory and told the user
# they were logged out. On a shared campus machine the next person's boot
# refresh would walk straight back into the previous session, for the
# remaining life of the refresh cookie. Logging out has to work on the
# strength of the cookie alone.
#
# Being cookie-authenticated now, it needs verify_csrf: a Bearer requirement
# was what made it CSRF-safe before, and a forced logout is a real (if minor)
# nuisance attack.
@router.post(
    "/logout",
    dependencies=[Depends(rate_limit(30, 60)), Depends(verify_csrf)],
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_optional_user),
):
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        _revoke_refresh_token(db, raw_refresh)
    # actor may be None when the access token has already expired; the audit
    # row is still worth writing, and log_action already accepts None.
    log_action(
        db,
        current_user,
        "user_logout",
        "User",
        str(current_user.id) if current_user else None,
    )
    db.commit()
    _clear_auth_cookies(request, response)
    # Unconditional 200: the client has torn down its own state either way,
    # and a failure here would only tell an attacker whether a cookie was live.
    return {"detail": "Logged out"}


