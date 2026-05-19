# FTS substrate: `corpus_chunks.fts` tsvector + GIN

**Phase:** 32 — RAG retrieval (hybrid + local rerank + citations)
**Task:** Plan 01 — Alembic migration `0020_add_corpus_chunk_fts_column`

## TL;DR

Phase 32 introduces lexical retrieval over the Phase-31 corpus by
adding a single generated `tsvector` column and a GIN index on
`corpus_chunks`. The migration is strictly additive — no edits to
existing columns, no application backfill, no changes to the ORM. The
generated column auto-populates the existing 4,731 chunks at `ALTER
TABLE` time.

## The shape

```sql
ALTER TABLE corpus_chunks
  ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX ix_corpus_chunks_fts ON corpus_chunks USING GIN (fts);
```

Two statements, one new column, one new index. The `coalesce` guards
the `to_tsvector` call against any future `content IS NULL` state
(the column is currently `NOT NULL`, but the guard costs nothing).

## Design choices (and rejected alternatives)

| Decision | Choice | Rejected | Reason |
|---|---|---|---|
| Text-search config | `english` | `simple` | Snowball stemmer + stopword list match how users phrase chat questions; `simple` only fits identifier-heavy text. [CITED: postgresql.org/docs/current/textsearch-controls.html] |
| Population mechanism | `GENERATED ALWAYS AS … STORED` | Trigger-maintained column | Declarative constraint lives in the schema; no separately versioned trigger function to drift; auto-backfills existing rows at `ALTER TABLE` time. [CITED: postgresql.org/docs/current/ddl-generated-columns.html] |
| Index type | GIN | GiST | Read-heavy / append-mostly corpus. GIN is faster for searches; GiST is faster to update. We optimise for the query side. [CITED: postgresql.org/docs/current/textsearch-indexes.html] |
| Query operator (downstream Plan 02) | `plainto_tsquery` | `to_tsquery` | User input must not be parsed as a tsquery expression — operator-injection class of bug. `plainto_tsquery` treats input as ANDed plain words. [CITED: postgresql.org/docs/current/textsearch-controls.html] |
| Search service | Postgres built-in FTS | Elasticsearch / Meilisearch / OpenSearch | Corpus is ~5k chunks. Postgres FTS handles low-millions of documents on commodity hardware; a second search daemon is operational debt with no measurable benefit at our scale. |

## Migration round-trip behaviour

`downgrade()` runs in strict reverse order:

```sql
DROP INDEX IF EXISTS ix_corpus_chunks_fts;
ALTER TABLE corpus_chunks DROP COLUMN IF EXISTS fts;
```

The `IF EXISTS` guards make the downgrade idempotent — running it
twice does not error. After downgrade the column is gone and the
index is gone; re-`upgrade` rebuilds both. The round-trip test
(`test_round_trip_clean`) asserts this end-to-end on a real Postgres
session.

## What the test suite proves

`backend/tests/test_corpus_fts_migration.py` — 4 tests:

1. **`test_upgrade_adds_fts_column_and_index`** — column exists and
   has type `tsvector`; index exists and uses GIN method.
2. **`test_existing_rows_populated`** — after seeding two chunks and
   re-querying, every chunk has a non-null `fts` value, and
   `fts @@ to_tsquery('english','volunteer')` matches the chunk
   containing "Volunteers" (proves the Snowball stemmer is active).
3. **`test_round_trip_clean`** — downgrade to `0019` removes the
   column and index; re-upgrade restores them.
4. **`test_gin_index_used_by_planner`** — with `enable_seqscan = off`
   the planner picks `ix_corpus_chunks_fts`, proving the index is
   available to the planner. (Production corpus at 4,731+ rows will
   pick the index without coaxing; the test table is too small to
   coax the planner naturally.)

## ORM contract

`backend/app/models.py::CorpusChunk` is **not** modified. Phase 32
retrieval queries the `fts` column via `sqlalchemy.text` only. This
keeps Phase 31's frozen-ORM invariant intact and prevents accidental
`SELECT *` queries from dragging tsvector byte arrays into Python
memory.

## Files changed

| Path | Change |
|---|---|
| `backend/alembic/versions/0020_add_corpus_chunk_fts_column.py` | New — additive migration: `fts` generated column + `ix_corpus_chunks_fts` GIN index. |
| `backend/tests/test_corpus_fts_migration.py` | New — 4 integration tests proving the migration, round-trip, and planner behaviour. |

## Invariants this restores

- **Phase 31 corpus schema is frozen** — additive migrations only.
  Plan 01 honours this: no existing column or index is touched.
- **Per-provider cosine isolation is unaffected** — `fts` is content-
  derived, not embedding-derived. Hybrid blending (Plan 02) still
  filters `WHERE embedding_provider = $1` on the dense side.
- **`app.corpus.*` coverage stays at 100%** — no application code
  ships in this plan; only schema + tests.

## Operational notes

- Migration runs in DDL and is transactional. On a 4,731-row corpus
  ALTER + STORED population is sub-second; the GIN build is bounded
  by tsvector size, not row count.
- For a future-state 50M-row corpus, the same migration is *not*
  immediately safe — Postgres rewrites the heap for STORED generated
  columns. A larger corpus would want batched migration via dual-
  writes. Not relevant at current scale.
- The collation mismatch warning from the test container (PG library
  2.41 vs OS 2.36) is unrelated to this migration; it is pre-existing
  test-DB cruft from a base-image bump and has no semantic effect on
  FTS behaviour.

## References

- PostgreSQL: Text Search Tables —
  https://www.postgresql.org/docs/current/textsearch-tables.html
- PostgreSQL: Generated Columns —
  https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL: GIN and GiST Index Types —
  https://www.postgresql.org/docs/current/textsearch-indexes.html
- PostgreSQL: Parsing Queries (`plainto_tsquery` vs `to_tsquery`) —
  https://www.postgresql.org/docs/current/textsearch-controls.html
