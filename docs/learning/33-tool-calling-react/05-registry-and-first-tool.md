# Lecture 33-05: From Three Boundary Layers to a Working Tool Call

## Where we are

The last four lectures built isolated parts. 33-01 was the audit log
that records every tool call with its own commit. 33-02 was the schema
filter that drops disallowed columns. 33-03 was the role scope that
adds the SQL `WHERE` clause for non-admin callers. 33-04 was the
redactor that scrubs PII patterns out of free-text strings.

None of those four parts ever ran together. This sub-phase is the one
where they finally do — and the trick is that they are wired together
in a single function (`invoke`) and made callable through a single
data structure (`Tool`). Once that is in place, adding a new tool is a
matter of declaring one more `Tool` and registering it. No new
boundary code, no new audit code, no new redactor wiring.

## The `Tool` shape

Open `backend/app/copilot/agent/tools/base.py`. The first thing you
see is:

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    json_schema: dict[str, Any]
    allowed_roles: list[str]
    requires_confirmation: bool
    pii_schema: list[str]
    handler: Callable[[Any, Scope, dict[str, Any]], Any]
```

Read this as a *capability declaration*. Every field is something the
agent loop or the boundary needs to know before it lets the tool run:

- `name` is what the model emits. It is also the registry key.
- `description` and `json_schema` are the only things the model sees
  about the tool. Together they form the "API doc" handed to the LLM.
- `allowed_roles` is the role allow-list. The registry filters on
  this; the model never sees tools that aren't allowed for the caller.
- `requires_confirmation` flags writes. Reads are `False`, writes
  (e.g. "schedule this module") are `True`.
- `pii_schema` is the layer-1 allow-list — the columns this tool is
  *allowed* to emit. Anything else gets dropped by `schema_apply`.
- `handler` is the actual function that hits the DB.

The dataclass is `frozen=True`. Once a `Tool` is built, you cannot
swap its `pii_schema` or its `allowed_roles`. The contract is static
by construction. This matters: a runtime-mutable schema would mean
the boundary's allow-list could be changed *after* registration, and
the whole point of declarative tools is that you can read the file
and know what they will do.

## The registry — boring on purpose

`backend/app/copilot/agent/tools/registry.py` is twenty-two lines:

```python
_REGISTRY: dict[str, Tool] = {}

def register(tool): ...
def get_tool(name): ...
def get_tools_for_role(role): ...
def _reset_for_tests(): ...
```

That is it. There is no namespacing, no plugin discovery, no fancy
decorator. A module-global dict, three readers, one test helper.

Why so plain? Because the registry is *read* on every agent turn but
*written* only at import time. When a new turn starts, the agent loop
calls `get_tools_for_role(role)` to get the list of tools to advertise
to the model. That call has to be cheap, deterministic, and impossible
to race. A plain dict comprehension wins on all three axes.

`_reset_for_tests()` is the one feature that exists purely for the
test layer. Because the registry is module-global, two tests that both
register a `Tool` named `"t1"` would collide unless one of them tore
the registry down. So `conftest.py` runs:

```python
@pytest.fixture(autouse=True)
def _reset_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()
```

Every agent test starts and ends with an empty registry. No
cross-contamination.

## Registration at import time

The `__init__.py` of the tools package looks like this:

```python
from . import registry
from .list_modules import LIST_MODULES_TOOL
registry.register(LIST_MODULES_TOOL)
```

That is the entire registration surface. Importing
`app.copilot.agent.tools` is sufficient to populate the registry.
There is no "call this once on startup" handshake. If you forget to
add the import line for a new tool, the tool is *not* registered —
which is loud and obvious, not silently wrong.

## The first tool: `list_modules`

Now look at `list_modules.py`. It is a read tool that answers
"what modules are scheduled for ISO week 2026-W22?". The handler:

```python
def _handler(db, scope, args):
    year, week_number = _parse_iso_week(args["week"])
    q = db.query(Event).filter(
        Event.year == year,
        Event.week_number == week_number,
    )
    if args.get("school"):
        q = q.filter(Event.school == args["school"])
    if not scope.see_all:
        q = q.filter(Event.owner_id == scope.module_owner_id)
    rows = [...]
    filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
    return {"modules": filtered}
