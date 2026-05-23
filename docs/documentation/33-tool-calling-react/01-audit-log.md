# 33-01: The Copilot Tool Call Audit Log

## Purpose

The `copilot_tool_calls` table is the durable, append-only record of every tool
invocation the copilot agent attempts during a session. One row is written per
tool call attempt — *before* the tool body runs — and then updated as the call
progresses through confirmation, execution, and (sometimes) rejection. The
table is the canonical source of truth for the paper's failure taxonomy,
post-hoc debugging, and any operator question that starts with "what did the
copilot actually do?".

This document describes the schema decisions, the write protocol, and the
shape of the queries we expect to run against it.

## What each row stores

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | Internal surrogate, not exposed to clients. |
| `call_id` | uuid, unique | Stable per-call identifier. Generated at the *start* of the call and reused for every update. |
| `session_id` | uuid, FK → `copilot_sessions.id` | `ON DELETE CASCADE` — sessions and their tool calls live and die together. |
| `caller_id` | bigint, FK → `users.id` | `ON DELETE SET NULL` — historical rows survive user deletion. |
| `role` | text | Caller's role at call time (`participant`, `organizer`, `admin`). Captured at write time because role can change later. |
| `tool_name` | text | Registry key, e.g. `search_participants`. |
| `args_json` | jsonb | The arguments the agent supplied, post-validation. |
| `result_json` | jsonb, nullable | Tool output (or error envelope) once execution completes. |
| `confirmation_status` | text | See state table below. |
| `redactions_applied` | int, default 0 | Count of redactor hits inside `args_json` + `result_json`. |
| `started_at` | timestamptz | When the row was first inserted. |
| `completed_at` | timestamptz, nullable | When the call reached a terminal status. |
| `latency_ms` | int, nullable | Convenience field; derived but stored so the paper's plots don't have to subtract every time. |

## Why a per-call UUID instead of the serial id

The serial `id` is fine for joins inside Postgres, but the agent loop, the
React UI, and the WebSocket protocol all need a stable identifier *before*
the row is committed. We mint a UUID in Python at the moment the LLM emits
a tool call, pass it through the confirmation flow, and only then write the
final state. Using the serial id would mean either (a) doing a `RETURNING id`
round trip on the synchronous insert (fine but couples the protocol to the
DB) or (b) flipping ids on retry. UUIDs sidestep both problems and make the
audit log portable if we ever ship it to a warehouse.

## Why JSONB for args and result

Tool argument shapes evolve constantly during research. `search_participants`
today takes `{query, limit}`; tomorrow it might add `{include_inactive}`.
Storing args as JSONB means:

- No schema migration when a tool changes its signature.
- We can index the inside of the blob (`CREATE INDEX … USING gin (args_json)`)
  if a particular tool becomes hot in queries.
- The paper's analysis scripts can pull arbitrary fields with `args_json->>'query'`
  without us pre-declaring which fields matter.

The cost is that we lose static type guarantees at the DB layer. That's
acceptable here because the validation happens upstream in Pydantic models
before the row is written.

## Commit-per-row: durability over atomicity

The audit write is its own short transaction. It does **not** share a
transaction with the caller. If the request handler rolls back — because
the tool errored, because the user disconnected, because a downstream
write failed — the audit row stays. That is the entire point.

If we wrapped the audit write inside the caller's transaction, every
failed call would also delete its own evidence. For a research artifact,
that's catastrophic. We accept the tradeoff that the audit row and the
side-effect can briefly disagree (e.g. row says `executed` but the email
send failed after commit) and reconcile via `result_json` payloads.

## `confirmation_status` state machine

| Value | Meaning |
|---|---|
| `not_required` | Read-only tool; executed immediately, no human-in-the-loop. |
| `pending` | Write tool, waiting on user confirmation in the UI. |
| `executed` | Tool body ran to completion (success or handled error). |
| `rejected` | User clicked "no" in the confirmation modal. |
| `expired` | Pending row passed its TTL without resolution. |

Terminal states are `executed`, `rejected`, `expired`, and `not_required`.
Once a row reaches a terminal state it is not updated again.

## `redactions_applied`

Every payload going into and coming out of the tool is passed through the
PHI/PII redactor. `redactions_applied` is a simple integer count of redactor
hits on this specific call. We store it denormalised so that aggregate
queries — "show me the top 10 tools by redaction rate this week" — do not
have to re-run the redactor over historical blobs.

## Sample queries for the failure taxonomy

How many calls per tool hit the redactor's HIGH severity branch (we tag
that as `redactions_applied >= 5` for now):

```sql
SELECT tool_name, COUNT(*) AS high_redaction_calls
FROM copilot_tool_calls
WHERE redactions_applied >= 5
GROUP BY tool_name
ORDER BY high_redaction_calls DESC;
```

Which tools have the highest rejection rate:

```sql
SELECT tool_name,
       COUNT(*) FILTER (WHERE confirmation_status = 'rejected')::float
         / NULLIF(COUNT(*) FILTER (WHERE confirmation_status IN ('executed','rejected')), 0)
         AS rejection_rate
FROM copilot_tool_calls
GROUP BY tool_name
ORDER BY rejection_rate DESC NULLS LAST;
```

Average tool calls per session, by role:

```sql
SELECT role, AVG(call_count) AS avg_calls_per_session
FROM (
  SELECT session_id, role, COUNT(*) AS call_count
  FROM copilot_tool_calls
  GROUP BY session_id, role
) s
GROUP BY role;
```

## FK behaviour and historical analysis

- `session_id → copilot_sessions.id ON DELETE CASCADE`: tool calls are
  meaningless without their session context (system prompt, model
  config, conversation state). When a session is purged, its calls go
  with it. Use `copilot_sessions` retention policy as the master knob.
- `caller_id → users.id ON DELETE SET NULL`: users may exercise their
  right to be deleted, but the *behaviour* of the copilot when serving
  them is a research artifact. We null the FK and keep `role` plus the
  redacted args/result.

This split means session-level GDPR purges are clean, while
account-level deletions still let us run cohort analyses.
