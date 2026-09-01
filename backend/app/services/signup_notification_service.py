"""Resolve admin recipients for school-branch signup notifications."""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)


def branch_for_event(db: Session, event: models.Event) -> models.SchoolBranch:
    """Return the module branch, routing legacy/unmatched events to everyone."""
    module = None
    if event.module_slug:
        module = (
            db.query(models.Module)
            .filter(models.Module.slug == event.module_slug)
            .first()
        )
    if module is None:
        logger.warning(
            "signup_notification_unmatched_module event_id=%s module_slug=%s "
            "fallback_branch=both",
            event.id,
            event.module_slug,
        )
        return models.SchoolBranch.both
    return module.school_branch


def eligible_admin_ids_for_event(db: Session, event_id: UUID) -> list[UUID]:
    """Return active, opted-in admins matched to an event's module branch."""
    event = db.get(models.Event, event_id)
    if event is None:
        return []

    event_branch = branch_for_event(db, event)
    query = db.query(models.User.id).filter(
        models.User.role == models.UserRole.admin,
        models.User.is_active.is_(True),
        models.User.deleted_at.is_(None),
        models.User.notify_email.is_(True),
    )
    if event_branch != models.SchoolBranch.both:
        query = query.filter(
            models.User.school_branch.in_(
                [event_branch, models.SchoolBranch.both]
            )
        )
    return [row.id for row in query.order_by(models.User.id).all()]
