# Ingestion Telemetry as Paper Data

## Why this matters

Phase 30 introduced the discipline of "logs are research data, not
just debug output" — every model call writes a structured row to
`copilot_messages`, and the columns were chosen with the Phase 35
evaluation in mind. Phase 31 extends that discipline to *ingestion*.
A corpus is not interesting; an ingestion *run* is. The same docs
can be re-ingested with a different chunker, a different embedding
model, or a different cut of the source globs, and the paper will
want to compare the results across those runs.

The mechanism is one new table — `ingestion_runs` — with 22
columns. One row is written per invocation of `python -m
app.corpus.ingest`. The columns are deliberately structured: every
field that future-you will want to filter, group, or join on is
already there. The cost is 22 columns of disk per run; the benefit
is that Phase 35's "did the new chunker improve retrieval recall?"
question becomes a single SQL query rather than a forensics
exercise.

## Why one row per CLI invocation

The unit of work is the *run*, not the chunk, because the run is what
the experimenter controls. Two runs of the same code on the same
data produce identical chunks (we are deterministic), so storing
"this chunk was produced by run X" is redundant per-chunk except for
joining back to the run's git SHA and chunker version. We store
both — `ingestion_run_id` is a foreign key on every chunk — so the
join is one-hop in either direction.

A run is identified by a UUID and is flanked by two timestamps,
`started_at` and `completed_at`. The status is one of `running`,
`succeeded`, `partial`, or `failed`. We write the row at start with
`status='running'`, update counters as documents land, and stamp
`completed_at` at the end. This is the Phase 30 pattern, applied
verbatim to ingestion.

## The 22 columns, in four groups

### Provenance — "what code produced this run?"

| Column | Meaning |
|---|---|
| `git_commit_sha` | Output of `git rev-parse HEAD` at run start |
| `git_dirty` | `true` if the working tree had uncommitted changes |
| `source_globs` | JSONB snapshot of the allow-list at run time |
| `chunker_version` | A string like `"v1-recursive-char-1024-128"` |

These four columns let you answer "if I check out this commit and
run with this chunker, do I get the same chunks?" The answer should
always be yes; the columns are the audit trail.

### What ran — "what code path produced the embeddings?"

| Column | Meaning |
|---|---|
| `embedding_provider` | `'jina'` or `'local-bge'` |
| `embedding_model` | The exact model ID, e.g. `'jina-embeddings-v3'` |
| `embedding_dim` | `1024` (locked) |

Note the redundancy with the per-chunk `embedding_provider` column.
That's deliberate: per-chunk lets you filter at retrieval time;
per-run lets you compare runs without scanning all rows.

### Counters — "what actually happened?"

| Column | Meaning |
|---|---|
| `files_scanned` | Files the walker considered |
| `files_unchanged` | Skipped due to content hash match |
| `files_ingested` | Newly written |
| `files_failed` | Errors during embed or commit |
| `chunks_emitted` | Total chunks produced (across all docs) |
| `chunks_embedded` | Chunks that called the embedder (excludes cache hits) |
| `embedding_api_calls` | Number of upstream provider calls made |
| `embedding_latency_ms_total` | Sum of provider latencies (milliseconds) |
| `embedding_tokens_total` | Provider-reported token count (when available) |

These are paper-grade columns. The ratio
`chunks_embedded / chunks_emitted` is your cache-hit rate; the ratio
`embedding_latency_ms_total / chunks_embedded` is your effective
per-chunk embedding cost; `files_failed / files_scanned` is your
failure rate. Every figure in the Phase 35 evaluation section comes
from one of these ratios.

### Outcome — "how did it end?"

| Column | Meaning |
|---|---|
| `started_at`, `completed_at` | Wall-clock timestamps |
| `status` | `running`, `succeeded`, `partial`, or `failed` |
| `error_class`, `error_message` | Exception details if anything failed |
| `notes` | Free-form text, including the fallback-engaged record |

Three subtleties. First, `status='partial'` exists for the case
where some documents committed and others failed. We use `failed`
for that case in practice because partial states are easier to
analyze if you can grep on a single status; the column allows the
distinction if a future analysis needs it. Second, `notes` is where
"primary=jina rate-limited; fell back to local-bge" appears. This
is the only signal you have, at row level, that a fallback event
happened mid-run. Third, the `started_at DESC` index makes the
"show me the last run" query free.

## Idempotency, walked through

The CLI's contract is: re-running on an unchanged repo is a no-op.
The mechanism is content addressing. Each document's identity is
`(source_path, content_sha256)` — a unique constraint on
`corpus_documents`. The ingest loop hashes each file's normalized
content and asks the DB whether that exact pair already exists.
If yes, the file is counted as `files_unchanged` and skipped (no
chunking, no embedding, no DB write). If no, the chunks are
emitted, embedded, and inserted within a single per-document
transaction.

This makes the CLI safe to run on a cron, safe to run after a
single-file edit, and safe to run twice in a row by mistake. The
second run writes one `ingestion_runs` row and updates zero
`corpus_*` rows. The cost of that second run is one full directory
walk plus N content hashes — measured in seconds for our repo.

## The `notes` column as a research artifact

A common engineering mistake is to log fallback events as warnings
that get rotated out of stdout logs after a few days. The Phase 35
analysis will want to know: "in run X, did the fallback engage, and
if so, on which chunks?" Stdout logs cannot answer that question
three months later; a structured column can.

We use `notes` as a poor-man's event log: a newline-separated list
of "things that happened that aren't represented elsewhere in the
row." The current implementation only emits the fallback record,
but the column is sized for more: future contributors should append
to `notes` rather than introduce new columns for one-off events.

## Check-in question

Suppose Phase 35 wants to compare the retrieval recall of "Jina v3
alone" vs "Jina v3 with BGE fallback on rate-limit." Which columns
of `ingestion_runs` do you partition by, and what SQL would you
write to identify each run? Try sketching the query before peeking
at the answer — it is two lines and exercises three different
columns we just walked through.

## What to read next

- [Kleppmann, *Designing Data-Intensive Applications*, ch. 11](https://dataintensive.net/) —
  event sourcing as the right pattern for research-grade logs.
- Phase 30's `telemetry-schema.md` — the per-message version of the
  same discipline we are extending here to per-run.
- [PostgreSQL JSONB documentation](https://www.postgresql.org/docs/16/datatype-json.html)
  — what `source_globs JSONB` actually buys us in terms of indexable
  containment queries.
