# Vector Search Inside PostgreSQL via `pgvector`

## Summary

Phase 31 implements similarity search over a corpus of documentation,
migration metadata, and source-code docstrings by extending the
project's existing PostgreSQL 16 database with the `pgvector`
extension rather than introducing a dedicated vector store. The
extension contributes one column type (`vector(N)`), three distance
operators (Euclidean, negative inner product, cosine), and two
approximate-nearest-neighbor index types (IVFFlat and HNSW)
[CITED: pgvector/pgvector]. All retrieval-relevant operations are
expressed as standard SQL; no separate process, network port, or
backup mechanism is required.

## Schema

Three new tables are introduced in Alembic revision
`0019_enable_pgvector_corpus_tables`:

- `corpus_documents` — one row per ingested source file, keyed by
  `(source_path, content_sha256)`.
- `corpus_chunks` — one row per chunk emitted by the splitter. The
  `embedding` column is typed `vector(1024)`.
- `ingestion_runs` — one row per invocation of the ingestion CLI,
  with paper-grade telemetry columns (see writeup 04).

`corpus_chunks.embedding` is the only column requiring the
`pgvector` extension. The remaining columns are standard PostgreSQL
types. The migration is round-trip safe under
`upgrade -> downgrade -> upgrade`; the downgrade step issues
`DROP EXTENSION IF EXISTS vector` after dropping the dependent
tables.

## Index strategy

The schema deliberately omits a vector index from the migration.
The index is created post-ingest via the ingestion CLI's
`--build-index` flag:

```sql
CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw
  ON corpus_chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

HNSW (Hierarchical Navigable Small World graphs) is preferred over
IVFFlat for this project. The corpus is expected to remain below
10^4 chunks for the duration of milestone v1.4, and HNSW provides
high recall at small `ef` with minimal parameter tuning at this
scale [CITED: Malkov & Yashunin, 2018]. IVFFlat would be the
appropriate choice for corpora exceeding ~10^6 rows where build
time and memory pressure dominate. The build-after-ingest pattern
is the documented best practice for pgvector HNSW: the bulk path
is materially faster than per-insert graph updates
[CITED: pgvector/pgvector].

## Distance operator

Cosine similarity (`<=>`) is used because the production embedding
model (Jina v3) produces unit-normalized vectors, for which cosine
distance is equivalent to Euclidean distance up to a constant. The
cosine operator class (`vector_cosine_ops`) provides the
corresponding HNSW index. Negative inner product (`<#>`) would
yield equivalent rankings for unit vectors but is less idiomatic
in the pgvector documentation.

## Dimensionality lock

The vector column type is fixed at 1024. PostgreSQL's `vector(N)`
type does not support `ALTER COLUMN ... TYPE vector(M)`; widening
or narrowing requires dropping and recreating the column, which
invalidates all existing embeddings. The choice of 1024 is
explained in writeup 02; the operational implication for the
schema is that the column type is immutable for the lifetime of
the corpus.

## Why not a dedicated vector database

The alternative — Pinecone, Qdrant, Weaviate, or Chroma — was
evaluated and rejected on three grounds:

1. **Operational surface.** Adding a separate database adds a
   process, a network endpoint, a backup target, and a credentials
   path. Phase 31 already requires changes to the `docker-compose`
   stack (image swap from `postgres:16` to `pgvector/pgvector:pg16`);
   no further runtime services are necessary.
2. **Transactional coherence.** Ingestion involves writing rows to
   `corpus_documents`, `corpus_chunks`, and `ingestion_runs`
   atomically per document. A dedicated vector store would require
   distributed transaction protocols or eventual-consistency
   reconciliation. Single-database operation eliminates both.
3. **Cost.** All evaluated dedicated stores have non-trivial
   minimum running cost for hosted variants. Self-hosting eliminates
   the cost but reintroduces the operational surface.

The reverse migration path — Postgres-with-pgvector to a dedicated
vector store — remains open if corpus size ever exceeds practical
HNSW limits inside PostgreSQL. We do not anticipate this within the
v1.4 milestone or the workshop paper's evaluation window.

## Docker image dependency

The `db` service was updated to use the `pgvector/pgvector:pg16`
image in plan 02 of this phase. The image is binary-compatible with
the prior `postgres:16` image at the data-volume level; the on-disk
format of the existing `pgdata` volume is preserved across the
image swap. The new image differs only in that the `vector`
extension's shared libraries and control files are present on the
filesystem, allowing `CREATE EXTENSION vector` to succeed
[CITED: hub.docker.com/r/pgvector/pgvector].

## References

- pgvector — https://github.com/pgvector/pgvector
  (accessed 2026-05-13).
- pgvector Docker images — https://hub.docker.com/r/pgvector/pgvector
  (accessed 2026-05-13).
- Malkov, Y. A., & Yashunin, D. A. (2018). "Efficient and robust
  approximate nearest neighbor search using Hierarchical Navigable
  Small World graphs." *IEEE TPAMI*. arXiv:1603.09320.
- PostgreSQL 16 documentation, `CREATE INDEX` and operator classes —
  https://www.postgresql.org/docs/16/ (accessed 2026-05-13).
- dbi-services, "pgvector: a guide for DBA — Part 2: Indexes"
  (March 2026) — https://www.dbi-services.com/blog/pgvector-2026/.
