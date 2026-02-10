# backend/app/main.py
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from .deps import limiter
from .database import get_db
from .routers import auth, users, events, slots, signups, notifications, admin, portals

app = FastAPI(title="University Volunteer Scheduler API")

# Rate limiting middleware
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
# ✅ Return clean 429 responses when rate limited
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
origins = [
    # Dev frontends
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # TODO: add your production frontend origin here, e.g.:
    # "https://volunteer.your-university.edu",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
