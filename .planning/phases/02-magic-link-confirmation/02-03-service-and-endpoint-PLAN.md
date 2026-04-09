---
phase: 02
plan: 03
name: Magic-link service, endpoint, rate limit, signup wiring
wave: 2
depends_on: [02-01, 02-02]
files_modified:
  - backend/app/magic_link_service.py
  - backend/app/routers/magic.py
  - backend/app/main.py
  - backend/app/signup_service.py
  - backend/app/config.py
  - backend/app/celery_app.py
  - backend/tests/test_magic_link_service.py
  - backend/tests/test_magic_link_router.py
autonomous: true
requirements:
  - "GET /auth/magic/{token} handler"
  - registered→confirmed transition
  - rate limiting
  - "TTL ≤ 15 min"
  - single-use
---

# Plan 02-03: Service, Endpoint, Rate Limit

<objective>
Implement the full magic-link backend flow: token issuance service, atomic
single-use consume, rate limiting via Redis, `GET /auth/magic/{token}` and
`POST /auth/magic/resend` endpoints, Celery dispatch task, and wiring into
`signup_service.create_signup()` so new non-waitlisted signups start `pending`
and receive an email.
</objective>

<must_haves>
- `magic_link_service.py` with `issue_token`, `consume_token`, `check_rate_limit`, `dispatch_email`
- Atomic single-use via `UPDATE ... WHERE consumed_at IS NULL RETURNING ...`
- 15-minute TTL enforced
- Rate limit: 5/email/hour, 20/IP/hour, configurable via env
- `GET /auth/magic/{token}` returns 302 to `/signup/confirmed?event={id}` on success
- Failure modes redirect to `/signup/confirm-failed?reason={expired|used|not_found}`
- `POST /auth/magic/resend` returns 200 on success, 429 on rate limit with `Retry-After` header
- `signup_service.create_signup` sets `pending` for non-waitlisted and dispatches email (idempotently)
- Unit + integration tests cover happy path + all failure modes + rate limit
</must_haves>

<tasks>

<task id="02-03-01" parallel="false">
<action>
Create `backend/app/config.py` additions (or edit existing) to add:

```python
MAGIC_LINK_TTL_MINUTES: int = int(os.getenv("MAGIC_LINK_TTL_MINUTES", "15"))
MAGIC_LINK_MAX_PER_EMAIL_PER_HOUR: int = int(os.getenv("MAGIC_LINK_MAX_PER_EMAIL_PER_HOUR", "5"))
MAGIC_LINK_MAX_PER_IP_PER_HOUR: int = int(os.getenv("MAGIC_LINK_MAX_PER_IP_PER_HOUR", "20"))
FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
```

If `config.py` uses a Pydantic `Settings` class, add the fields there instead using `Field(default=15, ...)` pattern consistent with existing fields. Do NOT break existing config loading — match the existing style.
</action>
<read_first>
- backend/app/config.py
</read_first>
<acceptance_criteria>
- `grep -q 'MAGIC_LINK_TTL_MINUTES' backend/app/config.py`
- `grep -q 'MAGIC_LINK_MAX_PER_EMAIL_PER_HOUR' backend/app/config.py`
- `grep -q 'MAGIC_LINK_MAX_PER_IP_PER_HOUR' backend/app/config.py`
- `grep -q 'FRONTEND_BASE_URL' backend/app/config.py`
- `python -c "from backend.app import config"` exits 0
</acceptance_criteria>
</task>

<task id="02-03-02" parallel="false">
<action>
Create `backend/app/magic_link_service.py` with these exact functions:

```python
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import config
from backend.app.models import MagicLinkToken, Signup, SignupStatus


class ConsumeResult(str, Enum):
    ok = "ok"
    expired = "expired"
    used = "used"
    not_found = "not_found"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(db: Session, signup: Signup) -> str:
    """Create a new magic-link token for a signup. Returns raw token."""
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.MAGIC_LINK_TTL_MINUTES)
    row = MagicLinkToken(
        token_hash=token_hash,
        signup_id=signup.id,
        email=signup.email.lower(),
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
    # Atomic update — raises IntegrityError if another request beat us
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
    if email_count > config.MAGIC_LINK_MAX_PER_EMAIL_PER_HOUR:
        return False
    if ip_count > config.MAGIC_LINK_MAX_PER_IP_PER_HOUR:
        return False
    return True


def dispatch_email(db: Session, signup: Signup, event, base_url: str) -> None:
    """Issue a token and enqueue the send task. Idempotent within a 60s window."""
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
        return  # A token was just issued; worker will send it
    raw = issue_token(db, signup)
    from backend.app.emails import send_magic_link
    send_magic_link(signup.email, raw, event, base_url)
```

