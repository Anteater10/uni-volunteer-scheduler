# Sub-phase 33-05: Tool Registry + First Tool (`list_modules`) + Uniform `invoke()`

## Purpose

Sub-phases 33-01 through 33-04 built the boundary stack (audit log,
schema filter, role scope, redactor) in isolation. This sub-phase wires
those pieces into a **tool dispatch surface**: a tiny, frozen contract
for what a tool *is*, a module-global **registry** that the agent loop
can ask "which tools is this role allowed to call?", a first concrete
tool (`list_modules`), and the single function — `invoke()` — that
every tool call has to go through.

The point is to make the boundary unavoidable. There is exactly one
chokepoint that touches audit log + redactor; no tool can be called by
any path other than `invoke()`, and the registry is the only way the
agent loop sees a tool at all.

## The `Tool` dataclass — the contract

`backend/app/copilot/agent/tools/base.py` defines:

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

Seven fields, each load-bearing:

| Field                   | Role                                                                          |
| ----------------------- | ----------------------------------------------------------------------------- |
| `name`                  | Stable string the LLM emits in its tool call; also the registry key.          |
| `description`           | Natural-language tool description handed to the LLM in the system prompt.     |
| `json_schema`           | JSON-Schema for the tool's arguments — the LLM's contract for `args`.         |
| `allowed_roles`         | Role allow-list. `get_tools_for_role(role)` filters on this.                  |
| `requires_confirmation` | If true, the tool is a *write*: `invoke()` returns `pending_confirmation`.    |
| `pii_schema`            | Allow-list of output fields the tool legitimately exposes (drives layer 1).   |
| `handler`               | The actual callable `(db, scope, args) -> raw_payload`.                       |

The class is `frozen=True` deliberately. A `Tool` is a static
declaration of capability — not state. Once registered, the schema,
role list, and PII shape must not drift at runtime. Freezing the
dataclass turns "do not mutate" from a convention into a `TypeError`.

## The registry — module-global, role-filtered

`backend/app/copilot/agent/tools/registry.py` is forty lines including
blanks:

```python
_REGISTRY: dict[str, Tool] = {}

def register(tool: Tool) -> None: ...
def get_tool(name: str) -> Tool: ...
def get_tools_for_role(role: str) -> list[Tool]: ...
def _reset_for_tests() -> None: ...
```

`get_tools_for_role(role)` is the function the agent loop will call on
every turn to build the LLM-visible tool list. The filter is just
`role in t.allowed_roles` — there is no inheritance, no wildcard, no
"admin sees everything by default." If `admin` should see a tool,
`"admin"` has to be in `allowed_roles`. Explicit beats clever.

Registration happens at **module import time**:

```python
# app/copilot/agent/tools/__init__.py
from . import registry
from .list_modules import LIST_MODULES_TOOL

registry.register(LIST_MODULES_TOOL)
```

Importing the package is enough to populate the registry. There is no
"register all tools" call to forget on a new code path.

`_reset_for_tests()` exists because the registry is module-global. The
`conftest.py` autouse fixture wraps every agent test in a
`reset_for_tests() → yield → reset_for_tests()` sandwich so tests
cannot leak `Tool` instances into each other. Hermeticity is enforced
by the fixture, not by test discipline.

## The first tool: `list_modules`

`list_modules` reads scheduled modules for a given ISO week. It is the
canonical *read* tool — the simplest possible thing that still
exercises the boundary stack end-to-end.

ISO-week-string parsing is done by a tight regex:

```python
_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")
```

The handler accepts `args["week"]` (e.g. `"2026-W22"`), parses it into
`(year, week_number)`, and filters `Event.year` and `Event.week_number`
on the resulting integers. An optional `args["school"]` adds a second
filter clause.

The role-scope conditional is the security-critical line:

```python
if not scope.see_all:
    q = q.filter(Event.owner_id == scope.module_owner_id)
```

When the caller is an admin, `scope.see_all` is true and no
owner-based clause is added; admins see every module. When the caller
is an organizer, `see_all` is false and the query is restricted to
modules whose `owner_id` matches `scope.module_owner_id` — which the
boundary's `scope_for()` factory has already pinned to the caller's
own UUID. The tool itself cannot accidentally hand an organizer
somebody else's data; the layer-2 clause makes it impossible at the
SQL level.

