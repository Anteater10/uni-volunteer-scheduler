# `copilot_messages` — Research-Grade Telemetry Schema

> _Stub — to be filled in alongside the Alembic migration._

## Summary

Every model invocation in the AI Onboarding Copilot produces one row in
`copilot_messages`. The schema is designed to support the Phase 35
multi-model evaluation and the eventual paper's empirical contributions
without requiring backfill or reshape. The columns commit to schema
stability for the duration of the milestone; future phases extend by
adding columns rather than rewriting existing ones.

## Schema

| Column | Type | Purpose |
|---|---|---|
| `id` | uuid | primary key |
| `session_id` | uuid FK → `copilot_sessions` | conversation grouping |
| `role` | enum(`user`,`assistant`,`system`) | message author |
| `content` | text | rendered message |
| `created_at` | timestamptz | wall-clock timestamp |
| `latency_ms` | integer | end-to-end model call latency |
| `prompt_tokens` | integer | OpenRouter usage report |
| `completion_tokens` | integer | OpenRouter usage report |
| `prompt_hash` | text | SHA-256 over rendered prompt |
| `response_hash` | text | SHA-256 over completion |
| `model_id` | text | OpenRouter model identifier |
| `error` | text nullable | error class string when call failed |

## Stability commitments

- Columns are append-only across phases 30–38.
- Renames or type changes require a milestone-level change request.

## References

- To be added at fill-in.