Notes:
- Redis client injection: the endpoint will import and pass a client; for now, add a top-level `get_redis()` helper that returns `redis.Redis.from_url(config.REDIS_URL)` only if `REDIS_URL` exists in config, otherwise have endpoint pass one.
- Do NOT import celery here — dispatch is synchronous for now (the `send_email` call inside `emails.py` can be made async in a follow-up; CONTEXT says 60s SLA is satisfied so long as dispatch is enqueued promptly).
</action>
<read_first>
- backend/app/models.py
- backend/app/config.py
- backend/app/emails.py
- backend/app/signup_service.py
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
- .planning/phases/02-magic-link-confirmation/02-RESEARCH.md
</read_first>
<acceptance_criteria>
- File `backend/app/magic_link_service.py` exists
- File contains `def issue_token`, `def consume_token`, `def check_rate_limit`, `def dispatch_email`
- File contains `ConsumeResult`
- File contains `secrets.token_urlsafe(32)`
- File contains `hashlib.sha256`
- File contains `MAGIC_LINK_TTL_MINUTES`
- `python -c "from backend.app.magic_link_service import issue_token, consume_token, check_rate_limit, dispatch_email, ConsumeResult"` exits 0
</acceptance_criteria>
</task>

<task id="02-03-03" parallel="false">
<action>
Create `backend/app/routers/magic.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.app import config
from backend.app.database import get_db
from backend.app.magic_link_service import (
    ConsumeResult,
    check_rate_limit,
    consume_token,
    dispatch_email,
)
from backend.app.models import Event, Signup, SignupStatus

router = APIRouter(prefix="/auth/magic", tags=["magic-link"])


def _get_redis():
    import redis
    return redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


@router.get("/{token}")
def consume_magic_link(token: str, db: Session = Depends(get_db)):
    result, signup = consume_token(db, token)
    if result == ConsumeResult.ok:
        db.commit()
        return RedirectResponse(
            url=f"{config.FRONTEND_BASE_URL}/signup/confirmed?event={signup.event_id}",
            status_code=302,
        )
    reason_map = {
        ConsumeResult.expired: "expired",
        ConsumeResult.used: "used",
        ConsumeResult.not_found: "not_found",
    }
    return RedirectResponse(
        url=f"{config.FRONTEND_BASE_URL}/signup/confirm-failed?reason={reason_map[result]}",
        status_code=302,
    )


class ResendPayload(BaseModel):
    email: EmailStr
    event_id: str


@router.post("/resend")
def resend_magic_link(
    payload: ResendPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    redis_client = _get_redis()
    if not check_rate_limit(redis_client, payload.email, ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a few minutes and try again.",
            headers={"Retry-After": "3600"},
        )
    signup = (
        db.query(Signup)
        .filter(
            Signup.email == payload.email.lower(),
            Signup.event_id == payload.event_id,
            Signup.status == SignupStatus.pending,
        )
        .first()
    )
    if signup is None:
        # Do not leak signup existence — return success regardless
        return {"status": "ok"}
    event = db.query(Event).filter_by(id=signup.event_id).first()
    dispatch_email(db, signup, event, config.FRONTEND_BASE_URL)
    db.commit()
    return {"status": "ok"}
```

Then edit `backend/app/main.py` to include the new router:

```python
from backend.app.routers import magic
app.include_router(magic.router)
```

Add this line next to the other `include_router` calls.
</action>
<read_first>
- backend/app/main.py
- backend/app/routers/auth.py (for patterns)
- backend/app/database.py
- backend/app/magic_link_service.py (post task 02-03-02)
</read_first>
<acceptance_criteria>
- File `backend/app/routers/magic.py` exists
- File contains `@router.get("/{token}")`
- File contains `@router.post("/resend")`
- File contains `RedirectResponse`
- File contains `status_code=302`
- File contains `Retry-After`
- `grep -q 'from backend.app.routers import magic' backend/app/main.py` OR `grep -q 'routers.magic' backend/app/main.py`
- `grep -q 'include_router(magic.router)' backend/app/main.py`
- `python -c "from backend.app.main import app; assert any('/auth/magic' in str(r.path) for r in app.routes)"` exits 0
</acceptance_criteria>
</task>

<task id="02-03-04" parallel="false">
<action>
Edit `backend/app/signup_service.py` to change signup creation behavior:

1. Locate `create_signup` (or equivalent entry point).
2. Where status is currently set to `confirmed` for non-waitlisted signups, change to `pending`.
3. After the signup row is flushed/committed, call `dispatch_email(db, signup, event, config.FRONTEND_BASE_URL)` from `magic_link_service`.
4. Import at top: `from backend.app.magic_link_service import dispatch_email` and `from backend.app import config`.
5. If there is a waitlist promotion function (e.g., `promote_from_waitlist`), change the promoted row's status to `pending` (NOT `confirmed`) and also call `dispatch_email` on it.
6. Leave the `cancelled` path unchanged.