Layer 1 then runs:

```python
filtered = schema_apply(rows, allowed_fields=_PII_SCHEMA)
```

`_PII_SCHEMA = ["id", "name", "week", "school"]`. Note that the
handler emits `owner_id` in every row — and the schema filter strips
it before returning. That is intentional: the tool needs `owner_id`
for layer 2 to even have something to filter on, but `owner_id` is
PII (it identifies the staff member behind the module) and must not
cross the boundary back to the LLM. The schema filter is what enforces
that, and the tool's unit test `test_returns_only_allowed_fields` pins
the invariant.

## Plan-vs-reality: `Event`/`Module` naming

The agent surface calls the concept "module" — that is the name
educators use day-to-day for a SciTrek classroom visit. The database
calls it `Event` because the v1.0 schema chose the more generic noun
before the product vocabulary settled. We did not rename the model
(too much churn for too little gain) but we did keep the **tool name
as `list_modules`**. The LLM sees the domain-facing name. The handler
internally queries `Event`. The two are aligned at the tool boundary,
which is the only place the language model ever looks.

## The uniform `invoke()` wrapper

`invoke()` is the only chokepoint that touches the audit log and the
redactor. Every tool call goes through it. The flow is:

```
write audit row (pending)
  └─ if requires_confirmation: return {call_id, status: "pending_confirmation"}
  └─ else:
       raw      = tool.handler(db, scope, args)
       scrubbed = scrub(raw, declared=True)
       update audit row (status=executed, redactions=len(events))
       return {call_id, result: scrubbed, redactions}
```

Three properties to call out:

1. **Audit before handler.** The pending row is written *before* the
   handler runs. If the handler throws, the audit log already has a
   record of the attempt. There is no "tool ran but we forgot to log
   it" failure mode.
2. **Write tools short-circuit.** When `requires_confirmation=True`
   the handler is never called; `invoke()` returns the `call_id` and
   `"pending_confirmation"`. A separate confirm-and-execute path
   (next sub-phase) is responsible for actually running the write.
3. **`declared=True` is intentional.** The tool's own `pii_schema`
   already names the fields that may carry PII. By passing
   `declared=True` to `scrub`, the redactor treats every hit as
   `LOW` — the expected case for a tool whose schema acknowledges
   PII surfaces. If a `list_modules` row ever emits, say, an email,
   the redactor will scrub it but won't fire a `HIGH` alarm. The
   tool's schema is the declaration.

## Why `invoke()` does not wrap a transaction

`audit_log.write_call()` and `audit_log.update_status()` each commit
on their own (durability-over-atomicity, see 33-01). That is what lets
the audit row survive even if the handler crashes. Wrapping `invoke()`
in a transaction would defeat that property — a rollback would erase
both the audit row *and* whatever crash-evidence it was meant to
capture. So `invoke()` issues no `BEGIN`/`COMMIT` itself; it relies on
each component to manage its own durability.

The handler runs against the session passed in by the caller and uses
whatever transactional discipline that session already provides (read
tools usually run inside the same SQLAlchemy session as the request
that triggered the agent turn). The audit log writes are independent.
The redactor is pure-functional and touches no database at all.

## Files

- `backend/app/copilot/agent/tools/base.py` — `Tool` dataclass + `invoke()` wrapper (55 lines).
- `backend/app/copilot/agent/tools/registry.py` — module-global registry (22 lines).
- `backend/app/copilot/agent/tools/list_modules.py` — first tool (77 lines).
- `backend/app/copilot/agent/tools/__init__.py` — import-time registration (4 lines).
- `backend/tests/copilot/agent/test_registry.py` — 4 registry tests.
- `backend/tests/copilot/agent/test_tool_list_modules.py` — 3 handler tests.
- `backend/tests/copilot/agent/test_tool_invoke.py` — 2 end-to-end dispatcher tests.
- `backend/tests/copilot/agent/conftest.py` — autouse `_reset_registry` fixture.
