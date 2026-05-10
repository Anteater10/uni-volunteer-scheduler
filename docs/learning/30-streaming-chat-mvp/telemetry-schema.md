# Telemetry as a First-Class Research Artifact

## Why this matters

Most production systems treat telemetry as observability — debug logs
to grep when something breaks. We are doing something different:
**`copilot_messages` is the raw data table for the paper.** Every
column corresponds to a possible column in the Phase 35 evaluation
results. If we forget to log a field at Phase 30, we either rebuild it
at Phase 35 (expensive, sometimes impossible) or write a weaker paper
(worse).

This is the most important design document in the milestone, because
the schema is the hardest thing to change later. Code can be rewritten
for free. A column you forgot to add three months ago is gone.

## The intuition

There are two ways to think about a database table:

1. **As state.** The table represents what currently is. A row goes
   stale or wrong; you `UPDATE` it. SQL was designed for this view.
2. **As an event log.** The table records what happened. Rows are
   immutable. You never `UPDATE` them; you just `SELECT` over them and
   roll up.

`copilot_messages` is the second kind. Each row is one model
invocation, frozen at the moment it ended. Future analyses are SQL
queries over this log. This pattern is sometimes called "event
sourcing" or "append-only logs"; the canonical reference is Kleppmann's
*Designing Data-Intensive Applications*.

The implication for schema design: every field that future-you will
want to filter, group, or join on must already be in the table at write
time. You cannot retroactively add `model_id` to a row that didn't
record it.

## The mechanism

The schema is two tables (`copilot_sessions` and `copilot_messages`)
joined by `session_id`. Sessions hold conversation-level metadata that
shouldn't be repeated per-row. Messages hold every turn.

### `copilot_sessions`

| Column | Type | Why it earns its keep |
|---|---|---|
| `id` | uuid | primary key |
| `user_id` | uuid FK → users | who is talking — required for role analysis |
| `created_at` | timestamptz | session start; needed for time-of-day cohorts |
| `model_id` | text | which model the session was started with |
| `system_prompt_hash` | text | SHA-256 of the rendered system prompt |
| `system_prompt_version` | text | human-readable version (e.g. `"v0.1.0"`) |

The hash + version pair is redundant on purpose. The hash is canonical
(it is the actual fingerprint). The version is for humans reading the
DB; you don't have to reverse-engineer which prompt `4f8a...` is.

### `copilot_messages`

| Column | Type | Why it earns its keep |
|---|---|---|
| `id` | uuid | primary key |
| `session_id` | uuid FK | conversation grouping |
| `role` | enum(user, assistant, system) | message author |
| `content` | text | what was said |
| `created_at` | timestamptz | wall-clock |
| `latency_ms` | integer (assistant only) | end-to-end model latency |
| `prompt_tokens` | integer | upstream usage report |
| `completion_tokens` | integer | upstream usage report |
| `prompt_hash` | text | SHA-256 of the chat history sent to the model |
| `response_hash` | text | SHA-256 of the assistant text |
| `model_id` | text | which model actually answered (post-fallback) |
| `error` | text nullable | exception class name when call failed |

### Why each non-obvious column exists

- **`latency_ms`** — answers "is the model fast enough?" without
  separate APM. Phase 35 figure: latency CDF per model.
- **`prompt_tokens` / `completion_tokens`** — cost per turn (free tier
  today, but the paper needs the cost numbers anyway), and a sanity
  check on prompt size when context windows get tight.
- **`prompt_hash`** — duplicate detection for caching analysis, and
  a way to count "how many distinct questions are people asking?"
  without storing the prompt text twice.
- **`response_hash`** — same, on the answer side. Particularly
  valuable for spotting model degeneracy (same response to many
  different prompts).
- **`model_id`** — *required* for cross-model comparison. Logged
  per-row because fallback can change which model answered mid-session.
- **`error`** — Phase 33's failure-mode taxonomy is built from this
  column. Free-tier rate limits, vendor 5xx, timeouts, our own bugs —
  they all show up as distinct exception class names.

### What we deliberately did NOT add

- No `cost_usd`. Free tier today; Phase 35 derives cost from token
  counts × the price sheet at eval time.
- No `tool_calls` JSON. Phase 30 has no tools. Phase 33 will add a
  separate `copilot_tool_calls` table rather than bloating this one.
- No vector embedding of the prompt. Embeddings can be computed later
  from `content`; storing them now would balloon the table for no
  current consumer.

## Why we chose to log everything from day one

The opposite policy — start small, add columns when they're needed —
seems sensible but is in fact a trap. Once the system is in production,
each missing column is a migration plus a backfill plus a "what about
the historical rows?" debate. Logging every field on day one costs us
~12 columns of disk; we have far more than 12 columns of disk.

Concretely: the SUMMARY table for the paper will rely on `latency_ms`,
`prompt_tokens`, `completion_tokens`, `prompt_hash`, `response_hash`,
`model_id`, `role`, and `error`. Skip any one and the paper has a hole.

## What to read next

- Kleppmann, *Designing Data-Intensive Applications*, Ch. 11 — stream
  processing, event sourcing.
- [LangSmith schema](https://docs.smith.langchain.com/) — what columns
  the leading observability vendor thinks matter (we converged on
  similar choices).
- [Helicone schema](https://docs.helicone.ai/) — same exercise.