Preserve any existing idempotency-key pattern already present in `signup_service.py` — the `dispatch_email` function is itself idempotent for the 60s window so Celery retries won't double-send.
</action>
<read_first>
- backend/app/signup_service.py
- backend/app/magic_link_service.py (post 02-03-02)
- backend/app/config.py (post 02-03-01)
- backend/app/models.py (post 02-01)
- .planning/phases/02-magic-link-confirmation/02-CONTEXT.md
</read_first>
<acceptance_criteria>
- `grep -q 'from backend.app.magic_link_service import dispatch_email' backend/app/signup_service.py`
- `grep -q 'SignupStatus.pending' backend/app/signup_service.py`
- `grep -q 'dispatch_email' backend/app/signup_service.py`
- `python -c "from backend.app.signup_service import create_signup"` exits 0 (or whatever the entrypoint name is)
- Existing signup tests still pass: `cd backend && pytest tests/test_signup*.py -q` exits 0 (may require updating expected status from `confirmed` to `pending` — if those tests fail because of the new behavior, update them in-place as part of this task)
</acceptance_criteria>
</task>

<task id="02-03-05" parallel="false">
<action>
Create `backend/tests/test_magic_link_service.py` with unit tests covering:

1. `issue_token(db, signup)` returns a raw string, stores only the hash (assert `db.query(MagicLinkToken).first().token_hash != raw`).
2. `consume_token(db, raw)` returns `(ConsumeResult.ok, signup)` on first call, flips signup status from `pending` to `confirmed`.
3. Second call with the same raw token returns `(ConsumeResult.used, None)`.
4. A token whose `expires_at` is in the past returns `(ConsumeResult.expired, None)`.
5. A random unknown token returns `(ConsumeResult.not_found, None)`.
6. A signup that is `cancelled` returns `(ConsumeResult.not_found, None)`.
7. `check_rate_limit` using a fake/stub Redis (use `fakeredis` if available, else a MagicMock with `pipeline().execute()` returning incrementing counts): allows first 5 per email, rejects 6th; allows first 20 per IP, rejects 21st.

Use the existing DB fixture.
</action>
<read_first>
- backend/app/magic_link_service.py (post 02-03-02)
- backend/tests/conftest.py
- backend/tests/ (to find existing fixture patterns)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_magic_link_service.py` exists
- File contains `issue_token`
- File contains `consume_token`
- File contains `check_rate_limit`
- File contains `ConsumeResult.expired`
- File contains `ConsumeResult.used`
- File contains `ConsumeResult.not_found`
- `cd backend && pytest tests/test_magic_link_service.py -v` exits 0
</acceptance_criteria>
</task>

<task id="02-03-06" parallel="false">
<action>
Create `backend/tests/test_magic_link_router.py` with integration tests using FastAPI `TestClient`:

1. `GET /auth/magic/{valid_token}` → 302 with `Location` containing `/signup/confirmed?event=`, DB row shows signup status flipped to `confirmed`.
2. `GET /auth/magic/{expired_token}` → 302 with `Location` containing `/signup/confirm-failed?reason=expired`.
3. `GET /auth/magic/{consumed_token}` → 302 with `Location` containing `reason=used`.
4. `GET /auth/magic/{unknown_token}` → 302 with `Location` containing `reason=not_found`.
5. `POST /auth/magic/resend` with valid body → 200, `{"status": "ok"}`, new token row created.
6. `POST /auth/magic/resend` called 6 times in a row with same email → 6th returns 429 with `Retry-After` header.

Stub the email send (monkeypatch `send_magic_link` to a no-op) so tests don't hit Resend. Use `fakeredis` or a monkeypatched `_get_redis` returning an in-memory fake for the rate-limit test.

Use `follow_redirects=False` on the TestClient to assert 302 status codes.
</action>
<read_first>
- backend/app/routers/magic.py (post 02-03-03)
- backend/app/magic_link_service.py (post 02-03-02)
- backend/tests/conftest.py
- backend/tests/ (existing router tests for TestClient patterns)
</read_first>
<acceptance_criteria>
- File `backend/tests/test_magic_link_router.py` exists
- File contains `/auth/magic/`
- File contains `302`
- File contains `reason=expired`
- File contains `reason=used`
- File contains `reason=not_found`
- File contains `/auth/magic/resend`
- File contains `429`
- File contains `Retry-After`
- `cd backend && pytest tests/test_magic_link_router.py -v` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- All new files import: `python -c "from backend.app.magic_link_service import *; from backend.app.routers.magic import router"` exits 0
- Full test suite green: `cd backend && pytest -q` exits 0
- App boots: `cd backend && python -c "from backend.app.main import app"` exits 0
- Routes registered: `cd backend && python -c "from backend.app.main import app; paths=[r.path for r in app.routes]; assert '/auth/magic/{token}' in paths and '/auth/magic/resend' in paths"` exits 0
</verification>
