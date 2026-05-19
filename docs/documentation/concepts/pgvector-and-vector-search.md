# pgvector and vector search — reference

Operational reference for the pgvector extension and the vector
search pipeline. Optimized for lookup, not learning. For the
"why does this exist" lecture, see
`docs/learning/concepts/pgvector-and-vector-search.md`.

## TL;DR

- pgvector adds a `vector(N)` column type and three distance
  operators (`<->` L2, `<=>` cosine, `<#>` inner product) to
  Postgres.
- Build an ANN index (HNSW or IVFFlat) to make `ORDER BY embedding
  <=> :q LIMIT k` queries millisecond-fast instead of
  second-slow.
- HNSW is the default. `m`, `ef_construction`, `ef_search` are the
  three knobs.
- In this codebase: `vector(1024)` on `corpus_chunks.embedding`,
  cosine, HNSW with `m=16, ef_construction=64`, built lazily via
  the `python -m app.corpus.ingest --build-index` CLI.

## API surface

### Extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Idempotent. Requires superuser by default. Once installed,
`vector(N)` is a usable column type.

### Column type

```sql
CREATE TABLE corpus_chunks (
    id uuid PRIMARY KEY,
    embedding vector(1024) NOT NULL
);
```

`N` is fixed at column creation. Changing N requires a column
migration (add new column, backfill, swap, drop).

### Distance operators

| Operator | Meaning | Returns |
|---|---|---|
| `<->` | L2 (Euclidean) distance | smaller = closer |
| `<=>` | Cosine distance (1 - cosine_similarity) | smaller = closer |
| `<#>` | Negative inner product | smaller = closer |

All three return a numeric scalar. They are used in `ORDER BY` and
can also appear in `SELECT` clauses to expose the score:

```sql
SELECT id, embedding <=> :q AS score
FROM corpus_chunks
ORDER BY score
LIMIT 10;
```

### Index types

**HNSW** — graph-based, fast queries, slow build, high memory.

```sql
CREATE INDEX ix_corpus_chunks_embedding_hnsw
ON corpus_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

| Parameter | Default | Range | Effect |
|---|---|---|---|
| `m` | 16 | 2-100 | Graph degree. Higher = better recall, more memory |
| `ef_construction` | 64 | 4-1000 | Build-time candidate list. Higher = better index, slower build |
| `ef_search` (session) | 40 | 1-1000 | Query-time candidate list. Higher = better recall, slower query |

`ef_search` is set per session/transaction:

```sql
SET LOCAL hnsw.ef_search = 200;
```

**IVFFlat** — cluster-based, fast build, lower recall, needs
training data.

```sql
CREATE INDEX ix_corpus_chunks_embedding_ivfflat
ON corpus_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

| Parameter | Default | Rule of thumb | Effect |
|---|---|---|---|
| `lists` | 100 | `sqrt(rows)` for <1M, `rows/1000` for >1M | Number of k-means centroids |
| `probes` (session) | 1 | start at `sqrt(lists)` | Centroids scanned per query |

### Operator classes

The index needs to know which distance metric it's optimizing
for. Pick the operator class to match your query operator.

| Operator class | Pairs with operator |
|---|---|
| `vector_l2_ops` | `<->` |
| `vector_cosine_ops` | `<=>` |
| `vector_ip_ops` | `<#>` |

A single column can have multiple indexes, one per operator
class, if you need both metrics. Most codebases don't.

### Python — SQLAlchemy adapter

```python
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

class CorpusChunk(Base):
    __tablename__ = "corpus_chunks"
    id = sa.Column(sa.UUID, primary_key=True)
    embedding = sa.Column(Vector(1024), nullable=False)
```

The `Vector` type accepts `list[float]` and `numpy.ndarray` on
insert. The psycopg2 / psycopg3 codec handles serialization.

Inserts via raw SQL still work — pgvector accepts the
`'[0.1, 0.2, ...]'` string literal:

```python
session.execute(
    text("INSERT INTO corpus_chunks (embedding) VALUES (:emb)"),
    {"emb": [0.1, 0.2, ...]},  # list[float], not str
)
```

## Mental model

Three layers, top to bottom:

```
                  application
                      |
                      v
    +------------------------------------+
    |   embedding model (Jina / BGE)     |
    |   text -> 1024-d float vector      |
    +------------------------------------+
                      |
                      v
    +------------------------------------+
    |   pgvector column vector(1024)     |
    |   stored alongside row data        |
    +------------------------------------+
                      |
                      v
    +------------------------------------+
    |   HNSW index on (embedding)        |
    |   ORDER BY <=> :q LIMIT k          |
    +------------------------------------+
```

Each layer has its own failure mode and its own tuning surface.

