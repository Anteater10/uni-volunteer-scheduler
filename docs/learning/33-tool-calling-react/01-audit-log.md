# Learning: Why the Copilot Has an Audit Log

## A scenario to start with

Imagine an organizer pings you on a Friday afternoon. "The copilot just
emailed something weird to one of my participants. Can you figure out
what happened?"

You have a few choices. You could SSH into the box and grep through stdout
logs, hoping the relevant lines weren't already rotated away. You could
ask the LLM to "remember" what it did, which it won't. Or — if you planned
ahead — you could open `psql`, run one query against `copilot_tool_calls`,
and see the exact arguments the agent passed, whether the user clicked
confirm, what came back, and how many redactor hits fired on the way.

That last option is what we are building here. The table is the answer
to "what did the copilot actually do?" — every time, for every session,
forever (or until retention says otherwise).

## The two pillars of agent safety

There's a useful way to think about safety for any system that can take
actions in the world on a user's behalf:

1. **Prevent bad things from happening.** Guardrails, confirmation modals,
   permission checks, rate limits, the redactor.
2. **Prove that bad things didn't happen.** Or, if they did, reconstruct
   exactly how. This is *accountability*, and it lives in the audit log.

You need both. Pillar 1 without pillar 2 means every incident becomes a
guessing game. Pillar 2 without pillar 1 means you have great forensics
but a lot of incidents. The audit log is the spine of pillar 2.

## Why "immutable, append-only, commit-per-row" matters

An audit log that can be edited isn't an audit log; it's a draft. So the
design commits to three properties:

- **Append-only.** No `UPDATE` paths that destroy the prior state. We
  *do* update the `confirmation_status` field as the call progresses,
  but the row is born with `pending` (or `not_required`) and only moves
  forward through the state machine.
- **Immutable once terminal.** Once a row reaches `executed`, `rejected`,
  or `expired`, nothing in the codebase touches it again.
- **Commit-per-row.** Each audit write is its own transaction. It does
  not piggyback on the caller's transaction.

That last one is the subtle one and worth dwelling on.

## "Commit-per-row" — why we don't share the caller's transaction

Imagine the agent calls a write tool, like `send_email`. The naive flow is:

```
BEGIN
  INSERT into copilot_tool_calls (..., status='pending')
  ...wait for user confirm...
  UPDATE copilot_tool_calls SET status='executed', result_json=...
  INSERT into outbox (email rows)
COMMIT
```

What happens if the email send fails and we roll back? The audit row
*also* vanishes. Now you have a failed action with **no evidence it was
ever attempted**. That is the worst possible state for an audit log.

So we flip it: the audit row commits *on its own*, immediately, before
any downstream effect. If the email then fails, we update `result_json`
to record the failure — in its own transaction — and the original
attempt is still on disk. We trade strict consistency between audit
and effect for durability of the audit itself, and that is the right
tradeoff for accountability.

## A worked example: "email all participants"

An organizer types: *"Please email all my Tuesday participants reminding
them to bring lab coats."*

The agent decides to call the `send_bulk_email` tool. Here is what the
audit row looks like at each stage:

**Stage 1 — agent emits tool call (`status = pending`):**

```json
{
  "call_id": "5d4f...",
  "session_id": "8e2c...",
  "caller_id": 142,
  "role": "organizer",
  "tool_name": "send_bulk_email",
  "args_json": {
    "audience_filter": {"day": "tuesday"},
    "subject": "Reminder: lab coats",
    "body": "Hi, please remember..."
  },
  "result_json": null,
  "confirmation_status": "pending",
  "redactions_applied": 0,
  "started_at": "2026-05-22T14:02:11Z"
}
```

**Stage 2 — organizer clicks confirm, tool runs:**

```json
{
  "result_json": {"sent": 18, "skipped": 0, "errors": []},
  "confirmation_status": "executed",
  "redactions_applied": 2,
  "completed_at": "2026-05-22T14:02:14Z",
  "latency_ms": 3100
}
```

Two redactions fired — probably participant email addresses inside the
result payload. They were masked before being stored. Three days later
when the organizer asks "wait, who got that email?", you can answer
*exactly*, with evidence.

## Why `args_json` is JSONB, not text

If we stored args as a `text` blob, every analysis query would start with
`json_parse` and end in tears. If we stored them as separate columns
(`arg_1`, `arg_2`...) we'd need a migration every time a tool's signature
changed. JSONB gives us both worlds: structured access via `args_json->>'subject'`
and zero schema churn when a tool evolves.

It also lets us build GIN indexes inside the blob when one tool becomes a
hot path. We don't pay that cost up front; we add it only when query
patterns demand it.

## How the paper's failure taxonomy gets built

The paper has a section that says, roughly: "Across N sessions, the
agent attempted M tool calls; X% required confirmation; of those, Y%
were rejected; the most common rejection reasons were ...". Every
number in that paragraph is one `GROUP BY` query against this table.

A concrete pipeline:

1. Pull every row for the experimental cohort window.
2. Bucket by `tool_name` → counts of `executed` vs `rejected` vs `expired`.
3. For `rejected`, optionally cluster `args_json` to see what kinds of
   arguments humans tend to reject (e.g. emails to "all participants"
   regardless of filter quality).
4. Cross-tab `redactions_applied > 0` against `tool_name` to find which
   tools most often touch sensitive data.

None of this requires new instrumentation. It all falls out of the schema
because the schema was designed around it.

## "Why not just log to stdout?"

A reasonable question. Stdout logs are easy. So why a whole table?

- **Rotation eats them.** Anything older than a week is probably gone.
- **No structure.** You parse strings, badly, every time.
- **No referential integrity.** You can't join logs to users or sessions
  without writing yet more parsing.
- **No transactional guarantee.** A crashed worker may have buffered
  log lines that never made it to disk.
- **Not redacted by default.** Stdout will happily print PHI; the audit
  writer runs everything through the redactor first.

For shipping a product *and* writing a paper about it, structured rows in
Postgres win on every axis. The stdout logs still exist (the dev loop
needs them), but they are not the source of truth. This table is.

## Takeaway

If you remember one thing: the audit log is not a logging feature. It is
a research instrument and a safety instrument that happens to look like a
table. Treat its rows the way you'd treat lab notebook entries — written
once, never erased, queried often.
