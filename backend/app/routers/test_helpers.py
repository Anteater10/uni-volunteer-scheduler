"""Test-only helpers — included ONLY when EXPOSE_TOKENS_FOR_TESTING=1.

These endpoints exist solely to enable idempotent E2E seed scripts.
They must NEVER be included in production deployments.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Signup, Slot, Volunteer, SignupStatus

router = APIRouter(prefix="/api/v1/test", tags=["test-helpers"])


@router.delete("/seed-cleanup", status_code=204)
def seed_cleanup(
    emails: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete cancelled signups for the given comma-separated volunteer emails.

    This allows the seed script to recreate signups that were previously
    cancelled, working around the UNIQUE(volunteer_id, slot_id) constraint.

    Only available when EXPOSE_TOKENS_FOR_TESTING=1.
    """
    email_list = [e.strip().lower() for e in emails.split(",") if e.strip()]
    if not email_list:
        return

    volunteers = (
        db.query(Volunteer)
        .filter(Volunteer.email.in_(email_list))
        .all()
    )
    volunteer_ids = [v.id for v in volunteers]
    if not volunteer_ids:
        return

    db.query(Signup).filter(
        Signup.volunteer_id.in_(volunteer_ids),
        Signup.status == SignupStatus.cancelled,
    ).delete(synchronize_session=False)
    db.commit()


@router.delete("/event-signups-cleanup", status_code=204)
def event_signups_cleanup(
    event_id: str,
    keep_emails: str,
    db: Session = Depends(get_db),
) -> None:
    """Cancel all non-essential signups for an event to prevent slot capacity issues.

    Cancels all pending/confirmed signups for the event EXCEPT volunteers in
    keep_emails. This prevents test slot capacity exhaustion from repeated runs.

    Only available when EXPOSE_TOKENS_FOR_TESTING=1.
    """
    keep_email_list = [e.strip().lower() for e in keep_emails.split(",") if e.strip()]

    # Find keep-volunteer IDs
    keep_vols = (
        db.query(Volunteer)
        .filter(Volunteer.email.in_(keep_email_list))
        .all()
    ) if keep_email_list else []
    keep_vol_ids = {v.id for v in keep_vols}

    # Get all slot IDs for this event
    slot_ids = [
        row.id for row in db.query(Slot.id).filter(Slot.event_id == event_id).all()
    ]
    if not slot_ids:
        return

    # Find all cancellable signups not in keep list
    to_cancel = (
        db.query(Signup)
        .filter(
            Signup.slot_id.in_(slot_ids),
            Signup.status.in_([SignupStatus.pending, SignupStatus.confirmed]),
            ~Signup.volunteer_id.in_(keep_vol_ids) if keep_vol_ids else True,
        )
        .all()
    )

    for signup in to_cancel:
        signup.status = SignupStatus.cancelled

    if to_cancel:
        # Recompute slot counts
        for slot_id in slot_ids:
            confirmed_count = (
                db.query(Signup)
                .filter(
                    Signup.slot_id == slot_id,
                    Signup.status.in_([SignupStatus.pending, SignupStatus.confirmed]),
                )
                .count()
            )
            slot = db.query(Slot).filter(Slot.id == slot_id).first()
            if slot:
                slot.current_count = confirmed_count

    db.commit()