```

Three things to notice.

**First**, the ISO week parsing is a regex, not `datetime.fromisocalendar`.
The agent receives the week as a string the LLM produced; we want to
reject malformed input loudly with a `ValueError` rather than feed
bad data into the database driver.

**Second**, the role-scope clause is conditional:

```python
if not scope.see_all:
    q = q.filter(Event.owner_id == scope.module_owner_id)
```

Admins get no `WHERE owner_id = ...` clause. Organizers do, and the
value comes from the scope object — *not* from anything the LLM said.
The LLM cannot ask "show me organizer B's modules"; the scope was
pinned at the start of the agent turn from the authenticated session.

**Third**, every row in the result includes `owner_id`, and the
schema filter strips it:

```python
_PII_SCHEMA = ["id", "name", "week", "school"]
filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
```

That is layer 1 in action. The handler *needs* `owner_id` (so layer 2
has something to filter on), but `owner_id` is staff PII and must not
cross back to the LLM. The schema filter is what makes the line not
appear in the model-visible output.

## A name-vs-model mismatch worth knowing

The data model calls them `Event`. The agent surface calls them
`module`. Why?

Because the v1.0 SQLAlchemy model chose `Event` early, before the
product vocabulary settled around "module" (the term educators
actually use for a SciTrek classroom visit). Renaming the model would
mean a migration, an Alembic step, and changes across every existing
admin and participant page. Not worth the churn.

But the tool's *name* — what the LLM sees — is `list_modules`. The
domain-facing word wins at the agent boundary because that is the
word the model will hear from the user. Inside, the handler still
queries `Event`. The translation happens once, at the tool boundary,
and the model never has to learn the legacy noun.

## The `invoke()` wrapper

Now the punchline. Every tool call goes through this:

```python
def invoke(db, *, tool, scope, args, session_id):
    call_id = write_call(db, ..., requires_confirmation=tool.requires_confirmation)
    if tool.requires_confirmation:
        return {"call_id": call_id, "status": "pending_confirmation"}
    raw = tool.handler(db, scope, args)
    scrubbed, events = scrub(raw, declared=True)
    update_status(db, call_id, status="executed",
                  result=scrubbed, redactions=len(events))
    return {"call_id": call_id, "result": scrubbed,
            "redactions": len(events)}
```

The sequence is:

1. Write a `pending` audit row (its own commit).
2. If the tool is a *write*, stop here — return `pending_confirmation`
   and let a separate confirm path actually run the handler.
3. Otherwise run the handler.
4. Run the redactor with `declared=True`.
5. Update the audit row to `executed` with the redaction count.
6. Return the scrubbed result.

That is the *only* dispatch path. There is no shortcut, no "internal
call" that skips the audit. The boundary is unavoidable because it
lives inside the only function any caller can use.

## Why `declared=True`?

The `Tool` has a `pii_schema`. By declaring it, the tool is asserting:
"my output may contain PII in these fields, please scrub them." The
redactor honors that declaration by treating any hit as `LOW`
severity — expected, logged, not an alarm.

If we passed `declared=False`, every redaction would be `HIGH`, and
the audit log would fill up with false alarms every time a real
note happened to contain a phone number. The declaration is what
lets the alarm bell stay loud for *actual* boundary bugs.

## Why no transaction around `invoke()`

The audit log writes commit on their own. That is by design — see
33-01. If `invoke()` wrapped the whole call in a transaction, a
handler crash would roll back the audit row too, and we would lose
the very record we built the audit log to preserve.

So `invoke()` does not own a transaction. It calls `write_call()`
(commits), runs the handler (uses whatever session was passed in),
runs the redactor (no DB), and calls `update_status()` (commits). If
anything between the two commits crashes, you are left with a
`pending` audit row and no execution — which is exactly the trace
you want for diagnosing the crash.

## Check-in question

A new tool — `cancel_module` — needs to be added. It is a *write*,
so `requires_confirmation=True`. Walk through what `invoke()` will
do on the first call (the user's "cancel module X" turn) and on the
second call (the confirmation turn that actually runs the handler).
Where does the audit row live, and what does the redactor see, in
each of those two turns?

(Answer in the next session.)
