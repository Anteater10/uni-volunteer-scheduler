"""Boundary layer 2: role-scoped query helper.

Produces an immutable Scope object that each tool uses to add WHERE clauses
to its DB queries. Both staff roles are unrestricted (see_all=True) — the
boundary that matters is the set of admin-only routes, not a per-event owner
check (L4 #36; deps.ensure_event_staff_access is the same rule for the REST
API). Unknown roles raise ScopeError. Caller_id must still be present for an
organizer: it records who acted.

With no role owner-scoped, the read tools' own ``if not scope.see_all``
filters could never run and were removed. The one seam kept is
``deny_if_not_owned`` below, which every *write* handler still calls: a future
per-event rule belongs there, and the read tools would need their filters
back alongside it."""

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
        # L4 #36: organizers used to be confined here to events whose
        # owner_id was their own user id. The REST API stopped working that
        # way — see deps.ensure_event_staff_access, which grants any staff
        # role any event, because the staff event list is global and nothing
        # in the product can transfer ownership, so owner-scoping only ever
        # meant "events you personally created". The copilot kept the old
        # rule, so the same organizer got different answers depending on
        # whether they asked the app or asked the assistant.
        #
        # caller_id stays on the Scope: it is who acted, which the write
        # tools record, and is not the same question as what they may touch.
        return Scope(
            role=role,
            caller_id=caller_id,
            module_owner_id=None,
            see_all=True,
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
