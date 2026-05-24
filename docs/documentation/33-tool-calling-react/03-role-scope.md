# Sub-phase 33-03: Role Scope (PII Defense Layer 2)

## Purpose

The **role scope** helper is the second of three boundary layers that
keep tool calls honest about *which rows* they are allowed to return.
Where layer 1 (schema filter) governs **columns**, layer 2 governs
**rows**. It produces a small immutable `Scope` object that every tool
consults before constructing its `WHERE` clause.

This document specifies the contract of the role-scope helper, the
decisions it encodes, and the failure modes it intentionally raises on
rather than swallowing.

## Where it sits in the defense stack

PII defense is layered. Each layer is independent and redundant:

| Layer | Mechanism                       | Scope                  | Failure mode if bypassed                          |
| ----- | ------------------------------- | ---------------------- | ------------------------------------------------- |
| 1     | Schema filter                   | Per-tool whitelist     | A new DB column would appear in tool output       |
| 2     | **Role scope** (this doc)       | SQL `WHERE` clause     | A tool would return rows the role cannot see      |
| 3     | Redactor                        | Regex / classifier     | Free-form text would leak emails, phones, etc.    |

Layer 1 prevents whole-column leakage. Layer 2 prevents whole-row
leakage. Layer 3 catches free-text content that the first two layers
have no opinion about. The three are independent so that a misconfigured
schema or a buggy regex cannot, on its own, produce a PII leak.

## The `Scope` dataclass

```python
@dataclass(frozen=True)
class Scope:
    role: str
    caller_id: int | None
    module_owner_id: int | None  # None means "no filter" (admin)
    see_all: bool
```

Field-by-field:

- `role` — the caller's role at scope time, captured for downstream
  audit and logging. Mirrors the `role` column on `copilot_tool_calls`.
- `caller_id` — the user id of the requester. Carried through so tools
  that need to attribute writes (e.g. "set `updated_by`") have the
  identifier without re-deriving it.
- `module_owner_id` — the owner id that organizer-scoped queries must
  filter on. `None` for admins.
- `see_all` — explicit boolean for admin scope. Tools branch on this
  rather than on `module_owner_id is None` so that intent is obvious at
  the call site.

The dataclass is `frozen=True` so tool code cannot mutate the scope
mid-query.

## The factory: `scope_for(role, caller_id)`

```python
def scope_for(*, role: str, caller_id) -> Scope: ...
```

Keyword-only arguments are deliberate — there is no positional form. A
call like `scope_for("organizer", None)` would parse as a positional
argument and silently produce a broken scope; forcing keywords makes
the call site read like a sentence.

The decision table:

| `role`        | `caller_id` | Result                                  |
| ------------- | ----------- | --------------------------------------- |
| `"admin"`     | anything    | `Scope(see_all=True, module_owner_id=None)` |
| `"organizer"` | non-`None`  | `Scope(see_all=False, module_owner_id=caller_id)` |
| `"organizer"` | `None`      | raises `ScopeError`                     |
| anything else | anything    | raises `ScopeError`                     |

There is no fallthrough "default" branch. The factory either returns a
valid `Scope` or raises. This is the **deny-by-default** posture: a
permissive scope is never produced by accident.

## Why admins get `see_all=True`

Admin is the only role that legitimately operates across module
boundaries — they triage, reassign, and audit. Encoding their scope as
"no filter" rather than "filter on every owner_id" keeps the SQL clean
and avoids accidentally constraining admin queries when a new
organizer is added.

Tools translate `see_all=True` into "skip the owner filter entirely":

```python
q = db_session.query(Event).filter(Event.id.in_(event_ids))
if not s.see_all:
    q = q.filter(Event.owner_id == s.module_owner_id)
```

That `if not s.see_all` is the canonical pattern. The condition is on a
named boolean, not on `module_owner_id is None`, so the reader does not
have to remember which `None` means what.

## Why organizers get `module_owner_id = caller_id`

The product invariant is: *an organizer can see the data attached to the
modules they own, and nothing else*. In the schema, ownership lives on
`Event.owner_id` (a UUID foreign key to the `users` table). The helper
encodes that invariant by copying `caller_id` into `module_owner_id`.
The tool does not have to know about the join shape; it just adds a
single equality on `owner_id`.

If the ownership model ever changes — e.g. organizers gain access to a
team's events instead of only their own — the change lives in one
place (`scope_for`) rather than in every tool's query.

## The Event-model reality

The phase plan refers to "modules" generically because that is the
domain concept the paper uses. The actual ORM model is `Event`
(`app/models/event.py`), with `owner_id: UUID` pointing at the
organizer who created it. Tests in `tests/copilot/agent/conftest.py`
seed three `Event` rows across two organizers, and the scope tests
verify that an organizer-scoped query returns exactly the two rows
owned by that organizer.

The mismatch between "module" (planning vocabulary) and "Event"
(codebase reality) is worth flagging in code review whenever the docs
talk about the boundary helper. The contract is the same either way;
only the table name differs.

## Deny-by-default for unknown roles

```python
raise ScopeError(f"role {role!r} not allowed in agent")
```

Three roles exist in the product: `participant`, `organizer`, `admin`.
The agent surface only serves `organizer` and `admin`. A participant
should never reach `scope_for` because participant requests do not run
through the tool-call path. If one ever does — because of a routing
bug, a misconfigured session, or a future feature — `scope_for` raises
rather than producing a permissive scope.

The same goes for any string that isn't one of the two allowed values.
A typo (`"orgnaizer"`) raises. A new role added to the system without
updating the helper raises. There is no implicit fallback to "treat as
the most restrictive role" because being silently restrictive on a
write tool would corrupt data just as badly as being silently
permissive on a read tool.

## How tools consume a `Scope`

A tool handler accepts the `Scope` as an injected argument:

```python
def list_events(scope: Scope, *, limit: int = 50) -> list[dict]:
    q = db_session.query(Event)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)
    return [row.as_dict() for row in q.limit(limit)]
```

The translation is mechanical: `see_all` decides whether to add the
filter; `module_owner_id` is the value. A tool does **not** read
`scope.role` to make access decisions — role is informational. The
filter decision lives in the boolean and the owner id.

## Failure modes (by design)

**Missing `caller_id` for organizer.** Raises `ScopeError`. The agent
loop must surface this as a session error, not silently degrade. An
organizer scope without a caller id would have to either filter on
`NULL` (returning nothing, which looks like data loss) or skip the
filter (returning everything, which is the leak we are trying to
prevent). Raising is the only honest option.

**Unknown role.** Raises `ScopeError`. See the deny-by-default
discussion above.

**Tool forgets to apply the filter.** The helper cannot prevent this.
Tools are expected to use the canonical `if not scope.see_all:` block.
Code review and the tool-registration test suite are the backstop.

## Independence from other layers

Layer 2 does not know about layer 1 or layer 3. A row that passes the
role-scope filter is still subject to schema filtering on the way out
and to redaction of any free-text content. Likewise, layer 1 cannot
substitute for layer 2: dropping the `owner_id` column from the
output does nothing to stop the *row* from being returned in the first
place.

The three layers compose by sitting on top of each other, not by
trusting each other. That is the whole point of defense in depth.
