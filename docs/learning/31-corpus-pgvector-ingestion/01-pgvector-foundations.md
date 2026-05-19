# pgvector and the Choice to Stay Inside Postgres

## Why this matters

By Phase 31 we know two things about the copilot. First, the model on
its own is unreliable — it confabulates facts and cannot quote our
codebase. Second, the answer to confabulation is **retrieval**: before
the model writes anything, we hand it the most relevant chunks of our
docs and code. That handoff requires a similarity search over
embedding vectors. A similarity search at our scale is one SQL query —
but only if the database knows how to index a vector.

The decision in front of us is small in code (one extension, two
tables) but large in operational consequences: do we run a dedicated
vector database (Pinecone, Weaviate, Qdrant, Chroma) or do we teach
Postgres the vector trick? Phase 31 picks the second option. This
lecture explains why, and what `pgvector` actually does once it is
installed.

## The intuition

A vector database is not really a separate kind of database. It is a
**plain database with one specialized index**. The data is
fixed-length arrays of floats; the index supports the operator
"approximately nearest under cosine distance"; everything else (rows,
columns, transactions, joins, foreign keys, backups) is exactly what
you already know.

Once you see vector search as an index type rather than a new product,
the right question becomes: does my existing database already support
that index type? For Postgres the answer is yes, via the `pgvector`
extension. The extension contributes three things:

1. A new column type — `vector(N)`, a fixed-length array of `float4`.
2. Three distance operators — `<->` (L2), `<#>` (negative inner
   product), and `<=>` (cosine). We will use `<=>` because our
   embeddings are unit-normalized.
3. Two index types — `IVFFlat` (an inverted file with quantization)
   and `HNSW` (a hierarchical navigable small world graph).

That is all `pgvector` is. There is no separate process, no separate
network port, no separate backup story. The volumes, the credentials,
the migration tooling, the test fixtures — every one of them is
reused.

## The mechanism

To install the extension, we run `CREATE EXTENSION vector;` inside an
Alembic migration. The schema is then three tables:

```
corpus_documents
  id, source_path, source_kind, title, content_sha256, byte_size,
  ingested_at, ingestion_run_id

corpus_chunks
  id, document_id, chunk_index, content, content_sha256,
  char_start, char_end, token_estimate,
  embedding vector(1024),
  embedding_model, embedding_provider, ingestion_run_id

ingestion_runs
  id, started_at, completed_at, status,
  git_commit_sha, git_dirty, source_globs, embedding_provider,
  embedding_model, embedding_dim, chunker_version,
  files_scanned, files_unchanged, files_ingested, files_failed,
  chunks_emitted, chunks_embedded, embedding_api_calls,
  embedding_latency_ms_total, embedding_tokens_total,
  error_class, error_message, notes
```

The `vector(1024)` column on `corpus_chunks.embedding` is the only
field that needs the extension. Everything else is plain text and
integers. From the application's perspective, an `INSERT` writes a
Python `list[float]` and pgvector's psycopg2 adapter converts it to
the binary on-disk representation transparently.

## HNSW versus IVFFlat — the picture in your head

The two indexes that pgvector offers solve the same problem (find me
the K rows whose embedding is closest to this query vector) but with
very different shapes.

`IVFFlat` is *cells*. The index pre-partitions the embedding space
into `N` clusters at build time. A query first picks the nearest few
clusters, then exhaustively scans the rows assigned to those clusters.
It is fast to build, predictable in memory, but recall drops sharply
when a query lands near a cluster boundary.

`HNSW` is a *graph*. Every row becomes a node; nodes that are similar
are connected by edges; edges are arranged in layers (very long-range
on top, very short-range at the bottom). A query walks the graph
greedily, top to bottom, jumping to the closest reachable neighbor at
each step. The result is high recall at small `ef` (search-time
parameter) with minimal tuning. The downside is slower build time and
larger on-disk footprint per row.

For a corpus of a few thousand chunks — which is what this project
will ever hold — HNSW wins on every axis except build time, and we
sidestep build time by building the index *after* the first bulk
ingest rather than at every row insert. See lecture 04 for that
trick.

## Why 1024 dimensions, locked

`vector(N)` is a fixed-width column. You cannot ALTER it from 384 to
1024 without dropping the column and re-embedding every row. So `N`
is one of the most important decisions in the whole milestone. We
pick **1024** because:

- Jina Embeddings v3 (our primary provider) is natively 1024.
- BGE-small (our local fallback) is natively 384; we right-pad to
  1024 with zeros so it fits the same column.
- Voyage 3.5 and Cohere Embed v3 both support 1024 as a named output
  size; if we ever swap providers in Phase 35, no schema change is
  needed.
- Going to 2048 would be wasted disk; going to 512 would foreclose
  the swap path.

The lock-in is what makes the project portable across embedding
providers — the cost is one column type and a `+pad1024` model-name
suffix on the BGE rows.

## The "build index after first ingest" trick

`pgvector` does support incremental insert into an HNSW index, but
each insert pays the cost of routing the new vector through the graph
to find its neighbors and adding edges. On a bulk load of several
thousand rows that overhead is wasted: it is dramatically cheaper to
load all rows first, then build the index in one pass over the final
data. The ingestion CLI exposes a `--build-index` flag for exactly
this reason; the Alembic migration deliberately leaves the index
uncreated. See `backend/app/corpus/ingest.py::build_hnsw_index`.

## Check-in question

If we swap the embedding model from Jina v3 to a hypothetical
"Voyage-4" that natively outputs 768 dimensions, what changes about
our schema, and what stays the same? Take a moment before reading on:
this is exactly the kind of decision Phase 35 will force us to make.

## What to read next

- [pgvector README](https://github.com/pgvector/pgvector) — operator
  classes, index parameters, and the `IF NOT EXISTS` semantics we
  rely on for round-trip safety.
- [Malkov & Yashunin, "Efficient and robust approximate nearest
  neighbor search using HNSW graphs"](https://arxiv.org/abs/1603.09320)
  — the original HNSW paper.
- [dbi-services pgvector DBA guide, 2026](https://www.dbi-services.com/blog/pgvector-2026/)
  — the most current operational comparison of IVFFlat vs HNSW for
  Postgres 16.
