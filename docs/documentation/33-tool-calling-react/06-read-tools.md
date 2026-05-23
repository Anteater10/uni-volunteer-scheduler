# Sub-phase 33-06: Seven Read Tools on the `invoke()` Boundary

## Purpose

Sub-phase 33-05 stood up the dispatch surface: a `Tool` dataclass, a
module-global registry, the first concrete tool (`list_modules`), and
the single chokepoint — `invoke()` — that every tool call has to go
through. 33-06 builds on that foundation by adding seven more
**read-only** tools without touching the boundary stack:

| Tool                          | What it answers                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------- |
| `get_module_roster`           | Who is signed up for module X?                                                  |
| `find_understaffed_modules`   | Which modules are below fill-rate threshold T?                                  |
| `participant_history`         | Which modules has volunteer X attended?                                         |
| `signup_stats_for_week`       | Aggregate signups + fill rate for ISO week W.                                   |
| `signup_trend`                | Per-week signups + fill rate for the last N weeks.                              |
| `find_module_by_name`         | Fuzzy search modules by title.                                                  |
| `current_user_context`        | Who is the caller? (role, id, display name)                                     |

These seven cover the read surface the ReAct loop needs to answer
every common organizer/admin question. They share one template, one
PII discipline, and one dispatch path. No new boundary code is added —
that is the whole point.

## Shared template

Every tool in this sub-phase follows the same structure that
`list_modules` set in 33-05:

```python
_PII_SCHEMA = [...]  # allow-list of LLM-visible fields

def _handler(db, scope, args):
    # 1. Parse args (ISO week, UUID, threshold, ...).
    # 2. Build a SQLAlchemy query.
    # 3. Apply the role-scope WHERE clause when not scope.see_all.
    # 4. Build a Python dict / list of dicts that includes everything
    #    the role-scope WHERE clause needed (e.g. owner_id) PLUS what
    #    the LLM is allowed to see.
    # 5. schema_apply(payload, allowed_fields=_PII_SCHEMA)
    # 6. Return the filtered payload.

TOOL = Tool(
    name=...,
    description=...,
    json_schema=...,
    allowed_roles=["admin", "organizer"],
    requires_confirmation=False,
    pii_schema=_PII_SCHEMA,
    handler=_handler,
)
```

The handler always emits more than the PII schema allows. That is
intentional: layer 2 (role scope) needs `owner_id` to filter, the
redactor needs string fields to scrub, and layer 1 (schema filter) is
the *only* thing that decides what crosses back to the LLM. Putting
the filter at the end of the handler — not in the SELECT list — keeps
the security boundary in exactly one place.

## Role-scope-as-not-found pattern

`get_module_roster` and `participant_history` both take an entity id
and look it up. Two failure modes exist:

1. The entity does not exist at all.
2. The entity exists but the caller's organizer scope does not own
   it (or, for participant history, the participant has no signups on
   any of the caller's events).

Both collapse to the same sentinel:

```python
{"error": "module not found or not accessible"}
```

The LLM cannot tell case 1 from case 2. That is deliberate: if an
organizer probes `get_module_roster("00000000-...")` for many ids,
distinguishing "owned by someone else" from "does not exist" leaks the
existence of other organizers' modules through timing/responses. The
not-found sentinel removes the side channel. Tests cover the
cross-scope path explicitly so the regression is pinned.

## PII schemas — what is in vs out

The PII schemas for the seven tools, exactly as they appear in code:

| Tool                          | `_PII_SCHEMA`                                                                                  |
| ----------------------------- | ---------------------------------------------------------------------------------------------- |
| `get_module_roster`           | `module_id`, `module_name`, `participants.id`, `participants.name`, `participants.signup_status` |
| `find_understaffed_modules`   | `id`, `name`, `school`, `week`, `slots_filled`, `slots_total`, `slot_gap`                       |
| `participant_history`         | `participant_id`, `name`, `school`, `modules_attended`                                         |
| `signup_stats_for_week`       | `week`, `total_signups`, `unique_participants`, `modules_count`, `fill_rate`                   |
| `signup_trend`                | `weeks.week`, `weeks.total_signups`, `weeks.fill_rate`                                         |
| `find_module_by_name`         | `id`, `name`, `school`, `week`, `owner_name`                                                   |
| `current_user_context`        | `role`, `caller_id`, `display_name`                                                            |

The most important "out" cases:

- **No emails or phones.** Roster and participant tools never expose
  `Volunteer.email` or `Volunteer.phone_e164`. The handler reads them
  for completeness; `schema_apply` drops them.
- **No `owner_id`.** Every module-shaped tool emits `owner_id` so the
  role-scope WHERE clause has something to filter on, but the schema
  filter strips it on the way out. `find_module_by_name` keeps the
  human-readable `owner_name` (`User.name`) instead — that is safe to
  display because it is already on the public organizer page.

## Composing with `invoke()`

Each tool is wired into the registry at import time exactly the way
`list_modules` was:

```python
# tools/__init__.py
from .get_module_roster import GET_MODULE_ROSTER_TOOL
from .find_understaffed_modules import FIND_UNDERSTAFFED_MODULES_TOOL
# ... etc
registry.register(GET_MODULE_ROSTER_TOOL)
registry.register(FIND_UNDERSTAFFED_MODULES_TOOL)
# ... etc
```

Tests dispatch through `invoke()` rather than calling the handler
directly:

```python
out = invoke(
    db_session,
    tool=GET_MODULE_ROSTER_TOOL,
    scope=scope_for(role="organizer", caller_id=uuid_a),
    args={"module_id": str(event_id)},
    session_id=session_id,
)
```

That matters because `invoke()` is the only place that touches the
audit log and the redactor. Calling `handler()` directly would bypass
both. The end-to-end test for each tool therefore runs through
`invoke()`, asserts the result shape, and (where relevant) checks
that `out["redactions"] == 0` — the schema filter caught everything
sensitive before the redactor had to.

## Plan-vs-reality adaptations

A few tools needed small adaptations because the codebase has `Event`
where the plan said `Module` and `Volunteer` where the plan said
`Participant`:

- `participant_history` derives `school` from the participant's most-
  recent event because `Volunteer` has no `school` column.
- `find_understaffed_modules` defines fill rate against
  `Slot.capacity` summed across the event; events with no slots have
  `fill_rate = 0.0` and are always understaffed.
- `signup_stats_for_week` and `signup_trend` ignore signups whose
  status is `SignupStatus.cancelled` — only "live" signups count
  toward the totals.

Each tool file carries a one-line comment at the top noting the
mapping so a reader does not have to consult the plan.

## Files

- `backend/app/copilot/agent/tools/_iso_week.py` — shared ISO-week parser.
- `backend/app/copilot/agent/tools/get_module_roster.py`
- `backend/app/copilot/agent/tools/find_understaffed_modules.py`
- `backend/app/copilot/agent/tools/participant_history.py`
- `backend/app/copilot/agent/tools/signup_stats_for_week.py`
- `backend/app/copilot/agent/tools/signup_trend.py`
- `backend/app/copilot/agent/tools/find_module_by_name.py`
- `backend/app/copilot/agent/tools/current_user_context.py`
- Matching test file for each tool under `backend/tests/copilot/agent/`.
