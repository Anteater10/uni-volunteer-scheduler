"""Public orientation-status endpoint — no authentication required.

GET /public/orientation-status?email=  — check if a volunteer has attended orientation (all-time)

Enumeration defense (D-08): returns identical shape for unknown and known emails.
Anti-enumeration rate limit: 5/min/IP (tightest on any public endpoint).
"""
from fastapi import APIRouter, Depends, Query
from pydantic import EmailStr
from sqlalchemy.orm import Session

from ... import schemas
from ...database import get_db
from ...deps import rate_limit
from ...services.orientation_service import has_attended_orientation

router = APIRouter(prefix="/public", tags=["public"])


@router.get(
    "/orientation-status",
    response_model=schemas.OrientationStatusRead,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
)
def orientation_status(
    email: EmailStr = Query(...),
    db: Session = Depends(get_db),
):
    """Check orientation attendance status for an email.

    D-08: returns same shape regardless of email existence (no 404 for missing email).
    T-09-06: combined with rate limit (5/min/IP) bounds oracle attacks.
    """
    # D-08: no 404; identical shape for unknown emails
    return has_attended_orientation(db, str(email))
