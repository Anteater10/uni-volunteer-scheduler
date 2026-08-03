# backend/app/main.py
import logging
import os
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import assert_test_mode_allowed, settings
from .database import get_db
from .observability import configure_logging, init_sentry

configure_logging()
init_sentry()
from .routers import auth, users, events, slots, shifts, signups, notifications, admin, magic, roster, check_in, organizer
from .routers.public import events as public_events
from .routers.public import signups as public_signups
from .routers.public import orientation as public_orientation
# Phase 24 — token-gated reminder preferences
from .routers import preferences as public_preferences
# Phase 26 — broadcast messages (organizer/admin → confirmed signups)
from .routers import broadcasts
from .copilot import router as copilot_router

logger = logging.getLogger(__name__)

_expose_tokens = os.environ.get("EXPOSE_TOKENS_FOR_TESTING") == "1"
assert_test_mode_allowed(settings.environment, expose_tokens=_expose_tokens)

_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if settings.environment == "production"
    else {}
)
app = FastAPI(title="University Volunteer Scheduler API", **_docs_kwargs)

if _expose_tokens:
    logger.warning(
        "EXPOSE_TOKENS_FOR_TESTING is ON — confirm tokens will be returned in signup "
        "responses. DO NOT use in production."
    )
    from .routers.test_helpers import router as test_helpers_router


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """AUDIT-03: Normalize every HTTPException into {error, code, detail}.

    - error:  short machine-readable slug derived from the status code
              (e.g. 'http_401'), or the raising site's override
    - code:   when the raising site passed a dict detail with a 'code'
              key (e.g. 'AUTH_REFRESH_INVALID'), surface that; otherwise
              fall back to the same status-code slug
    - detail: original human-readable string detail

    Plan 06 `test_error_response_shape` asserts this shape across the
    auth, signups, and admin routers.
    """
    status_code = exc.status_code
    raw = exc.detail
    if isinstance(raw, dict):
        code = raw.get("code", f"http_{status_code}")
        detail = raw.get("detail", raw.get("message", ""))
        error = raw.get("error", f"http_{status_code}")
    else:
        code = f"http_{status_code}"
        detail = raw if isinstance(raw, str) else str(raw)
        error = f"http_{status_code}"
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "code": code, "detail": detail},
        headers=getattr(exc, "headers", None) or None,
    )

# CORS origins loaded from settings.cors_allowed_origins env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # JSON API — nothing should load subresources or frame it. The docs UI
    # (dev only; disabled entirely in production) needs CDN assets, so those
    # paths stay exempt.
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
    return response


@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    """
    Simple health check that also pings the database.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


# Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(slots.router, prefix="/api/v1")
app.include_router(shifts.router, prefix="/api/v1")
app.include_router(signups.router, prefix="/api/v1")
app.include_router(signups.shift_signups_router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(magic.router, prefix="/api/v1")
app.include_router(roster.router, prefix="/api/v1")
app.include_router(check_in.router, prefix="/api/v1")
# Phase 21: organizer-scoped actions (grant orientation credit, etc.)
app.include_router(organizer.router, prefix="/api/v1")
# Phase 09: public (unauthenticated) volunteer signup surface
app.include_router(public_events.router, prefix="/api/v1")
app.include_router(public_signups.router, prefix="/api/v1")
app.include_router(public_orientation.router, prefix="/api/v1")
# Phase 24 — volunteer reminder opt-out endpoints (token-gated)
app.include_router(public_preferences.router, prefix="/api/v1")
# Phase 26 — broadcast messages (organizer/admin → confirmed signups)
app.include_router(broadcasts.router, prefix="/api/v1")
# Phase 30 (v1.4) — AI Onboarding Copilot, flag-gated to 404 when disabled.
app.include_router(copilot_router.router, prefix="/api/v1")

# Test helpers — only included when EXPOSE_TOKENS_FOR_TESTING=1
if _expose_tokens:
    app.include_router(test_helpers_router)
