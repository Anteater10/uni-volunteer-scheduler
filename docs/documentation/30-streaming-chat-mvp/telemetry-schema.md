# `copilot_messages` — Research-Grade Telemetry Schema

## Summary

Every model invocation in the AI Onboarding Copilot produces one row
in `copilot_messages`. The schema is designed to support the Phase 35
multi-model evaluation and the eventual workshop paper's empirical
contributions without requiring backfill or schema reshape. The
columns commit to schema stability for the duration of milestone v1.4
(Phases 30–38); future phases extend by adding columns rather than
rewriting existing ones.

## Schema (Alembic revision `0018`)

### `copilot_sessions`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | uuid | primary key | session identifier |
| `user_id` | uuid | FK → `users.id`, not null | session owner |
| `created_at` | timestamptz | not null, default now() | session start |
| `model_id` | text | not null | model selected at session creation |
| `system_prompt_hash` | text | not null | SHA-256 hex of rendered system prompt |
| `system_prompt_version` | text | not null | human-readable prompt version (e.g. `"v0.1.0"`) |

Index: `(user_id, created_at desc)` for the session-list endpoint.

### `copilot_messages`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | uuid | primary key | message identifier |
| `session_id` | uuid | FK → `copilot_sessions.id` cascade, not null | conversation grouping |
| `role` | enum `copilot_message_role` (`user`, `assistant`, `system`) | not null | message author |
| `content` | text | not null | rendered message |
| `created_at` | timestamptz | not null, default now() | wall-clock timestamp |
| `latency_ms` | integer | nullable (assistant only) | end-to-end model call latency |
| `prompt_tokens` | integer | nullable | OpenRouter usage report |
| `completion_tokens` | integer | nullable | OpenRouter usage report |
| `prompt_hash` | text | nullable | SHA-256 hex of the chat history sent to the model |
| `response_hash` | text | nullable | SHA-256 hex of the assistant text |
| `model_id` | text | nullable | model that actually answered (post-fallback) |
| `error` | text | nullable | exception class name when the call failed |

Composite index: `(session_id, created_at)` for in-order message
retrieval per conversation.

## Stability commitments

1. Columns are append-only across milestone v1.4 (Phases 30–38).
2. Renames or type changes require a milestone-level change request
   and an Alembic migration that preserves historical data.
3. Enum members may be added; existing members may not be removed.

## Justification by column

The Phase 35 evaluation depends on every column listed above:

- `model_id` partitions rows for cross-model comparison.
- `latency_ms` produces the latency cumulative distribution function
  per model.
- `prompt_tokens` and `completion_tokens` produce per-turn cost when
  multiplied by the model price sheet at evaluation time.
- `prompt_hash` and `response_hash` enable duplicate detection and
  cache-hit analysis without reprocessing free-text content.
- `role` partitions admin and organizer behavior.
- `error` produces the failure-mode taxonomy that constitutes
  paper contribution #3.

Columns deliberately excluded at this milestone:

- `cost_usd` is derived at evaluation time from token counts and is
  therefore not stored.
- `tool_calls` will be introduced in a separate `copilot_tool_calls`
  table at Phase 33 to avoid bloating the per-message row.
- Vector embeddings are not stored; embeddings are reproducible from
  `content` post-hoc.

## Privacy considerations

Through Phase 32, `content` records full user and assistant text. No
personally identifiable information enters `content` because the model
has no tools that surface PII. From Phase 33 onward, where the model
gains scoped data access, the `content` column will continue to record
the model-visible text and a separate `copilot_tool_calls` audit
table will record structured arguments and results. Text fields
remain in the database; they are not shipped to third-party
observability platforms in the current deployment.

## References

- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly,
  2017. Ch. 11 — stream processing and event sourcing.
- LangSmith schema documentation —
  https://docs.smith.langchain.com/ (accessed 2026-05-08).
- Helicone schema documentation —
  https://docs.helicone.ai/ (accessed 2026-05-08).
