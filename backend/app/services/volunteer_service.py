"""Volunteer upsert service.

Uses INSERT ... ON CONFLICT DO UPDATE for atomic upsert by email.
The UNIQUE(email) index on volunteers is the conflict target.
"""
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Volunteer


def upsert_volunteer(
    db: Session,
    email: str,
    first_name: str,
    last_name: str,
    phone_e164: str | None,
) -> Volunteer:
    """Upsert a Volunteer row by email using pg ON CONFLICT DO UPDATE.

    If a Volunteer with this email already exists, update first_name, last_name,
    phone_e164, and updated_at. Returns the Volunteer row (existing or new).

    This is safe under concurrent submissions from the same email.
    """
    stmt = (
        pg_insert(Volunteer)
        .values(
            email=email.lower().strip(),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_e164=phone_e164,
        )
        .on_conflict_do_update(
            index_elements=["email"],
            set_={
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
                "phone_e164": phone_e164,
                "updated_at": func.now(),
            },
        )
        .returning(Volunteer.id)
    )
    result = db.execute(stmt)
    volunteer_id = result.scalar_one()
    db.flush()
    return db.get(Volunteer, volunteer_id)
