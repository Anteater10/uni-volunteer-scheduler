"""Volunteer upsert service.

Uses INSERT ... ON CONFLICT DO NOTHING for atomic insert-if-absent by email.
The UNIQUE(email) index on volunteers is the conflict target.
"""
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
    """Insert a Volunteer row by email if absent; otherwise return the existing one.

    Returns the Volunteer row (existing or new). Safe under concurrent
    submissions from the same email.

    **This used to be ON CONFLICT DO UPDATE**, rewriting first_name,
    last_name and phone_e164 on every signup. The public signup form is
    unauthenticated and email ownership is not verified at submit time, so
    anyone who knew a volunteer's address could retype their name and phone
    number and the record would silently take it — quietly repointing the
    reminder SMS for someone else's shift. It also meant an honest typo on
    one signup overwrote the good data from every previous one.

    Identity here is the email address. Everything hanging off a volunteer —
    signups, credits, preferences — is keyed to it, so a later submission
    carrying different details is not evidence that the details changed; it
    is one unverified claim about an existing record. Corrections belong on
    an authenticated path (staff edit, or a confirmed magic-link session),
    which is where they can be attributed.
    """
    normalized = email.lower().strip()
    stmt = (
        pg_insert(Volunteer)
        .values(
            email=normalized,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_e164=phone_e164,
        )
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(Volunteer.id)
    )
    volunteer_id = db.execute(stmt).scalar_one_or_none()
    db.flush()

    if volunteer_id is None:
        # DO NOTHING returns no row on conflict — the volunteer already
        # exists and keeps the details it already had.
        return (
            db.query(Volunteer)
            .filter(Volunteer.email == normalized)
            .one()
        )
    return db.get(Volunteer, volunteer_id)
