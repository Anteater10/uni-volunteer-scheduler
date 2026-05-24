# Lecture 33-03: Role Scope — Filtering Rows Before the Agent Ever Sees Them

## Opening scenario

An organizer named Priya signs in and asks the copilot: *"Show me the
participants registered for any of my events next week."* Behind the
scenes, the agent decides to call `list_events`. The tool runs a
SQLAlchemy query against the `events` table. The query returns rows.

Question: what stops that query from returning **every** event in the
database — including the events Priya does not own?

If the answer is "the tool author remembered to add a `WHERE`
clause," you are one forgotten line of code away from a PII leak. We
need something better. That something is the **role-scope helper**,
boundary layer 2.

## What problem we are actually solving

In the previous lecture we covered layer 1, the schema filter. Schema
filter answers: *given a row, which columns is the agent allowed to
see?* It drops `email`, `phone`, internal notes, and so on.

But schema filter has nothing to say about *which rows* the query
returns in the first place. If a tool blindly does
`SELECT * FROM events`, schema filter will dutifully strip the columns
it doesn't like — and then hand the agent every event in the system,
including events belonging to other organizers. The PII fields are
gone, but the *existence* and *titles* of those other events are
still a leak.

Layer 2 fixes that. It makes sure that before any query runs, the tool
knows exactly which rows it is allowed to look at.

## The Scope object

The helper produces a small, immutable dataclass:

```python
@dataclass(frozen=True)
class Scope:
    role: str
    caller_id: int | None
    module_owner_id: int | None
    see_all: bool
```

Four fields. Each one carries a specific piece of information that a
tool needs to build a safe query:

- `role` — who you are. Mostly informational, used for logging.
- `caller_id` — your user id, in case the tool needs to write an
  `updated_by` field or similar.
- `module_owner_id` — the value to filter `owner_id` on. `None` if no
  filter is needed.
- `see_all` — a boolean shortcut. `True` means "don't bother filtering."

`frozen=True` is important. A tool cannot accidentally mutate the scope
mid-query — there is no `scope.see_all = True` escape hatch.

## The two real cases

The agent surface only serves two roles. Let's walk through both.

### Admin: `see_all = True`

Admins are unrestricted. They triage incidents, reassign events between
organizers, and audit the platform. The scope they get is essentially
"no filter":

```python
Scope(role="admin", caller_id=42, module_owner_id=None, see_all=True)
```

A tool checks `see_all` and skips the owner filter:

```python
if not scope.see_all:
    q = q.filter(Event.owner_id == scope.module_owner_id)
```

For admins, that `if` is false, so no filter gets added. They see
everything. Tests confirm this: `test_admin_scope_sees_all_events`
seeds three events across two organizers and verifies an admin scope
returns all three.

### Organizer: `module_owner_id = caller_id`

Organizers can see only the events they own. The helper expresses this
by copying the caller's own id into `module_owner_id`:

```python
Scope(role="organizer", caller_id=47, module_owner_id=47, see_all=False)
```

The tool then filters on `Event.owner_id == 47`. Tests verify this:
`test_scope_applies_owner_filter_to_event_query` seeds two events owned
by organizer A and one owned by organizer B, scopes as A, and confirms
exactly the two A-events come back.

## Why we do not just compute this inside each tool

Every read tool would otherwise need a copy of the same three lines:

```python
if role == "organizer":
    q = q.filter(Event.owner_id == caller_id)
elif role == "admin":
    pass
else:
    raise SomeError(...)
```

That is a recipe for drift. One tool forgets the `elif admin`; one
tool spells the role string wrong; one tool inverts the check during a
refactor. Centralizing the decision into `scope_for` means there is
exactly one place in the codebase where the role-to-filter mapping
lives. Tools become consumers of that decision, not co-authors of it.

## The deny-by-default pattern

Here is the whole factory:

