"""Boundary layer 2: role-scoped query helper.

Produces an immutable Scope object that each tool uses to add WHERE clauses
to its DB queries. Admins are unrestricted (see_all=True); organizers are
scoped to rows where module.owner_id matches their user id. Unknown roles
raise ScopeError. Caller_id must be present for organizer scope."""

from __future__ import annotations

from dataclasses import dataclass


class ScopeError(Exception):
    pass


@dataclass(frozen=True)
class Scope:
    role: str
    caller_id: int | None
    module_owner_id: int | None  # None means "no filter" (admin)
    see_all: bool


def scope_for(*, role: str, caller_id) -> Scope:
    if role == "admin":
        return Scope(
            role=role,
            caller_id=caller_id,
            module_owner_id=None,
            see_all=True,
        )
    if role == "organizer":
        if caller_id is None:
            raise ScopeError("organizer requires caller_id")
        return Scope(
            role=role,
            caller_id=caller_id,
            module_owner_id=caller_id,
            see_all=False,
        )
    raise ScopeError(f"role {role!r} not allowed in agent")


_OUT_OF_SCOPE = "that event is not one of yours"


def owns_event(scope: Scope, event) -> bool:
    """Whether ``scope`` may act on ``event``.

    Admins see everything; an organizer is confined to events they own.
    """
    if scope.see_all:
        return True
    return getattr(event, "owner_id", None) == scope.module_owner_id


def deny_if_not_owned(scope: Scope, event) -> dict | None:
    """The error payload a tool handler returns, or None when allowed.

    The read tools each grew their own copy of this check
    (``get_module_roster.py:51`` is the canonical one) while every *write*
    handler in ``events_edit.py`` and ``operations.py`` had none at all — so
    an organizer who knew an event id could rename, reschedule or move
    people inside another organizer's event. One helper, called from every
    handler that resolves an event, so the next write tool inherits the
    boundary instead of having to remember it.
    """
    if owns_event(scope, event):
        return None
    return {"error": _OUT_OF_SCOPE}
