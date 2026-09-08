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
Output schema: `["queued_count", "failed_count", "skipped_count"]`.
The handler resolves
each ID to a `Volunteer.email` internally and dispatches through a
module-level `_dispatch` seam. Organizer scope is enforced through a
"reachable volunteer ID" set derived from non-cancelled signups on the
caller's events; out-of-scope IDs increment `failed_count` without
leaking which ones.

### nudge_understaffed_module (both roles, organizer scoped)

Args: `module_id` (Event UUID). Output schema: `["module_id",
"module_name", "queued_count", "failed_count", "skipped_count"]`.
The handler resolves the recipient
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


## Outbound mail: the transport, and why the counter is named `queued_count`

Both mail tools shipped with a `_dispatch` seam whose production body
was `return True`. Nothing was sent, and the handlers counted those
Trues, so a confirmed send came back `sent_count: 47` and the model
told the admin 47 people had been reminded. That is the K26 defect: not
a missing feature, but a missing feature that **reported itself as
present**. The only signal was 47 no-shows.

The seam is now bound to the same path every other email in the app
uses — a Celery task (`app.celery_app.send_copilot_email`) calling
`_send_email`, which dispatches to SMTP (AWS SES in production) or
SendGrid per `settings.email_mode`. Enqueueing rather than sending
inline is what the recipient cap demands: 200 synchronous SMTP round
trips would exceed the HTTP request budget, and a transient failure
would have no retry.

That choice creates the naming problem the counter solves. At the
moment the tool returns, the message is on a durable broker but has not
been delivered. Calling that `sent_count` would be K26 again at lower
volume — a weaker claim wearing the name of a stronger one. Hence
`queued_count`, and hence `_outbound.QUEUE_SEMANTICS`, appended to both
tool descriptions so the model phrases it honestly too. The guarantee
has to survive the last hop: a tool that returns "queued" and a model
that says "sent" have told the admin the same untruth.

Three counters, deliberately not two:

| Counter | Meaning |
|---|---|
| `queued_count` | Handed to the broker. Not delivered. |
| `skipped_count` | Recipient turned reminder email off. |
| `failed_count` | Out of scope, unknown ID, or unqueueable. |

`skipped_count` is separate because a respected opt-out is not a
failure. Folding the two together would tell an admin something had
gone wrong and invite a retry of a decision the volunteer already made.

Opt-outs are honoured here even though `send_broadcast_email`
deliberately ignores them. The difference is who chose: a broadcast has
a human picking both the audience and the words, and is operational
mail. A copilot nudge has a model picking the audience from a sentence,
and — for `nudge_understaffed_module` — nobody, not even the admin who
confirmed it, ever sees the recipient list. That is the case where an
opt-out has to hold.

The flag still governs on its own. `COPILOT_OUTBOUND_EMAIL_ENABLED=false`
means nothing is built and nothing is enqueued, and the refusal says so.
