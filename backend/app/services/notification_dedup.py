"""One canonical dedup insert per anchor for ``sent_notifications``.

The exactly-once guarantee behind every email is a single ``INSERT ... ON
CONFLICT DO NOTHING``: whoever inserts the ``(anchor, kind)`` row first sends,
everyone else sees ``rowcount == 0`` and stays quiet.

2026-08-02 shifts made the table dual-anchored — exactly one of ``signup_id``
(orientation) or ``shift_signup_id`` (a shift commitment) is set. Since both
columns are nullable, one unique index spanning them would treat every
``(NULL, kind)`` pair as distinct and silently disable dedup, so uniqueness
lives in two *partial* unique indexes instead.

That makes the insert subtly conditional: Postgres only infers a partial index
when ``ON CONFLICT`` repeats the index predicate, so ``index_where`` is
mandatory. Omit it and you do not get a weaker dedup, you get
``InvalidColumnReference`` and no email at all.

This module exists because that statement had been copy-pasted to four call
sites and two of them shipped without the predicate — orientation reminders and
every broadcast raised instead of sending. The omission is near-invisible in
review: the broken form looks like a tidier version of the correct one. One
implementation per anchor removes the opportunity.

Kept free of Celery imports so both ``celery_app`` and the service layer can
import it at module scope without a cycle.
"""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import models


def dedup_insert_signup(db: Session, signup_id, kind: str) -> bool:
    """Claim ``(signup_id, kind)``. True when this caller is the first sender.

    The orientation anchor: an orientation slot is still booked with a
    ``Signup`` end to end.
    """
    stmt = (
        pg_insert(models.SentNotification)
        .values(signup_id=signup_id, kind=kind)
        .on_conflict_do_nothing(
            index_elements=["signup_id", "kind"],
            index_where=models.SentNotification.signup_id.isnot(None),
        )
    )
    return db.execute(stmt).rowcount == 1


def dedup_insert_shift_signup(db: Session, shift_signup_id, kind: str) -> bool:
    """Claim ``(shift_signup_id, kind)``. True when this caller is first.

    The commitment anchor. Independent of the signup anchor by design: a
    volunteer can hold an orientation signup *and* a shift commitment on the
    same event, and both are entitled to their own reminder.
    """
    stmt = (
        pg_insert(models.SentNotification)
        .values(shift_signup_id=shift_signup_id, kind=kind)
        .on_conflict_do_nothing(
            index_elements=["shift_signup_id", "kind"],
            index_where=models.SentNotification.shift_signup_id.isnot(None),
        )
    )
    return db.execute(stmt).rowcount == 1