```python
def scope_for(*, role: str, caller_id) -> Scope:
    if role == "admin":
        return Scope(role, caller_id, None, see_all=True)
    if role == "organizer":
        if caller_id is None:
            raise ScopeError("organizer requires caller_id")
        return Scope(role, caller_id, caller_id, see_all=False)
    raise ScopeError(f"role {role!r} not allowed in agent")
```

Notice what is *not* there: a final `else: return Scope(..., see_all=False)`
fallback. There is no "default safe scope." Two specific roles are
handled; everything else raises.

Why? Because a default "safe" scope is a lie. Consider the options:

1. **Default to "see nothing."** That looks safe, but it presents to
   the user as a totally broken product. The agent says "I couldn't
   find any events" when the real answer is "you reached a code path
   the helper doesn't understand."
2. **Default to "see everything."** Obviously a leak.
3. **Default to "filter on caller_id anyway."** Quietly correct for
   organizers and quietly wrong for any future role.

The honest choice is to raise. A `ScopeError` propagates up the agent
loop, fails the request, and shows up in the audit log as a session
error. That gets fixed. A silent leak does not.

This is the same philosophy as schema filter: deny rather than degrade.

## The missing-`caller_id` case

Organizer scope requires a `caller_id`. If somehow the caller id is
missing (a bug in session bootstrapping, a misconfigured test, a
malformed token), the helper raises:

```python
if caller_id is None:
    raise ScopeError("organizer requires caller_id")
```

We could have invented a "filter on `NULL`" fallback. That would have
produced zero rows for every query, which looks like data loss in the
UI. Or we could have skipped the filter entirely, which is the worst
possible behavior. Raising is the only choice that produces a clear
signal at the moment the bug exists.

## How a tool actually uses a Scope

The canonical pattern is short and mechanical:

```python
def list_events(scope: Scope, limit: int = 50) -> list[dict]:
    q = db_session.query(Event)
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)
    return [row.as_dict() for row in q.limit(limit)]
```

Two things to notice. First, the tool does not read `scope.role`. The
role string is for logging, not for access decisions — those are baked
into the booleans. Second, the filter expression is the same shape
every time: `Model.owner_id == scope.module_owner_id`. New tools copy
the pattern. Code review checks that the pattern is present.

## "Wait, the spec says 'Module' but the code says 'Event'"

You may notice the docstring talks about `module_owner_id` and the
tests query `Event`. That is not a bug — it is a vocabulary mismatch.

The product domain has a concept called a *module* (a SciTrek learning
module, taught in some classroom on some day). In the database, the
concrete row that represents "a scheduled module at a school on a
date" is an `Event`. The owner of that `Event` is the organizer who
created it.

So when the helper says `module_owner_id`, it means "the owner field
on whatever DB model stands in for the module concept." Right now that
is `Event.owner_id`. If that model is ever renamed, the field name on
`Scope` should be renamed with it.

## How this layer composes with the other two

Recall the stack:

1. **Layer 1 — schema filter.** Drops columns the agent is not allowed
   to see.
2. **Layer 2 — role scope (this one).** Drops rows the agent is not
   allowed to see.
3. **Layer 3 — redactor.** Catches PII content inside free-text fields
   that survived the first two layers.

The crucial property is **independence**. A row that passes layer 2
still gets its columns filtered by layer 1. A column that survives
layer 1 still gets its contents scrubbed by layer 3. Any single layer
failing — a schema with a missing whitelist entry, a tool that forgets
the `if not scope.see_all` check, a regex that misses a phone-number
format — still leaves two layers standing.

If we had built one big function that "did everything," a single bug
would defeat all of PII protection at once. Three separate, dumb,
boring layers is harder to defeat than one clever layer.

## Check-in question

A new developer asks: "I'm writing a tool that lists all participants
across all events. Can I just call `scope_for(role='admin',
caller_id=None)` from inside the tool to get an unrestricted scope?"

What is the right answer, and why? (Answer in the next session.)