- Embedding layer fails by drifting (wrong model, wrong
  normalization). Symptom: relevant chunk exists but never ranks.
- Storage layer fails by mismatch (dim wrong, provider mixed).
  Symptom: insert error or nonsense ranking across providers.
- Index layer fails by missing or stale stats. Symptom: query
  latency spikes; `EXPLAIN` shows `Seq Scan`.

The query path looks like this, top to bottom:

1. App computes the query embedding using the *same model* as the
   stored embeddings.
2. App issues `SELECT ... ORDER BY embedding <=> :q LIMIT k`.
3. Planner consults pg_statistics and the index catalog. If the
   table is big enough and the operator matches, it picks the
   HNSW Index Scan plan.
4. HNSW walks layer-by-layer to find approximate top-k.
5. Results returned to app, joined with `corpus_documents` to
   recover source path / offsets.

## Usage in this codebase

### Files

- `backend/alembic/versions/0019_enable_pgvector_corpus_tables.py` —
  enables extension, creates `ingestion_runs`, `corpus_documents`,
  `corpus_chunks`. Does **not** create the HNSW index.
- `backend/app/corpus/walker.py` — allow-list file walker.
- `backend/app/corpus/chunker.py` — recursive char splitter,
  `CHUNK_SIZE=1024`, `CHUNK_OVERLAP=128`.
- `backend/app/corpus/embeddings.py` — `JinaEmbeddingProvider` and
  `LocalBgeEmbeddingProvider` behind a shared `Protocol`. Locked
  to `EMBEDDING_DIM = 1024`.
- `backend/app/corpus/ingest.py` — `run_ingestion()` orchestrates
  walk + chunk + embed + upsert. `build_hnsw_index()` creates the
  index idempotently.
- `backend/app/corpus/__main__.py` — argparse CLI. Entry point:
  `python -m app.corpus.ingest [--commit | --dry-run | --build-index]`.
- `backend/tests/test_corpus_hnsw_index.py` — proves planner picks
  the index after a 20-doc ingest.

### Schema shape

```
ingestion_runs (id, status, started_at, completed_at,
                files_scanned, chunks_emitted, ...)
   ^
   | FK (RESTRICT)
   |
corpus_documents (id, source_path, content_sha256, ingestion_run_id)
   ^
   | FK (CASCADE)
   |
corpus_chunks (id, document_id, chunk_index,
               content, char_start, char_end,
               embedding vector(1024),
               embedding_model, embedding_provider, ...)
```

Idempotency is on `corpus_documents (source_path, content_sha256)`
via a unique constraint. Re-running ingest with no source changes
is a no-op.

### How a query looks

There is no query path landed yet — Phase 31 ships ingestion;
Phase 32 ships retrieval. The shape will be:

```sql
SELECT
    c.id,
    c.content,
    c.char_start,
    c.char_end,
    d.source_path,
    d.title,
    c.embedding <=> :query_vec AS distance
FROM corpus_chunks c
JOIN corpus_documents d ON d.id = c.document_id
WHERE c.embedding_provider = :provider  -- never mix providers
ORDER BY c.embedding <=> :query_vec
LIMIT 10;
```

The `WHERE embedding_provider = ?` clause is structural — without
it, a corpus that contains both Jina and BGE vectors would return
nonsense (cosine is meaningless across the pad-to-1024 boundary).

## Operational concerns

### Index build cost

HNSW builds are CPU-bound and single-backend on pgvector < 0.6.
Empirically: ~1k vectors/sec on a modern x86 core. For 100k chunks
expect a 90-second build. For 10M chunks expect a 3-hour build.

`CREATE INDEX CONCURRENTLY` lets writes continue during the build
but takes longer overall and requires twice the work (Postgres
runs two passes).

Best practice: bulk insert all vectors first, then create the
index. The ingest pipeline here separates the two phases on
purpose — `python -m app.corpus.ingest --commit` writes data,
`python -m app.corpus.ingest --build-index` creates the index.

### Memory

HNSW lives in shared_buffers + OS cache. Memory footprint is
roughly `n_rows * m * 8 bytes` for graph pointers plus `n_rows *
dim * 4 bytes` for the float32 vectors.

At `m=16, dim=1024, n=100k`: ~12.8 MB graph + ~400 MB vectors =
~413 MB. At `n=10M`: ~41 GB. If the index doesn't fit in RAM,
query latency degrades sharply.

### Bulk insert performance

Inserting into a table with an HNSW index is 10-100x slower than
inserting into an unindexed table, because each insert traverses
and updates the graph. For initial loads:

1. Create the table without an index.
2. `INSERT` / `COPY` all rows.
3. `CREATE INDEX`.
4. `ANALYZE` so the planner sees the new statistics.

### Statistics

