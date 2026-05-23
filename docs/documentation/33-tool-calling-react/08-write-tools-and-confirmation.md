# Sub-phase 33-08: Write Tools and the Confirmation Gate

## Purpose

Read tools (sub-phases 33-05 and 33-06) are safe by construction: they
look at the database and return scrubbed payloads. Write tools are not.
A tool that sends email, creates an Event, or moves a Signup mutates
real user-facing state. If the LLM hallucinates a target it can spam
participants, double-book modules, or move someone into a class they
never signed up for. Sub-phase 33-08 is where the agent gains four
write tools and the safety scaffold that keeps them honest.

The contract is simple. A write tool's `invoke()` does **not** run the
handler. It writes a `pending` audit row, parks the call in an
in-process registry, and returns a `pending_confirmation` envelope. The
React frontend renders a confirmation card with the args; the human
clicks approve or deny; the router calls `execute_after_confirmation`
(approve) or `resolve(approved=False)` (deny). Only then does the
handler actually run. **Writes never bypass the human click.**

## The pending store

`backend/app/copilot/agent/confirmation.py` is a single module with a
process-local dict `_PENDING`, a five-minute TTL, and three public
functions:

- `store_pending(call_id, tool_name, args, session_id)` — parks an
  entry. Called from `invoke()` after the audit row is written.
- `resolve(call_id, approved)` — consumes the entry and returns a
  `Decision`. Raises `ConfirmationNotFound` for unknown IDs and
  `ConfirmationExpired` past TTL.
- `execute_after_confirmation(db, call_id, scope_role, caller_id)` —
  looks up the pending entry, resolves the tool from the registry,
  runs the handler under the user's role scope, scrubs the result,
  flips the audit row to `executed`, and pops the entry.

The store is process-local on purpose. Confirmation must round-trip
through a human within minutes; durability across restarts is not a
requirement. The TTL makes sure stale entries do not accumulate if the
user walks away from their screen.

## How `invoke()` branches on writes

`invoke()` in `tools/base.py` calls `_begin()` to write the audit row
(`requires_confirmation=True` parks the row in status `pending`), then
inspects `tool.requires_confirmation`. For writes it calls
`store_pending()` and returns `{"call_id": ..., "status":
"pending_confirmation"}`. The agent loop sees that envelope and yields
a `ConfirmationRequestEvent` instead of a `ToolResultEvent`, then
exits the turn. The handler never runs in the same turn that proposed
it.

## The four write tools

All four set `requires_confirmation=True` and declare a tight
`_PII_SCHEMA` that names only the counters or identifiers the LLM is
allowed to see. Recipient emails, addresses, and other PII never cross
back into the model context.

### send_reminder_email (both roles, organizer scoped)

Args: `participant_ids` (list of Volunteer UUIDs) and `template`.
Output schema: `["sent_count", "failed_count"]`. The handler resolves
each ID to a `Volunteer.email` internally and dispatches through a
module-level `_dispatch` seam. Organizer scope is enforced through a
"reachable volunteer ID" set derived from non-cancelled signups on the
caller's events; out-of-scope IDs increment `failed_count` without
leaking which ones.

### nudge_understaffed_module (both roles, organizer scoped)

Args: `module_id` (Event UUID). Output schema: `["module_id",
"module_name", "notified_count"]`. The handler resolves the recipient
pool from prior non-cancelled signups in the caller's scope and
dispatches via `_dispatch`. An organizer cannot nudge a module owned
by a different organizer — the handler returns the not-found sentinel
in that case.

### create_module_from_template (admin only)

Args: `template_id` (ModuleTemplate slug) and `week` (ISO week).
Output schema: `["new_module_id", "name", "week"]`. The handler
resolves the slug, synthesizes the Monday of the target ISO week plus
`duration_minutes` for `end_date`, and inserts an Event row owned by
the calling admin. Unknown slug returns a not-found sentinel rather
than raising, so the confirmation gate still records the attempt.

### move_participant (admin only)

Args: `participant_id`, `from_module`, `to_module`. Output schema:
`["participant_id", "from_module", "to_module", "status"]`. The
handler finds the first non-cancelled Signup whose slot belongs to
`from_module`, then re-points it at any Slot belonging to `to_module`.
Returns the not-found sentinel if there is no active signup or no
destination slot.

## Why the gate matters

The gate is what makes "tool-calling LLM" safe to ship. Three properties
hold together:

1. **The audit row is written before anything else.** Even if the user
   never confirms, the row sits in `pending` forever — the attempt is
   forensically recoverable.
2. **The args the user sees are the args the handler runs with.** The
   pending store snapshots `args` at `invoke()` time; the LLM cannot
   re-prompt to change them between proposing and executing.
3. **The redactor still runs on the result.** `execute_after_confirmation`
   passes the handler's return value through `scrub(declared=True)`
   exactly like a read tool, so a buggy write handler that leaks PII
   gets the same treatment as a buggy read handler.
