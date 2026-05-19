# pgvector and vector search

This is an interview-prep lecture. It is not a tutorial on a specific
library. It is the mental model you need to walk into an
infra/backend interview and explain how a "semantic search" or
"retrieval-augmented generation" feature actually works under the
hood, where the costs hide, and what knobs you turn when the recall
graph dips.

The lecture is organized around the journey of a single 1024-dim
float vector: how it gets into Postgres, how it gets compared to
other vectors quickly, and how the comparison can go subtly wrong.

---

## Why this matters

Vector search shows up in three interview contexts:

1. **System design** — "design semantic search over our help docs",
   "design a RAG pipeline for an internal knowledge base", "how
   would you find duplicate support tickets".
2. **Backend / infra** — "we want to add embeddings to Postgres,
   what changes operationally", "should we use Pinecone or pgvector",
   "how do you index a billion vectors".
3. **ML-adjacent** — "explain cosine similarity vs L2", "why HNSW",
   "what's a good chunk size".

Most interviewers don't expect you to derive HNSW from scratch. They
expect you to know:

- Which **distance metric** matches which **embedding model**.
- Why an **approximate** nearest-neighbour index exists at all.
- Which **knobs trade recall for latency**, and in which direction.
- How **chunking** upstream of the vector affects retrieval
  downstream.
- Why you would or would not put vectors in Postgres vs a dedicated
  store.

The last bullet is where pgvector lives.

---

## The design choice

### Vector-in-Postgres vs dedicated vector DB

You have four shapes of solution:

| Shape | Examples | Why pick it |
|---|---|---|
| Vectors in your existing OLTP DB | pgvector, pg_embedding | One backup, one connection pool, transactional joins |
| Dedicated managed vector DB | Pinecone, Weaviate Cloud | No ops, scale-out, hybrid search built in |
| Self-hosted vector store | Qdrant, Milvus, Weaviate, Vespa | Tunable, cheaper at scale, more index types |
| Library-on-disk | FAISS, Annoy, ScaNN | Embedded, no server, no transactions |

The pgvector pitch is simple: if you already run Postgres, putting
vectors *next to* the rows they describe collapses your stack. You
get:

- **Transactional inserts.** The row and its embedding land in the
  same `BEGIN ... COMMIT`. No "row exists but embedding is missing"
  state. No two-phase write across two systems.
- **Joins.** You can `JOIN corpus_chunks` to `corpus_documents` to
  `users` in one SQL statement. A dedicated vector DB makes you
  carry foreign-key-ish IDs back into Postgres in app code.
- **One operational surface.** One backup, one HA story, one auth
  story, one set of dashboards.

The trade-off is real:

- **Index build time** dominates large corpora. Postgres does HNSW
  builds in a single backend (parallel build landed in pgvector 0.6
  but is still slower than a dedicated engine).
- **Hot path latency** on 100M+ vectors is consistently faster on
  Qdrant / Milvus, which are designed around the index, not around
  MVCC.