Postgres uses pg_statistics to estimate plan costs. After bulk
load, run `ANALYZE corpus_chunks`. Without it the planner thinks
the table is empty and may pick seq scan instead of HNSW even
when the index exists.

`ANALYZE` cannot run inside a transaction block. The
`build_hnsw_index` function in `backend/app/corpus/ingest.py`
issues an explicit `COMMIT` before `ANALYZE`:

```python
session.execute(text("..."))
session.commit()
session.execute(text("COMMIT"))   # break out of any active txn
session.execute(text("ANALYZE corpus_chunks"))
```

### Tuning `ef_search` at query time

```sql
BEGIN;
SET LOCAL hnsw.ef_search = 200;
SELECT id FROM corpus_chunks
ORDER BY embedding <=> :q LIMIT 10;
COMMIT;
```

`SET LOCAL` scopes the change to the transaction. The right value
is empirical — start at the default 40, raise it until recall@10
plateaus on your eval set.

### Provider isolation

`corpus_chunks.embedding_provider` tags each row. Queries must
filter on it because the cosine distance between a Jina v3 vector
and a pad-to-1024 BGE vector is not meaningful. The HNSW index
ignores `embedding_provider`, so a provider-filtered query may
over-fetch and then filter — for two providers in a small corpus
this is fine. For a multi-tenant production system you'd build
separate indexes per provider.

### Backup and restore

pgvector vectors are stored as ordinary binary columns and survive
`pg_dump` / `pg_restore` with no special handling. The catch is
that the destination must have the extension installed — `CREATE
EXTENSION vector` must run before restore.

### Monitoring

Three signals to watch:

- **Query latency p95/p99** on the vector path. Spike = index is
  missing, stale stats, or `ef_search` too high.
- **Index size** vs table size. The HNSW index can be larger than
  the table itself. Track with `pg_relation_size`.
- **Recall@k** on a held-out eval set, run nightly. The whole
  point of vector search is retrieval quality — without an eval
  loop you cannot tell whether a tuning change helped or hurt.

## Glossary

**ANN** — Approximate Nearest Neighbour. The class of indexes
(HNSW, IVFFlat, PQ, ScaNN) that trade exact correctness for speed
on nearest-neighbour search.

**Chunk** — One unit of text that gets embedded. In this codebase
a chunk is a 1024-char slice with 128-char overlap (see
`backend/app/corpus/chunker.py`).

**Cosine similarity** — `(a · b) / (|a| |b|)`. Ranges from -1 to
1. For unit-norm vectors equals the dot product.

**Cosine distance** — `1 - cosine_similarity`. Ranges from 0 to 2.
The `<=>` operator returns this.

**Dimension (dim)** — The length of a vector. Fixed at column
creation in pgvector. Locked to 1024 in this codebase.

**Embedding** — A fixed-length numeric vector that represents the
meaning of an input in continuous space.

**`ef_construction`** — HNSW build-time candidate list size.
Higher = better index quality, slower build.

**`ef_search`** — HNSW query-time candidate list size. Higher =
better recall, slower query. Tunable per session.

**HNSW** — Hierarchical Navigable Small World. Multi-layer graph
index. Default ANN index in pgvector.

**Hybrid search** — Combining a sparse retriever (BM25 / tsvector)
with a dense retriever (vector). The two methods catch different
failure modes — sparse for exact terms, dense for semantic
similarity.

**Inner product** — Dot product, `a · b`. The `<#>` operator
returns the *negative* inner product so smaller-is-closer like
the other operators.

**IVFFlat** — Inverted File with Flat compression. Cluster-based
ANN index. Cheaper builds than HNSW, lower recall.

**L2 distance** — Euclidean distance, `sqrt(sum((a_i - b_i)^2))`.
The `<->` operator returns this.

**`m`** — HNSW graph degree. Number of neighbours each node has
in the bottom layer. Default 16.

**Normalization** — Scaling a vector to unit length (`v / |v|`).
Required for L2 to give the same ranking as cosine.

**Operator class** — In Postgres, the binding between an index
type and a distance metric. `vector_cosine_ops` is the operator
class for cosine-indexed HNSW.

**pgvector** — The Postgres extension that adds vector types,
distance operators, and ANN indexes.

**Recall@k** — Fraction of the true top-k results that an ANN
index returns. The headline metric for index quality.

**Recursive character splitter** — A chunking algorithm that
tries coarse separators first (paragraph), falls back to finer
ones (sentence, word), and finally to character-level. Used in
`backend/app/corpus/chunker.py`.

**RRF (Reciprocal Rank Fusion)** — A way to merge ranked lists
from multiple retrievers. The standard hybrid-search merging
method.

**`vector(N)`** — pgvector column type for an N-dimensional
float32 vector.
