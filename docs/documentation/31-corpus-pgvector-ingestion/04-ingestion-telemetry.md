# Ingestion Telemetry Schema (`ingestion_runs`)

## Summary

Each invocation of the corpus ingestion CLI
(`python -m app.corpus.ingest`) writes exactly one row to the
`ingestion_runs` table. The schema records 22 columns covering
provenance (which code and configuration produced the run),
execution (which embedding pipeline ran), counters (what work
was performed), and outcome (status, errors, free-form notes).
The design follows the per-message telemetry pattern established
in Phase 30 [CITED: copilot_messages, Phase 30 SUMMARY] and is
intended to support the Phase 35 evaluation without backfill.

## Schema (Alembic revision `0019`)

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | uuid | primary key | run identifier |
| `started_at` | timestamptz | not null, default now() | wall-clock run start |
| `completed_at` | timestamptz | nullable | wall-clock run end |
| `status` | text | not null, default `'running'` | one of `running`, `succeeded`, `partial`, `failed` |
| `git_commit_sha` | char(40) | nullable | `git rev-parse HEAD` at start |
| `git_dirty` | boolean | not null, default false | `true` if working tree had uncommitted changes |
| `source_globs` | jsonb | not null | allow-list snapshot |
| `embedding_provider` | text | not null | configured primary provider name |
| `embedding_model` | text | not null | configured primary model ID |
| `embedding_dim` | integer | not null | 1024 (locked) |
| `chunker_version` | text | not null | e.g. `'v1-recursive-char-1024-128'` |
| `files_scanned` | integer | not null, default 0 | files matched by walker |
| `files_unchanged` | integer | not null, default 0 | skipped due to content hash match |
| `files_ingested` | integer | not null, default 0 | newly committed |
| `files_failed` | integer | not null, default 0 | per-document failures |
| `chunks_emitted` | integer | not null, default 0 | total chunks produced |
| `chunks_embedded` | integer | not null, default 0 | chunks that called the embedder |
| `embedding_api_calls` | integer | not null, default 0 | total provider calls |
| `embedding_latency_ms_total` | bigint | not null, default 0 | summed provider latency |
| `embedding_tokens_total` | integer | not null, default 0 | provider-reported tokens |
| `error_class` | text | nullable | exception class on failure |
| `error_message` | text | nullable | exception message on failure |
| `notes` | text | nullable | newline-separated free-form events |

Index: `(started_at DESC)` to support the "most recent run" query
without a sequential scan.

## Lifecycle

A run row is inserted at start with `status='running'` and the
provenance fields populated. As documents are processed, counters
are accumulated in process memory and flushed to the row at
completion. On normal termination, `completed_at` is stamped and
`status` is set to `succeeded`. If any document fails, `status`
becomes `failed` and the first observed `error_class` and
`error_message` are recorded; counters reflect partial progress.
A `partial` status value is reserved for analyses that wish to
distinguish total failure from mid-run failure, though the current
ingestion path uses `failed` for both cases (see writeup 04 of the
learning folder for the rationale).

## Idempotency anchor

The pairing of `corpus_documents.source_path` and
`corpus_documents.content_sha256` under a unique constraint enables
the CLI to detect unchanged documents and skip both chunking and
embedding. The skip is counted in `files_unchanged`; the document
and chunk rows from the prior run remain unchanged. This makes
re-running the CLI on an unmodified repository a constant-time
no-op (one walker pass plus N content hashes plus one new
`ingestion_runs` row).

## Foreign-key relationships

`corpus_documents.ingestion_run_id` and
`corpus_chunks.ingestion_run_id` are non-null foreign keys with
`ON DELETE RESTRICT`. The `RESTRICT` semantics protect historical
chunks from accidental loss if a run row is targeted for deletion;
the project policy is to never delete `ingestion_runs` rows.

## Fallback event recording

When the configured primary provider raises `RateLimitError` and a
fallback is configured, the ingest loop transparently retries on
the fallback. The transition is recorded in the `notes` column as
a newline-separated event. The per-chunk
`corpus_chunks.embedding_provider` and
`corpus_chunks.embedding_model` columns record the provider that
actually produced each row, allowing the retrieval layer to filter
on provider isolation at query time.

## Paper-grade ratios derivable from the schema

The columns are chosen to support several analyses directly via
aggregate SQL:

- **Cache-hit rate per run:**
  `chunks_emitted - chunks_embedded` divided by `chunks_emitted`.
- **Effective per-chunk embedding latency:**
  `embedding_latency_ms_total / NULLIF(chunks_embedded, 0)`.
- **Per-run failure rate:**
  `files_failed / NULLIF(files_scanned, 0)`.
- **Cross-run drift detection:**
  Compare `files_unchanged` for consecutive runs against the same
  git commit; non-zero `files_ingested` between commits with no
  source diff indicates a chunker-version or content-normalization
  change.

These ratios are expected to anchor the Phase 35 evaluation
section's "ingestion characteristics" subsection.

## Privacy considerations

No personally identifiable information is recorded in
`ingestion_runs`. The `source_globs` column contains glob patterns,
not file contents. The `notes` column is reserved for system events,
not user data. The ingestion pipeline reads only allow-listed
source files and opens no database connections to PII tables; the
telemetry table inherits this property by construction.

## References

- PostgreSQL JSONB documentation —
  https://www.postgresql.org/docs/16/datatype-json.html
  (accessed 2026-05-10).
- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly,
  2017. Chapter 11 — stream processing and event sourcing.
- Phase 30 telemetry schema writeup —
  `docs/documentation/30-streaming-chat-mvp/telemetry-schema.md`
  (the pattern this writeup extends from per-message to per-run).
