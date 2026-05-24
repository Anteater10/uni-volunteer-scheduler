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
