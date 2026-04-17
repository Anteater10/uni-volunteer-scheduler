"""Audit-log humanization service (Phase 16 Plan 01, D-19 / D-34).

Resolves actor and entity IDs on an AuditLog row to human-readable strings the
admin Audit page can render without another round-trip to the DB. Deleted
(tombstoned) rows render as "(deleted) #xxxxxxxx" where the suffix is the first
8 chars of the original UUID, so the history stays auditable even after CCPA
deletions.

Used by the admin audit-log list endpoint and the audit-log CSV export. Pure
read side — no writes, no side-effects.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app import models


ACTION_LABELS: dict[str, str] = {
    "signup_cancelled": "Cancelled a signup",
    "signup_promote": "Promoted from waitlist",
    "signup_move": "Moved a signup to a different slot",
    "signup_resend": "Resent a confirmation email",
    "signup_ics_export": "Exported a signup calendar file",
    "admin_signup_cancel": "Admin cancelled a signup",
    "user_invite": "Invited a new user",
    "user_deactivate": "Deactivated a user",
    "user_reactivate": "Reactivated a user",
    "user_update": "Updated a user",
    "user_login": "Logged in",
    "ccpa_export": "Exported a user's personal data (CCPA)",
    "ccpa_delete": "Deleted a user's personal data (CCPA)",
    "event_create": "Created an event",
    "event_update": "Updated an event",
    "event_notify": "Sent a notification to event attendees",
    "template_create": "Created a module template",
    "template_update": "Updated a module template",
    "template_delete": "Archived a module template",
    "import_upload": "Uploaded a CSV import",
    "import_commit": "Committed a CSV import",
    # Phase 21 — orientation credit engine
    "orientation_credit_grant": "Granted orientation credit",
    "orientation_credit_revoke": "Revoked orientation credit",
    # Phase 22 — custom form fields
    "form_schema_set": "Updated event form fields",
    "form_schema_template_set": "Updated template default form fields",
    "form_schema_field_append": "Added a form field to an event",
    # Phase 23 — recurring event duplication
    "event_duplicate": "Duplicated an event",
    # Phase 25 — waitlist manual override surfaces
    "waitlist_promote_manual": "Promoted from waitlist (manual override)",
    "waitlist_reorder": "Reordered the waitlist",
}


def _short(id_val: Any) -> str:
    s = str(id_val) if id_val is not None else ""
    return s[:8] if s else "unknown"


def _resolve_actor(
    actor_id: Any, db: Session
) -> Tuple[str, Optional[str]]:
    if actor_id is None:
        return ("System", None)
    user = db.query(models.User).filter(models.User.id == actor_id).first()
    if user is None:
        return (f"(deleted) #{_short(actor_id)}", None)
    label = user.name or user.email or f"User #{_short(user.id)}"
    role = user.role.value if user.role else None
    return (label, role)


def _resolve_entity(
    entity_type: Optional[str], entity_id: Any, db: Session
) -> str:
    if not entity_type or entity_id is None:
        return ""
    et = entity_type.lower()

    if et == "user":
        u = db.query(models.User).filter(models.User.id == entity_id).first()
        if not u:
            return f"(deleted) #{_short(entity_id)}"
        return u.name or u.email or f"User #{_short(u.id)}"

    if et == "event":
        e = db.query(models.Event).filter(models.Event.id == entity_id).first()
        if not e:
            return f"(deleted) #{_short(entity_id)}"
        date_str = e.start_date.date().isoformat() if e.start_date else ""
        return f"{e.title} on {date_str}".rstrip(" on ").rstrip()

    if et == "signup":
        s = (
            db.query(models.Signup)
            .filter(models.Signup.id == entity_id)
            .first()
        )
        if not s:
            return f"(deleted) #{_short(entity_id)}"
        vol = s.volunteer
        if vol:
            first = (vol.first_name or "").strip()
            last = (vol.last_name or "").strip()
            vol_name = (f"{first} {last}".strip()) or vol.email or "a student"
        else:
            vol_name = "a student"
        ev_title = (
            s.slot.event.title if s.slot and s.slot.event else "an event"
        )
        ev_date = (
            s.slot.event.start_date.date().isoformat()
            if s.slot and s.slot.event and s.slot.event.start_date
            else ""
        )
        if ev_date:
            return f"{vol_name}'s signup for {ev_title}, {ev_date}"
        return f"{vol_name}'s signup for {ev_title}"

    if et == "slot":
        sl = db.query(models.Slot).filter(models.Slot.id == entity_id).first()
        if not sl:
            return f"(deleted) #{_short(entity_id)}"
        slot_type = sl.slot_type.value if sl.slot_type else "slot"
        ev_title = sl.event.title if sl.event else "an event"
        return f"{slot_type} in {ev_title}"

    if et in ("template", "moduletemplate", "module_template"):
        t = (
            db.query(models.ModuleTemplate)
            .filter(models.ModuleTemplate.slug == entity_id)
            .first()
        )
        if not t:
            return f"(deleted) #{_short(entity_id)}"
        return t.name

    # Phase 21 — orientation credit
    if et in ("orientationcredit", "orientation_credit"):
        c = (
            db.query(models.OrientationCredit)
            .filter(models.OrientationCredit.id == entity_id)
            .first()
        )
        if not c:
            return f"(deleted) #{_short(entity_id)}"
        return f"{c.volunteer_email} ({c.family_key})"

    return f"#{_short(entity_id)}"


def humanize(log: models.AuditLog, db: Session) -> dict:
    """Return a JSON-serializable dict for a single AuditLog row.

    Shape matches what the admin audit page + CSV export both consume.
    """
    actor_label, actor_role = _resolve_actor(log.actor_id, db)
    action = log.action or ""
    return {
        "id": str(log.id),
        "action": action,
        "action_label": ACTION_LABELS.get(
            action, action.replace("_", " ").capitalize() if action else ""
        ),
        "actor_id": str(log.actor_id) if log.actor_id else None,
        "actor_label": actor_label,
        "actor_role": actor_role,
        "entity_type": log.entity_type,
        "entity_id": str(log.entity_id) if log.entity_id else None,
        "entity_label": _resolve_entity(log.entity_type, log.entity_id, db),
        "payload": getattr(log, "extra", None),
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
    }
