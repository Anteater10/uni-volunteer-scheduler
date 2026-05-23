# 34-01: Memory Schema — Free-Form Profile + Session Lifecycle Columns

## Purpose

Phase 34 gives the copilot a memory that survives across sessions. The data
model is intentionally minimal: one row per user holding a free-form text
blob, plus three small lifecycle columns added to the existing
`copilot_sessions` table. This document describes the schema, the reasoning
behind it, and the operations each column will end up driving in later
sub-phases.

## What we added

Migration `0022_add_copilot_user_profiles_and_session_columns.py` makes two
changes against the existing copilot schema (last touched in Phase 33).

### New table — `copilot_user_profiles`

| Column | Type | Notes |
|---|---|---|
| `user_id` | uuid, PK, FK → `users.id` ON DELETE CASCADE | One row per user. When the user is deleted, the profile vanishes with them. |
| `profile_text` | text, NOT NULL, default `''` | The blob. Plain text. No structure imposed at the DB layer. |
| `version` | int, NOT NULL, default `0` | Monotonic counter, incremented every time the extractor rewrites the profile. Used in the API response so the frontend can detect updates. |
| `updated_at` | timestamptz, NOT NULL, default `now()` | When the current `profile_text` was written. |

### New columns on `copilot_sessions`

| Column | Type | Drives |
|---|---|---|
| `closed_at` | timestamptz, nullable | Frontend-initiated session close — the user clicks "end chat", the API stamps this column, and the extractor fires. NULL means "still open". |
| `last_message_at` | timestamptz, NOT NULL, default `now()` | Every assistant or user message bumps this. The Celery beat job uses it to find idle sessions to sweep. |
| `profile_extracted_at` | timestamptz, nullable | Idempotency guard. Once the extractor commits a new profile row, this is stamped on the session it consumed. The sweeper skips any session where this is non-NULL. |

A composite index `ix_copilot_sessions_idle_sweep (last_message_at, closed_at)`
supports the sweeper's lookup pattern (`WHERE closed_at IS NULL AND
last_message_at < now() - interval '30 minutes'`).

## Why a free-form blob and not structured columns

Spec decision #4 (see `.planning/phases/34-memory-multi-turn/SPEC.md`) locked
this choice. The reasoning, in short:

- The set of things worth remembering across sessions is open-ended. A
  participant might want the copilot to know they prefer afternoon shifts;
  an organizer might want it to remember that one specific school has a
  noisy fire alarm that the copilot should warn volunteers about. Trying to
  enumerate those into columns up front would be guesswork.
- The extractor is an LLM. Asking it to emit free-form prose is something
  modern instruction-tuned models do well; asking it to emit a strict JSON
  schema that we then re-render to prose adds two failure modes (schema
  drift and re-rendering) without giving us anything we couldn't already
  query.
- The downstream consumer is also an LLM (the chat agent). Free-form prose
  is precisely the format the consumer wants. Forcing a structured shape
  would force a join + render step on every chat turn for no measurable win.

The cost of this choice is that we cannot do SQL analytics on profile
contents. That cost is acceptable because the paper's analyses care about
*whether memory helps task success*, not about counting profile slots.

## Why no `copilot_user_profile_history` table

Each extractor run **overwrites** `profile_text` and bumps `version`. We
deliberately did not add a history table in v1 for three reasons:

1. The paper's evaluation does not need it. Memory adversarial scenarios
   (Phase 34-10) check current behavior, not regression against past
   profile states.
2. A history table would double the storage churn and add a new GC concern
   (when does old history age out?). The current design has bounded
   storage: O(users), full stop.
3. If we later decide we need history, we can add it without changing the
   live read path — the new table would be append-only and the current
   single-row read in `GET /copilot/profile` would not change.

Operators who need to inspect a profile drift over time can subscribe to
Postgres logical replication or stand up an ad-hoc trigger. We are not
ruling that out, just not paying for it on day one.

## Why three separate timestamps on `copilot_sessions`

Each timestamp serves a different reader.

- `last_message_at` is read by the **idle sweeper** (Phase 34-03). It needs
  a column that is updated on every message append, not every row read.
- `closed_at` is set by the **session close endpoint** (Phase 34-03). It
  flips a session from "open" to "closed" without deleting it — the audit
  log and message history stay queryable.
- `profile_extracted_at` is set by the **extractor task** (Phase 34-06).
  It is the idempotency token: even if both the close endpoint and the
  sweeper fire on the same session, only one extractor run wins (whichever
  commits its `UPDATE` first), and the other sees `profile_extracted_at IS
  NOT NULL` on re-read and bails.

Collapsing any pair of these into a single column would couple their
semantics. Keeping them separate makes the protocol obvious to anyone
reading the schema cold.

## Add-column vs sidecar table

We added the three columns directly to `copilot_sessions` rather than
introducing a `copilot_session_lifecycle` sidecar. The trade-off:

- **Pro add-column**: every session read (which already loads the row for
  role/scope checks) now also carries lifecycle state, no extra join. The
  three columns total 24 bytes (three `timestamptz` slots), trivial.
- **Con add-column**: schema migrations against a hot table need brief
  exclusive locks for the `NOT NULL DEFAULT now()` column. We accept this
  because the table is small in this project (low-thousands of rows in the
  evaluation horizon) and the migration runs against an empty production
  copy of the same schema.

A sidecar would have been justified only if any of the new columns were
high-frequency churn against a high-read table. None of them are.

## Migration ordering

`down_revision = "0021_add_copilot_tool_calls"`. The migration is additive
only — no data backfill needed. Existing `copilot_sessions` rows get
`last_message_at = now()` from the column default, which is the right
behavior: a session with no recorded last-message timestamp is treated as
"just talked" until the next real message lands, which can't be worse than
treating it as ancient.

## What this sub-phase does *not* deliver

To keep the diff reviewable, sub-phase 34-01 ships *only* the schema and
the ORM. The API surface (`GET`/`DELETE /copilot/profile`) lands in 34-02.
The session-close endpoint, the sweeper, and the extractor all land later.
At the end of 34-01 the database knows how to hold a memory; nothing yet
writes one.
