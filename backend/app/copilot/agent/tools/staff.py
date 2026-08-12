"""Staff accounts: who can log in, and as what.

The Users surface, from the copilot's side. Four verbs — list, invite,
change role, deactivate/reactivate — and one rule underneath all of them:
**the last active admin is untouchable.** Deactivating them or demoting
them locks every human out of the admin surface, including the person who
asked, and there is no way back in from the chat window they just did it
from. Both write paths count the remaining admins under a row lock before
they act, the same way ``users.py`` does.

Note what is not here. There is no delete: the router's delete path is the
CCPA erasure flow, which takes a written reason and is not something to
trigger from a sentence. There is no password reset either — invites go out
as magic links and that is the whole account-recovery story.

Names come back; emails do not. The boundary redactor rewrites any address
in a result, so ``list_staff`` returns names and roles and the user_id the
write tools need, and the invite tool takes an email the admin typed.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.copilot.agent.boundary.role_scope import Scope
from app.copilot.agent.boundary.schema_filter import apply as schema_apply
from app.copilot.agent.tools._ask import ask_for, suggesting
from app.copilot.agent.tools.base import Tool
from app.models import User, UserRole

_STAFF_SCHEMA = [
    "user_id",
    "name",
    "role",
    "active",
    "staff",
    "count",
    "invited",
    "changed",
    "from_role",
    "to_role",
    "invite_email_sent",
    "active_admins_remaining",
]

# Participants are not staff. The role still exists on the model for legacy
# rows, but nobody is created with it since the account-less realignment, and
# offering it here would let the copilot mint an account that can log in and
# do nothing.
_ASSIGNABLE = ("admin", "organizer")


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _row(user: User) -> dict[str, Any]:
    return {
        "user_id": str(user.id),
        "name": user.name,
        "role": user.role.value,
        "active": bool(user.is_active),
    }


def _get(db: Session, user_id: Any) -> User | None:
    key = _as_uuid(user_id)
    if key is None:
        return None
    return (
        db.query(User)
        .filter(User.id == key, User.deleted_at.is_(None))
        .one_or_none()
    )


def _other_active_admins(db: Session, exclude_id) -> int:
    """Active admins other than this one, counted under a row lock.

    Materialised and counted in Python because Postgres refuses FOR UPDATE
    alongside an aggregate — same shape as ``users.py``, and the admin table
    is a handful of rows.
    """
    rows = (
        db.query(User.id)
        .filter(
            User.role == UserRole.admin,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.id != exclude_id,
        )
        .with_for_update()
        .all()
    )
    return len(rows)


# An id no row has, for when the count should exclude nobody.
_NOBODY = uuid.UUID(int=0)

_LAST_ADMIN = (
    "that is the last active admin — doing this locks everyone out of the "
    "admin surface, including whoever asked, and there is no way back in "
    "from here. Promote another admin first."
)


# ------------------------------------------------------------ list


def _list_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    q = db.query(User).filter(
        User.deleted_at.is_(None),
        User.role.in_([UserRole.admin, UserRole.organizer]),
    )
    if args.get("include_inactive") is not True:
        q = q.filter(User.is_active.is_(True))
    if args.get("role"):
        wanted = str(args["role"]).strip().lower()
        if wanted not in _ASSIGNABLE:
            return {"error": f"role must be one of {', '.join(_ASSIGNABLE)}"}
        q = q.filter(User.role == UserRole(wanted))

    rows = [_row(u) for u in q.order_by(User.name).all()]
    return schema_apply(
        {"staff": rows, "count": len(rows)}, allowed_fields=_STAFF_SCHEMA
    )


LIST_STAFF_TOOL = Tool(
    name="list_staff",
    description=(
        "List the admins and organizers who can log in, with the user_id the "
        "other staff tools need. Inactive accounts are hidden by default. "
        "Volunteers are not staff and do not appear here — they have no "
        "accounts. Read-only."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": list(_ASSIGNABLE)},
            "include_inactive": {"type": "boolean"},
        },
    },
    allowed_roles=["admin"],
    requires_confirmation=False,
    pii_schema=_STAFF_SCHEMA,
    handler=_list_handler,
)


# ------------------------------------------------------------ invite


def _invite_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("email"):
        missing.append("the email address to send the invite to")
    if not args.get("name"):
        missing.append("their name, as it should appear in the admin list")
    if str(args.get("role") or "") not in _ASSIGNABLE:
        # Never defaulted. Organizer and admin are not near-neighbours —
        # one runs a classroom, the other can delete the quarter.
        missing.append(
            "whether they should be an organizer or an admin — an organizer "
            "runs events, an admin can change anything including quarters "
            "and other accounts"
        )
    return ask_for(missing)


def _invite_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    from app.services.invite import send_invite_email

    email = str(args["email"]).strip().lower()
    role = str(args.get("role") or "").strip().lower()
    if role not in _ASSIGNABLE:
        return {"error": f"role must be one of {', '.join(_ASSIGNABLE)}"}

    existing = (
        db.query(User).filter(User.email.ilike(email)).one_or_none()
    )
    if existing is not None:
        return {
            "error": (
                f"an account already exists for that address ({existing.name}, "
                f"{existing.role.value}). Change its role or reactivate it "
                "instead of inviting again."
            )
        }

    user = User(
        name=str(args["name"]).strip(),
        email=email,
        role=UserRole(role),
        # No password: the invite is a magic link, which is the whole
        # account-recovery story here.
        hashed_password=None,
        is_active=True,
        notify_email=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Best-effort, exactly like the router: an email failure must not undo
    # the account, or the admin is left with neither.
    sent = True
    try:
        send_invite_email(user, db)
    except Exception:
        sent = False

    row = _row(user)
    row["invited"] = True
    row["invite_email_sent"] = sent
    return schema_apply(row, allowed_fields=_STAFF_SCHEMA)


INVITE_STAFF_TOOL = Tool(
    name="invite_staff",
    description=(
        "Create a staff account and email them a magic-link invite. Needs an "
        "email, a name and a role — organizer or admin. Never pick the role: "
        "an organizer runs events, an admin can change quarters and other "
        "people's accounts. Volunteers do not need accounts and must not be "
        "invited here. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "name": {"type": "string"},
            "role": {"type": "string", "enum": list(_ASSIGNABLE)},
        },
        "required": ["email", "name", "role"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_STAFF_SCHEMA,
    handler=_invite_handler,
    precheck=_invite_precheck,
)


# ------------------------------------------------------------ role


def _role_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    missing: list[str] = []
    if not args.get("user_id"):
        missing.append("whose role to change — the user_id from list_staff")
    if str(args.get("role") or "") not in _ASSIGNABLE:
        user = _get(db, args.get("user_id"))
        missing.append(
            suggesting(
                "which role they should have — organizer or admin",
                user.role.value if user else None,
            )
        )
    return ask_for(missing)


def _role_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    user = _get(db, args.get("user_id"))
    if user is None:
        return {"error": "no staff account with that id"}

    role = str(args.get("role") or "").strip().lower()
    if role not in _ASSIGNABLE:
        return {"error": f"role must be one of {', '.join(_ASSIGNABLE)}"}
    if user.role.value == role:
        return {"error": f"{user.name} is already {role}"}

    was = user.role.value
    if user.role == UserRole.admin and user.is_active:
        remaining = _other_active_admins(db, user.id)
        if remaining < 1:
            db.rollback()
            return {"error": _LAST_ADMIN}

    user.role = UserRole(role)
    db.add(user)
    db.commit()
    db.refresh(user)

    row = _row(user)
    row["changed"] = True
    row["from_role"] = was
    row["to_role"] = role
    return schema_apply(row, allowed_fields=_STAFF_SCHEMA)


SET_STAFF_ROLE_TOOL = Tool(
    name="set_staff_role",
    description=(
        "Change a staff account between organizer and admin. Get the user_id "
        "from list_staff. Demoting the last active admin is refused outright "
        "— it would lock everyone out of the admin surface with no way back. "
        "Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "From list_staff."},
            "role": {"type": "string", "enum": list(_ASSIGNABLE)},
        },
        "required": ["user_id", "role"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_STAFF_SCHEMA,
    handler=_role_handler,
    precheck=_role_precheck,
)


# ------------------------------------------------------------ (de)activate


def _active_precheck(
    db: Session, scope: Scope, args: dict[str, Any]
) -> dict[str, Any] | None:
    if not args.get("user_id"):
        return ask_for(
            ["whose account to change — the user_id from list_staff"]
        )
    if args.get("active") is None:
        user = _get(db, args["user_id"])
        return ask_for(
            [
                suggesting(
                    "whether to deactivate or reactivate them — pass "
                    "active=false to switch the account off",
                    f"{user.name} is currently "
                    f"{'active' if user.is_active else 'inactive'}"
                    if user
                    else None,
                )
            ]
        )
    return None


def _active_handler(db: Session, scope: Scope, args: dict[str, Any]) -> dict[str, Any]:
    user = _get(db, args.get("user_id"))
    if user is None:
        return {"error": "no staff account with that id"}

    active = bool(args.get("active"))
    if bool(user.is_active) == active:
        state = "active" if active else "inactive"
        return {"error": f"{user.name} is already {state}"}

    if not active:
        caller_id = getattr(scope, "caller_id", None)
        if caller_id is not None and str(caller_id) == str(user.id):
            return {
                "error": (
                    "that is your own account — deactivating it would end "
                    "this session and lock you out"
                )
            }
        if user.role == UserRole.admin:
            if _other_active_admins(db, user.id) < 1:
                db.rollback()
                return {"error": _LAST_ADMIN}

    user.is_active = active
    db.add(user)
    db.commit()
    db.refresh(user)

    row = _row(user)
    row["changed"] = True
    # Reported on every switch so an admin can see how close they are to the
    # wall before they hit it, rather than only when the tool refuses.
    row["active_admins_remaining"] = _other_active_admins(db, _NOBODY)
    return schema_apply(row, allowed_fields=_STAFF_SCHEMA)


SET_STAFF_ACTIVE_TOOL = Tool(
    name="set_staff_active",
    description=(
        "Switch a staff account off (active=false) or back on. Deactivating "
        "is how somebody who has left loses access — it keeps their history, "
        "unlike deletion. Refused for your own account, and for the last "
        "active admin. Requires user confirmation."
    ),
    json_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "From list_staff."},
            "active": {
                "type": "boolean",
                "description": "false deactivates, true reactivates.",
            },
        },
        "required": ["user_id", "active"],
    },
    allowed_roles=["admin"],
    requires_confirmation=True,
    pii_schema=_STAFF_SCHEMA,
    handler=_active_handler,
    precheck=_active_precheck,
)
