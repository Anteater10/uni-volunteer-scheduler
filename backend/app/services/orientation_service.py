"""Orientation status service.

Checks all-time orientation attendance for a volunteer email.
Designed to be enumeration-safe (D-08): returns identical shape regardless
of whether the email exists. No 404 for missing emails.
"""
from sqlalchemy.orm import Session

from ..models import Signup, Slot, Volunteer, SignupStatus, SlotType
from ..schemas import OrientationStatusRead


def has_attended_orientation(db: Session, email: str) -> OrientationStatusRead:
    """Check if any past attended orientation signup exists for this email.

    All-time scope (D-03): no quarter/module filter.
    Enumeration-safe (D-08): returns same shape for unknown emails.

    Args:
        db: DB session.
        email: Raw email string (lowercased internally).

    Returns:
        OrientationStatusRead with has_attended_orientation + last_attended_at.
    """
    row = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .join(Volunteer, Volunteer.id == Signup.volunteer_id)
        .filter(
            Volunteer.email == email.lower().strip(),
            Slot.slot_type == SlotType.ORIENTATION,
            Signup.status == SignupStatus.attended,
        )
        .order_by(Signup.checked_in_at.desc().nullslast())
        .first()
    )
    if row is None:
        return OrientationStatusRead(has_attended_orientation=False, last_attended_at=None)
    return OrientationStatusRead(
        has_attended_orientation=True,
        last_attended_at=row.checked_in_at,
    )
