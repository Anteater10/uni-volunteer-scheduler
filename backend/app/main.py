# backend/app/main.py
import logging
import os
import threading
from contextlib import asynccontextmanager

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

# W5 S-05: fail-closed. Interactive docs are served only in development, not
# "everywhere except the one string 'production'". /docs, /redoc and
# /openapi.json together publish every route, every schema and every required
# field in the app — a complete map for anyone who finds the hostname — so the
# check that hides them must not be one typo away from serving them.
_docs_kwargs = (
    {}
    if settings.environment == "development"
    else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)


def _prewarm_models() -> None:
    """Load the two local models so the first real question doesn't pay for it.

    BASE-CONFIG-02 companion. Both are lru_cache'd singletons loaded on first
    use, per worker process — the reranker alone is ~1.1GB. Without this, the
    first copilot question after a deploy or restart waits for that load, and
    with several uvicorn workers the first question to each worker waits again.

    Deliberately tolerant: a prewarm failure logs and returns. This runs on a
    thread with nothing waiting on it, the lazy loaders are still in place, and
    a copilot that cannot warm up must not be able to stop the API — every
    non-copilot route works without either model.
    """
    import time

    def _load_reranker():
        from .copilot.retrieval.rerank import _model

        _model()

    def _load_embeddings():
        # The local provider specifically, not whatever is configured as
        # primary: this exists to touch the on-disk weights, and warming a Jina
        # primary would spend an API call on a request nobody made.
        from .corpus.embeddings import LocalBgeEmbeddingProvider

        LocalBgeEmbeddingProvider(model=settings.local_embedding_model).embed(
            ["warmup"]
        )

    for label, load in (
        ("reranker", _load_reranker),
        ("embeddings", _load_embeddings),
    ):
        started = time.monotonic()
        try:
            load()
        except Exception:
            logger.exception("model_prewarm_failed component=%s", label)
            continue
        logger.info(
            "model_prewarm_ok component=%s seconds=%.1f",
            label,
            time.monotonic() - started,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.copilot_enabled and settings.copilot_prewarm_on_startup:
        # A thread, not an await: readiness must not wait on ~1.3GB of weights,
        # or the container healthcheck fails the deploy it was meant to protect.
        threading.Thread(
            target=_prewarm_models, name="model-prewarm", daemon=True
        ).start()
    yield


app = FastAPI(
    title="UCSB SciTrek Volunteer Scheduler API", lifespan=lifespan, **_docs_kwargs
)

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
