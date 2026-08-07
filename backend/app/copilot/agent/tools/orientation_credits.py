"""Orientation credits: who is allowed to sign up for what.

Credit is keyed by ``(volunteer email, family_key)`` and is permanent — once
oriented for a module family, oriented forever, in every quarter. That
permanence is the reason these tools are shaped the way they are: a grant is
not a booking that expires next week, it is a standing statement about a
person, so ``grant_orientation_credit`` asks for the module by name and
refuses to guess which family the user meant.

Emails go **in** but never come **out**. The boundary redactor rewrites any
email in a tool result to ``[REDACTED:email]``, so a tool returning a list
of addresses returns a list of nothing useful. Every tool here is therefore
keyed by an email the user has already said out loud, and answers about
that one person. "Who has credit for CRISPR" is a report, and reports are
what the Exports surface is for.

The family a module belongs to is not something a model can work out from
a name — ``crispr-advanced`` may or may not share an orientation with
``crispr-intro``, and only the template says which. So these tools take a
module slug and resolve it, rather than taking a family key the model
guessed.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ambiguous, ask_for
from app.copilot.agent.tools.base import Tool
from app.models import Module, OrientationCredit, User, UserRole
from app.services import orientation_service

_CREDIT_SCHEMA = [
    "credit_id",
    "family_key",
    "module_slug",
    "has_credit",
    "source",
    "granted_at",
    "revoked_at",
    "revoked",
    "granted",
    "notes",
    "credits",
    "count",
    "covers_modules",
]


def _family_for_slug(db: Session, slug: str) -> str | None:
    """The orientation family a module belongs to, or None if no such module.

    Falls back to the slug itself the same way ``orientation_service`` does,
    so a legacy module with no template row still groups with itself instead
    of silently matching everything.
    """
    template = db.query(Module).filter(Module.slug == slug).one_or_none()
    if template is None:
        return None
    return template.family_key or template.slug


def _modules_in_family(db: Session, family_key: str) -> list[str]:
    """Every module this credit also covers.

    Surfaced on every result because a family is invisible from the outside:
    granting credit for "CRISPR intro" may quietly admit someone to three
    other modules, and the admin should read that back before it happens,
    not discover it on a roster.
    """
    rows = (
        db.query(Module)
        .filter(Module.deleted_at.is_(None))
        .filter((Module.family_key == family_key) | (Module.slug == family_key))
        .order_by(Module.slug)
        .all()
    )
    return [m.slug for m in rows]


def _resolve_family(
    db: Session, args: dict[str, Any]
) -> tuple[str | None, dict[str, Any] | None]:
    """(family_key, objection). Exactly one of the two is None."""
    slug = args.get("module_slug")
    if slug:
        family = _family_for_slug(db, str(slug).strip().lower())
        if family is None:
            return None, {
                "error": (
                    f"no module template with slug {slug!r} — call "
                    "list_module_templates for the real slugs"
                )
            }
        return family, None
    if args.get("family_key"):
        return str(args["family_key"]).strip(), None
    return None, ask_for(
        [
            "which module the orientation is for — the slug, e.g. "
            "crispr-gene-editing-basics. Orientation credit covers a whole "
            "module family, so the wrong slug grants access to the wrong set "
            "of modules."
        ]
    )


def _email(args: dict[str, Any]) -> str | None:
    raw = args.get("email")
    if not raw:
        return None
    cleaned = str(raw).strip().lower()
    return cleaned or None


# ------------------------------------------------------------ check


def _check_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    email = _email(args)
    if email is None:
        return {"error": "no email given"}
    family, objection = _resolve_family(db, args)
    if objection is not None:
        return objection

    status = orientation_service.has_orientation_credit(db, email, family)
    return schema_apply(
        {
            "family_key": family,
            "has_credit": status.has_credit,
            "source": status.source,
            "granted_at": status.last_attended_at.isoformat()
            if status.last_attended_at
            else None,
            "covers_modules": _modules_in_family(db, family),
        },
        allowed_fields=_CREDIT_SCHEMA,
    )


CHECK_ORIENTATION_CREDIT_TOOL = Tool(
    name="check_orientation_credit",
    description=(
        "Check whether one volunteer has orientation credit for a module. "
        "Takes their email and the module's slug; credit covers the module's "
        "whole orientation family, and the result lists which modules that "
        "is. Credit is permanent — it never expires and quarters do not gate "
        "it. Read-only."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "The volunteer's email."},
            "module_slug": {
                "type": "string",
                "description": "From list_module_templates.",
            },
            "family_key": {
                "type": "string",
                "description": "Only if the user named a family directly.",
            },
        },
        "required": ["email"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_CREDIT_SCHEMA,
    handler=_check_handler,
)


# ------------------------------------------------------------ list


def _list_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    email = _email(args)
    if email is None:
        return {"error": "no email given"}

    q = db.query(OrientationCredit).filter(
        OrientationCredit.volunteer_email == email
    )
    if args.get("include_revoked") is not True:
        q = q.filter(OrientationCredit.revoked_at.is_(None))
    rows = q.order_by(OrientationCredit.granted_at.desc()).limit(100).all()

    credits = [
        {
            # The id is the point of this tool: revoke_orientation_credit
            # needs one, and there is nowhere else to get it.
            "credit_id": str(c.id),
            "family_key": c.family_key,
            "source": c.source.value,
            "granted_at": c.granted_at.isoformat() if c.granted_at else None,
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            "notes": c.notes,
        }
        for c in rows
    ]
    return schema_apply(
        {"credits": credits, "count": len(credits)},
        allowed_fields=_CREDIT_SCHEMA,
    )


LIST_ORIENTATION_CREDITS_TOOL = Tool(
    name="list_orientation_credits",
    description=(
        "List one volunteer's orientation credits, with the credit_id needed "
        "to revoke one. Keyed by email — there is no way to list everybody, "
        "because a tool result cannot carry email addresses back. Read-only."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "include_revoked": {
                "type": "boolean",
                "description": "Revoked credits are hidden by default.",
            },
        },
        "required": ["email"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_CREDIT_SCHEMA,
    handler=_list_handler,
)


# ------------------------------------------------------------ grant


def _grant_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if _email(args) is None:
        missing.append("the volunteer's email address")
    if not args.get("module_slug") and not args.get("family_key"):
        missing.append(
            "which module the orientation is for — its slug, from "
            "list_module_templates"
        )
    if missing:
        return ask_for(missing)

    family, objection = _resolve_family(db, args)
    if objection is not None or family is None:
        return None  # the handler will report it

    if args.get("acknowledged_family"):
        return None

    covered = _modules_in_family(db, family)
    if len(covered) > 1:
        # Not a missing value — a consequence the user probably does not
        # know about. Granting for one CRISPR module admits them to all of
        # them, and that is worth one sentence before it happens rather
        # than a discovery on a roster later.
        #
        # ``acknowledged_family`` is what makes this answerable: without a
        # flag the model would re-send identical args and loop here forever.
        return ambiguous(
            [
                f"granting orientation credit for this module also covers "
                f"{', '.join(covered)} — they share an orientation family "
                f"('{family}'). Put that to the user, and if they agree call "
                f"this tool again with acknowledged_family=true."
            ]
        )
    return None


def _actor_id(db: Session, scope: Scope):
    if getattr(scope, "caller_id", None):
        return scope.caller_id
    admin = db.query(User).filter(User.role == UserRole.admin).first()
    return admin.id if admin else None


def _grant_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    email = _email(args)
    if email is None:
        return {"error": "no email given"}
    family, objection = _resolve_family(db, args)
    if objection is not None:
        return objection

    already = orientation_service.has_orientation_credit(db, email, family)
    if already.has_credit:
        # Duplicate rows are legal (the table is an audit trail) but a second
        # identical grant tells the admin nothing and clutters the trail.
        return schema_apply(
            {
                "granted": False,
                "family_key": family,
                "has_credit": True,
                "source": already.source,
                "notes": "already has credit for this family; nothing changed",
                "covers_modules": _modules_in_family(db, family),
            },
            allowed_fields=_CREDIT_SCHEMA,
        )

    credit = orientation_service.grant_orientation_credit(
        db,
        email,
        family,
        granted_by_user_id=_actor_id(db, scope),
        notes=args.get("notes"),
    )
    db.commit()
    db.refresh(credit)

    return schema_apply(
        {
            "granted": True,
            "credit_id": str(credit.id),
            "family_key": family,
            "has_credit": True,
            "source": credit.source.value,
            "granted_at": credit.granted_at.isoformat()
            if credit.granted_at
            else None,
            "notes": credit.notes,
            "covers_modules": _modules_in_family(db, family),
        },
        allowed_fields=_CREDIT_SCHEMA,
    )


GRANT_ORIENTATION_CREDIT_TOOL = Tool(
    name="grant_orientation_credit",
    description=(
        "Give a volunteer orientation credit for a module without them "
        "attending one — the vouched-for case: a walk-in, a returning "
        "volunteer, a correction. Credit is permanent and covers the "
        "module's whole orientation family, so the tool names every module "
        "it will admit them to and asks for that to be acknowledged before "
        "granting. Does nothing if they already have it. Requires user "
        "confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "module_slug": {
                "type": "string",
                "description": "From list_module_templates.",
            },
            "family_key": {"type": "string"},
            "notes": {
                "type": "string",
                "description": "Why — this is the audit trail's only context.",
            },
            "acknowledged_family": {
                "type": "boolean",
                "description": (
                    "Set true only after the user has been told which modules "
                    "the credit covers and agreed."
                ),
            },
        },
        "required": ["email"],
    },
    allowed_roles=["admin", "organizer"],
    requires_confirmation=True,
    pii_schema=_CREDIT_SCHEMA,
    handler=_grant_handler,
    precheck=_grant_precheck,
)


# ------------------------------------------------------------ revoke


def _revoke_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("credit_id"):
        return ask_for(
            [
                "which credit to revoke — call list_orientation_credits with "
                "the volunteer's email and read the credit_id from it"
            ]
        )
    return None


def _revoke_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    try:
        credit_id = UUID(str(args["credit_id"]))
    except (ValueError, TypeError):
        return {"error": f"{args.get('credit_id')!r} is not a credit id"}

    credit = orientation_service.revoke_orientation_credit(db, credit_id)
    if credit is None:
        return {"error": "no credit with that id"}
    db.commit()
    db.refresh(credit)

    return schema_apply(
        {
            "revoked": True,
            "credit_id": str(credit.id),
            "family_key": credit.family_key,
            "revoked_at": credit.revoked_at.isoformat()
            if credit.revoked_at
            else None,
            "covers_modules": _modules_in_family(db, credit.family_key),
        },
        allowed_fields=_CREDIT_SCHEMA,
    )


REVOKE_ORIENTATION_CREDIT_TOOL = Tool(
    name="revoke_orientation_credit",
    description=(
        "Revoke one orientation credit by its credit_id, from "
        "list_orientation_credits. This genuinely removes the credit — "
        "nothing re-derives it from past attendance — so the volunteer stops "
        "being eligible for every module in that family. Idempotent. "
        "Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "credit_id": {
                "type": "string",
                "description": "From list_orientation_credits.",
            }
        },
        "required": ["credit_id"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_CREDIT_SCHEMA,
    handler=_revoke_handler,
    precheck=_revoke_precheck,
)