- **Filter-then-search** ("WHERE tenant_id = ? ORDER BY embedding
  <=> ? LIMIT 10") interacts poorly with HNSW. Postgres often falls
  back to scanning the filtered set instead of using the index. A
  dedicated DB with payload-aware indexes handles this better.

For interview purposes, the answer is almost always: **start with
pgvector**. Move off it when you can quote a real number — index
build pinning a worker for hours, p99 over budget, fan-out joins
killing the planner. "Move off pgvector when you outgrow it" is a
better answer than "use Pinecone because it's purpose-built".

In this codebase the decision was made explicitly. See the Phase 31
research note at
`/Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/31-corpus-pgvector-ingestion/`
— the corpus will never exceed ~10k chunks, so pgvector wins on
"one less moving part".

### Distance metric: cosine vs L2 vs inner product

A vector is a point in N-dimensional space. To search, you need a
notion of "closer". pgvector ships three operators:

| Operator | Metric | When to use |
|---|---|---|
| `<->` | Euclidean (L2) | Embeddings that are not normalized; spatial data |
| `<=>` | Cosine distance | The default for normalized text embeddings (Jina, OpenAI, BGE) |
| `<#>` | Negative inner product | Normalized vectors where you trust dot-product semantics |

The rule for text embeddings: **use the metric the model was trained
with**. Almost every modern text embedding model is trained with
cosine similarity and outputs unit-norm vectors. If you mix metrics —
say, train on cosine and search with L2 — your top-K will be
plausible but subtly wrong, and your eval graph will sag in a way
that's hard to debug.

For unit-norm vectors, cosine and inner product give the same
ranking (with a sign flip). L2 also gives the same ranking on
unit-norm vectors, *but* only if you remember to normalize. Most
real bugs in this area trace back to "we forgot to normalize and
used L2".

### Why an index at all? — exact vs approximate

The naive query is:

```sql
SELECT id
FROM corpus_chunks
ORDER BY embedding <=> :query_vector
LIMIT 10;
```

Without an index this is O(N · D) per query — load every row, do a
dot product against a 1024-d vector, sort, return top 10. At 10k
rows this is fine. At 10M rows it is a sequential scan that pegs a
CPU and runs in seconds.

The approximate nearest neighbour (ANN) index trades a small amount
of **recall** (do we actually return the true top-10?) for a large
amount of **latency** (milliseconds instead of seconds).

pgvector ships two ANN index types:

- **HNSW** — Hierarchical Navigable Small World graph. Fast queries,
  high recall, slow to build, memory-hungry.
- **IVFFlat** — Inverted File with Flat compression. Cheaper build,
  worse recall, requires a "training" set to learn cluster
  centroids.

The default for new pgvector deployments is HNSW. IVFFlat is the
right call only when build time matters more than query latency
(batch pipelines, hourly rebuilds).

---

## How it works under the hood

### HNSW — the skip-list of nearest-neighbour graphs

HNSW is the index you need to be able to describe in 60 seconds.

Picture a multi-layer graph. The bottom layer is a graph of *every*
vector in your dataset, where each vector is connected to its
approximate `m` nearest neighbours. The layer above is a sparser
graph — a sample of those vectors, again connected to their nearest
neighbours within that layer. The layer above that is sparser still.
The top layer might have only a handful of points.

A query starts at the top, finds the closest point in that sparse
layer (cheap, few comparisons), then **drops to the next layer** and
greedily walks toward the query vector. It descends layer-by-layer,
the search getting finer-grained each time. At the bottom layer it
walks the dense graph until no neighbour is closer than the current
point.

Two parameters control the trade-off:

- **`m`** — degree of the graph (default 16). Higher `m` = denser
  graph = better recall = more memory.
- **`ef_construction`** — size of the candidate list while *building*
  the index (default 64). Higher = better index quality = much
  slower build.

And one parameter at query time:

- **`ef_search`** — size of the candidate list while *querying*
  (default 40). Higher = better recall = higher latency.

Typical recall curve: at `m=16, ef_search=40` you get ~90% recall@10
on most text-embedding corpora. Crank `ef_search` to 200 and you'll
push past 99%, paying maybe 3-5x query latency.

The skip-list intuition is load-bearing here. Without the upper
layers, HNSW would just be a bottom-up greedy walk, and you'd often
get stuck in a local minimum. The upper layers let you "teleport"
toward the right neighbourhood before refining.

### IVFFlat — inverted file with centroids

IVFFlat clusters your vectors into `lists` (k-means) at build time.
A query computes the query's distance to every centroid, picks the
nearest `probes` clusters, and does an exact scan within those
clusters.

Two knobs:

- **`lists`** — number of clusters. Rule of thumb:
  `sqrt(num_rows)`.
- **`probes`** — clusters scanned per query. Higher = better recall,
  higher latency.

IVFFlat needs a *training set* — pgvector picks centroids by
sampling existing rows, which means you must build the index *after*
you have a representative population of vectors, not before. If you
build it empty and add rows later, the centroids drift and recall
collapses.

### How the planner uses the index

This is the part that trips most engineers. Just because you
created an index doesn't mean Postgres uses it.

```sql
EXPLAIN
SELECT id FROM corpus_chunks
ORDER BY embedding <=> :q
LIMIT 5;
```

The planner uses the HNSW index when:

1. The `ORDER BY` uses the **exact operator** the index was built
   for. `<=>` for `vector_cosine_ops`, `<->` for `vector_l2_ops`.
2. The `ORDER BY` clause is just the operator — wrapping it
   (`ORDER BY 1 + (embedding <=> :q)`) defeats the index.
3. There's a `LIMIT`. Without it the planner has to materialize all
   rows anyway.
4. The **table is big enough** that the cost-model thinks the index
   is worth it. On a 20-row table, Postgres will sequentially scan
   regardless.

Point 4 is the one that bites in tests. See
`/Users/andysubramanian/uni-volunteer-scheduler/backend/tests/test_corpus_hnsw_index.py`
— the fixture seeds 20 documents specifically so the planner picks
the index, and even then the test runs `SET enable_seqscan = off`
to nudge the planner.

A `WHERE` clause complicates this further. With `WHERE tenant_id =
:t ORDER BY embedding <=> :q LIMIT 10`, Postgres has two choices:

- Use the HNSW index, return more than 10 rows, filter, hope enough
  survive.
- Use a B-tree on `tenant_id`, scan that subset, sort by distance.

If the filter is selective, option 2 is correct. pgvector handles
this via the planner's standard cost estimation, which can be
fragile. Production systems either denormalize (one index per
tenant), or use a vector DB with native filtered ANN.

### Building the index

```sql
CREATE INDEX ix_corpus_chunks_embedding_hnsw
ON corpus_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

This statement holds an `ACCESS EXCLUSIVE` lock by default —
production builds use `CREATE INDEX CONCURRENTLY` to avoid blocking
writes. Build time scales roughly linearly with row count and is
single-backend on pgvector < 0.6.

A sane build flow looks like:

1. Bulk-insert all vectors first (with no index — inserts into a
    50k-row HNSW are 10-100x slower than appending to an unindexed
   table).
2. Create the index once at the end.
3. `ANALYZE` so pg_statistics learns the table is no longer empty.

This is exactly the flow in `backend/app/corpus/ingest.py` (see the
`build_hnsw_index` function — it's a separate CLI flag, not part of
the ingest loop).

### Embedding dimensionality

A vector in pgvector is `vector(N)` where N is fixed at table
creation. You cannot mix 384-dim and 1024-dim vectors in the same
column. Once you commit to N, changing it is a column migration:
add a new column, backfill, swap, drop.

This is why the codebase **pads** BGE's native 384-dim output to
1024 with trailing zeros — so it can co-exist with Jina's native
1024-dim output in the same `vector(1024)` column. The trade-off is
that cosine between a padded BGE vector and a Jina vector is
meaningless. The system explicitly tags each row with
`embedding_provider` and filters by it at query time. See
`backend/app/corpus/embeddings.py`.

---

## How this codebase uses it

The corpus pipeline lives entirely under
`/Users/andysubramanian/uni-volunteer-scheduler/backend/app/corpus/`.

### Schema

`backend/alembic/versions/0019_enable_pgvector_corpus_tables.py`
enables the extension and creates three tables:

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")

op.create_table(
    "corpus_chunks",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, ...),
    sa.Column("document_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("corpus_documents.id", ondelete="CASCADE")),
    sa.Column("chunk_index", sa.Integer(), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
    sa.Column("char_start", sa.Integer(), nullable=False),
    sa.Column("char_end", sa.Integer(), nullable=False),
    sa.Column("embedding", Vector(1024), nullable=False),
    sa.Column("embedding_model", sa.Text(), nullable=False),
    sa.Column("embedding_provider", sa.Text(), nullable=False),
    ...
)
```

Three things to notice:

- **`Vector(1024)`** locks the dimension. Phase 31 chose 1024 because
  it matches Jina v3's native output.
- **`embedding_provider`** is stored *per row*. This is what makes
  the dual-provider pad-to-1024 strategy survivable.
- **No HNSW index in the migration.** It's built separately by the
  ingest CLI (`--build-index`). Building HNSW pre-bulk-load is
  materially slower per row.

### Chunking

`backend/app/corpus/chunker.py` is a hand-rolled recursive
character splitter. Hard-coded constants:

```python
CHUNKER_VERSION = "v1-recursive-char-1024-128"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
SEPARATORS: list[str] = ["\n\n", "\n", ". ", " ", ""]
```

Recursive splitting tries the coarsest separator first (paragraph),
falls through to finer ones (line, sentence, word), and finally a
character-level fallback. This is the algorithm LangChain ships as
`RecursiveCharacterTextSplitter`. The codebase wrote its own to
remove the dependency.

### Embedding

`backend/app/corpus/embeddings.py` defines two providers behind a
`Protocol`:

```python
class EmbeddingProvider(Protocol):
    name: str
    model_id: str
    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]: ...
```

`JinaEmbeddingProvider` calls the Jina v3 HTTPS API. It raises
`RateLimitError` on HTTP 429 so the ingest orchestrator can fall
back to the local provider.

`LocalBgeEmbeddingProvider` loads `BAAI/bge-small-en-v1.5` via
`sentence-transformers`. Output is 384-dim, right-padded to 1024.

### Ingestion

`backend/app/corpus/ingest.py` (`run_ingestion`):

```python
docs = walk_sources(root=root)
...
for doc in docs:
    content_sha = _document_hash(doc.content)
    if _is_unchanged(session, doc, content_sha):
        counters["files_unchanged"] += 1
        continue
    chunks = chunk_text(doc.content)
    vecs, meta, used_provider = _embed_with_fallback(
        [c.content for c in chunks], provider, fallback_provider, notes
    )
    _persist_document(session, doc=doc, content_sha=content_sha,
                      chunks=chunks, vectors=vecs, ...)
    session.commit()
```

Idempotency lives in `(source_path, content_sha256)`. Re-running the
ingest with no source changes inserts zero rows.

### Index build

```python
def build_hnsw_index(*, session) -> None:
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw "
            "ON corpus_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )
    session.commit()
    session.execute(text("COMMIT"))
    session.execute(text("ANALYZE corpus_chunks"))
```

Three subtle bits:

- `IF NOT EXISTS` makes it safe to re-run.
- `vector_cosine_ops` pairs with the `<=>` operator at query time.
- `ANALYZE` cannot run inside a transaction block — hence the
  explicit `COMMIT` between the create-index and the analyze.

### Verifying index usage

`backend/tests/test_corpus_hnsw_index.py` proves the planner picks
the index:

```python
plan_rows = corpus_db_session.execute(
    text("""
        EXPLAIN SELECT id FROM corpus_chunks
        ORDER BY embedding <=> (SELECT embedding FROM corpus_chunks LIMIT 1)
        LIMIT 5
    """)
).all()
plan_text = "\n".join(row[0] for row in plan_rows)
assert "ix_corpus_chunks_embedding_hnsw" in plan_text
```

The fixture seeds 20 documents and sets `enable_seqscan = off`
because Postgres prefers a seq scan on small tables.

---

## Common pitfalls

**1. Forgetting to create the HNSW index.**

The migration creates `corpus_chunks` with `vector(1024)` but no
index. The first ingest run inserts 5000 chunks; queries are fast
because the table fits in cache. Six months later the corpus is
500k chunks and p99 spikes to 4 seconds. Diagnosis: `EXPLAIN`
shows `Seq Scan`. Fix: `CREATE INDEX ... USING hnsw`.

This is exactly why this project gates the index behind an explicit
`--build-index` CLI flag instead of building it during ingest.

**2. Using the wrong distance operator.**

Index built with `vector_cosine_ops`, query uses `<->` (L2). The
planner cannot use the index — it scans every row.

Catch this with `EXPLAIN ANALYZE` in CI. If you ever see `Seq Scan
on corpus_chunks` in a vector query plan, it's a regression.

**3. `ef_search` too low for the recall you actually need.**

The default `ef_search = 40` gives you maybe 90% recall@10. If your
eval shows the right document is in the corpus but isn't retrieved,
your first move is `SET hnsw.ef_search = 100` and re-run. If recall
improves, your default was too low.

```sql
SET LOCAL hnsw.ef_search = 200;
SELECT id FROM corpus_chunks ORDER BY embedding <=> :q LIMIT 10;
```

`SET LOCAL` scopes the change to the current transaction.

**4. Embedding dimension mismatch.**

You upgrade from `text-embedding-ada-002` (1536-dim) to
`text-embedding-3-small` (1536-dim, different *space*). The column
accepts both because the dim matches, but cosine between old and
new vectors is garbage. The fix is the same shape as the pad-to-1024
trick: tag each row with the model, never compare across models,
backfill on rollover.

**5. Building the index before bulk load.**

You run the migration that creates `corpus_chunks` + the HNSW
index. You then bulk insert 100k chunks. Each insert maintains the
HNSW graph. The bulk load takes 4 hours instead of 4 minutes.

Fix: drop the index, bulk insert, recreate the index. Or skip the
index in the migration and build it after the first ingest.

**6. Forgetting to normalize.**

Some models (older ones, fine-tuned ones) don't return unit-norm
vectors. Cosine still works (it normalizes internally), but L2 will
give you nonsense rankings. If you don't know whether your model
normalizes, write a sanity check that asserts
`np.linalg.norm(vec) ≈ 1.0`.

**7. Hybrid search blind spots.**

Vector search loves *semantic similarity*. It hates *exact terms* —
identifiers, product SKUs, error codes. The fix is **hybrid
search**: run BM25 (Postgres `tsvector`) and vector search in
parallel, then merge the results with reciprocal rank fusion (RRF)
or a weighted score. A vector-only "search for SKU X-12-Q" will
return semantically related products instead of the exact one.

---

## Interview Q&A

**Q (junior): What is an embedding?**

A. A fixed-length numeric vector that represents the meaning of a
piece of text (or an image, or an audio clip) in a continuous
space. The training objective is that semantically similar inputs
land near each other in vector space.

**Q (junior): Why do we need a special index for vectors?**

A. Distance computation between two vectors is cheap, but you need
to compare against every row in your table to find the nearest
neighbours. With 10M rows × 1024 dims that's 10 billion floating
point ops per query — seconds, not milliseconds. ANN indexes like
HNSW trade a small amount of recall for orders-of-magnitude lower
latency by structuring the data so most rows can be skipped.

**Q (junior): What's the difference between cosine similarity, L2,
and inner product?**

A. Cosine is the angle between two vectors — it ignores magnitude.
L2 is the straight-line distance — it cares about magnitude. Inner
product is the raw dot product — for unit-norm vectors it ranks the
same as cosine. For normalized text embeddings, all three give the
same ranking. For non-normalized vectors, only cosine and inner
product are angle-aware.

**Q (mid): How would you build semantic search over our help docs?**

A. Four steps:

1. **Chunking.** Split each doc into 500-1500 char overlapping
   chunks at paragraph/sentence boundaries. Store start/end offsets
   so you can highlight in the UI.
2. **Embedding.** Run each chunk through a model
   (text-embedding-3-small, Jina v3, BGE). Store the vector
   alongside the chunk, the source doc, and the offsets.
3. **Indexing.** In pgvector, `CREATE INDEX USING hnsw (embedding
   vector_cosine_ops)`. For a few hundred thousand chunks, HNSW
   with `m=16, ef_construction=64` is fine.
4. **Querying.** Embed the user's query with the same model. `ORDER
   BY embedding <=> :query LIMIT 10`. Return chunks. If recall
   matters more than latency, hybrid with BM25 — Postgres can do
   both in one query via `tsvector` plus pgvector.

Pre-empt the "what if it's slow" follow-up: tune `ef_search` for
recall, partition by tenant for filter selectivity, switch to a
dedicated vector DB if you outgrow Postgres.

**Q (mid): What's chunk overlap and why does it matter?**

A. Adjacent chunks share `chunk_overlap` characters at the seam.
The reason is that retrieval works on chunks but understanding
needs context. If a key sentence happens to span the boundary
between chunks A and B, neither chunk contains the full thought
and neither will rank well. A 10-20% overlap (e.g. 128 chars on a
1024-char chunk) makes seam sentences appear in both chunks, so at
least one of them will surface the right context.

**Q (mid): HNSW vs IVFFlat — when do you pick which?**

A. HNSW by default. It has higher recall at the same latency, and
its `ef_search` knob lets you re-tune at query time without
rebuilding. IVFFlat wins when build time dominates — batch
pipelines that rebuild the index hourly, or when memory is tight
(IVFFlat is more compact than HNSW). IVFFlat also needs a
representative sample to learn its centroids, so it's a bad fit for
incrementally-growing data.

**Q (senior): How does the Postgres planner decide whether to use
the HNSW index?**

A. Three conditions: the ORDER BY uses the exact operator the index
supports (`<=>` for `vector_cosine_ops`), there's a LIMIT clause,
and the cost model thinks the index is cheaper than a seq scan. On
small tables the planner often picks seq scan even when the index
exists — pg_statistics shapes this decision, so an `ANALYZE` after
bulk load matters. Filtered queries (`WHERE x = ? ORDER BY embedding
<=> ? LIMIT k`) are the hardest case: Postgres may use a B-tree on
`x` and scan, or use HNSW and over-fetch then filter. Which one
wins depends on selectivity estimates.

**Q (senior): How do you debug "recall feels low"?**

A. Multi-step. First, check whether the right chunk is *in* the
corpus — the bug is often upstream in chunking. Second, run the
query with `SET enable_seqscan = off; SET hnsw.ef_search = 500` and
compare to the default. If recall jumps, the index parameters are
the issue. If recall doesn't jump, the embedding is wrong — wrong
model, wrong normalization, wrong distance metric. Third, evaluate
on a held-out labelled set with recall@k and MRR. Without numbers
you're guessing.

**Q (senior): When would you move off pgvector?**

A. Three triggers:

- **Scale.** Past ~10M vectors, pgvector's single-backend build and
  MVCC overhead start to hurt. Qdrant or Milvus rebuilds faster and
  serves queries faster at the same cost.
- **Filter selectivity.** If almost every query is "WHERE tenant_id
  = ? ORDER BY embedding <=> ? LIMIT k" and tenants vary in size by
  three orders of magnitude, the Postgres planner will pick the
  wrong plan often enough to matter. Vector DBs with payload-aware
  indexes (Qdrant, Weaviate) handle this natively.
- **Hybrid search at scale.** Postgres can do BM25 + vector, but
  combining them efficiently across millions of rows is painful.
  Vespa and Weaviate were built for this.

The honest answer in most interviews is: stay on pgvector until you
can quote one of those three with a real number.

---

## Further reading

- pgvector README — `github.com/pgvector/pgvector`. Specifically
  the "Indexing" section for HNSW and IVFFlat parameter ranges.
- Malkov & Yashunin, "Efficient and robust approximate nearest
  neighbor search using Hierarchical Navigable Small World graphs"
  (2016). The original HNSW paper. Read sections 3 and 4 — the
  rest is theoretical.
- Postgres planner docs — "Using EXPLAIN" and "Statistics Used by
  the Planner". Knowing how pg_statistics shapes plan choice is
  the difference between mid and senior on this topic.
- "ANN-Benchmarks" — `ann-benchmarks.com` runs HNSW, IVFFlat,
  ScaNN, FAISS, and others on standard datasets. The recall vs
  latency Pareto fronts there are the canonical reference.
- "Reciprocal Rank Fusion outperforms Condorcet and individual
  rank learning methods" (Cormack et al., 2009). The standard
  citation for hybrid search merging.
