# backend/app/main.py
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from .config import settings
from .database import get_db
from .routers import auth, users, events, slots, signups, notifications, admin, portals

app = FastAPI(title="University Volunteer Scheduler API")

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
