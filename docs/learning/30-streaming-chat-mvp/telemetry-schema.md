# Telemetry as a First-Class Research Artifact

> _Stub — to be filled in alongside the `copilot_messages` migration._

## Why this matters

Most production systems treat telemetry as observability — debug logs
to grep when something breaks. We treat it as the **raw data table for
the paper**. Every column on `copilot_messages` corresponds to a possible
column in a Phase 35 evaluation results figure. If we forget to log a
field at Phase 30, we either rebuild it at Phase 35 (expensive) or write
a weaker paper (worse).

## The intuition (to expand)

- The model is the experiment. The DB row is the result.
- Logs are append-only. They are the corpus from which the eval harness
  later runs analyses.
- Hashes (`prompt_hash`, `response_hash`) let us count exact-duplicates
  cheaply without storing PII or full prompts twice.

## The mechanism (to expand)

Columns and *why* each one earns its keep:

- `model_id` — required for cross-model comparison.
- `latency_ms` — performance contribution.
- `prompt_tokens`, `completion_tokens` — cost + context analysis.
- `prompt_hash`, `response_hash` — dedup, cache hit detection.
- `role` — separates admin from organizer behavior.
- `error` — failure-mode taxonomy (paper contribution #3).

## Why we chose it here (to expand)

- Locking the schema at Phase 30 means Phase 35 analyses just read SQL.
- Every later phase adds columns via Alembic migrations; no reshape.

## What to read next

- "Designing Data-Intensive Applications" Ch. 11 (stream processing).
- LangSmith and Helicone telemetry models — what columns the production
  observability vendors think matter.
