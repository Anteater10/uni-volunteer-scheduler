# backend/app/main.py
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import get_db
from .routers import auth, users, events, slots, signups, notifications, admin, portals, magic, roster, check_in
from .routers.public import events as public_events
from .routers.public import signups as public_signups
from .routers.public import orientation as public_orientation

app = FastAPI(title="University Volunteer Scheduler API")


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
    # TEMP: no CSP so Swagger UI can load CDN assets
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
app.include_router(signups.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(portals.router, prefix="/api/v1")
app.include_router(magic.router, prefix="/api/v1")
app.include_router(roster.router, prefix="/api/v1")
app.include_router(check_in.router, prefix="/api/v1")
# Phase 09: public (unauthenticated) volunteer signup surface
app.include_router(public_events.router, prefix="/api/v1")
app.include_router(public_signups.router, prefix="/api/v1")
app.include_router(public_orientation.router, prefix="/api/v1")
