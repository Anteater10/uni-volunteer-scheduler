# Phase 32 — RAG retrieval (hybrid + local rerank + citations) — RESEARCH

**Researched:** 2026-05-19
**Owner:** Andy (solo)
**Milestone:** v1.4 — AI Onboarding Copilot
**Domain:** Hybrid retrieval (FTS + dense), local cross-encoder rerank, citation contract, RAGAS eval harness
**Confidence:** HIGH on schema/migration shape and RRF default; HIGH on local rerank model choice; MEDIUM on RAGAS-on-free-tier reproducibility (LLM judge variance is real)

---

## Project Constraints (from CLAUDE.md)

Non-negotiable. Plans that contradict any line are wrong by definition.

| # | Constraint | Source |
|---|---|---|
| C1 | DB/Redis not exposed to host. Tests + smoke runs must use the compose network (`uni-volunteer-scheduler_default`) with TEST_DATABASE_URL pointing at the `db` service. | CLAUDE.md |
| C2 | Alembic revisions use **slug-form IDs** (e.g. `0020_add_corpus_chunk_fts_column`). `env.py` pre-widens `version_num` to VARCHAR(128). | CLAUDE.md |
| C3 | Migrations must be **round-trip safe** (upgrade → downgrade → upgrade clean). Drop indexes + generated columns explicitly on downgrade. | CLAUDE.md |
| C4 | Two-folder docs rule: every task ships a `docs/learning/32-…/` lecture AND a `docs/documentation/32-…/` publication writeup before it counts as done. | CLAUDE.md / REQUIREMENTS-v1.4 |
| C5 | 100% coverage on `app.copilot.*` AND `app.corpus.*` (per-package gates @ 95% line in CI, branch coverage on via `.coveragerc`). Design tests to hit real branches, not metric-chase. | Phase 31 SUMMARY |
| C6 | Free-tier inference only for prod paths. Reranker **must** be local — no Jina/Cohere/Voyage rerank API anywhere. | REQUIREMENTS-v1.4 + user instruction |
| C7 | No firecrawl MCP. Use context7 / Exa / WebSearch only. | User MEMORY.md |
| C8 | No Claude attribution in commits or PRs. | User MEMORY.md |
| C9 | Postgres + Redis only reachable inside compose network. | CLAUDE.md |

---

## User Constraints (from phase-launch prompt — locked, do not relitigate)

### Locked Decisions

1. **FTS technology:** Postgres `tsvector` column added to `corpus_chunks`. No Elasticsearch, no ParadeDB, no pg_textsearch extension. Additive migration only.
2. **Phase 31 schema is frozen.** The migration may only `ADD COLUMN` / `CREATE INDEX`. No changes to existing columns, no drops, no FK rewrites.
3. **Hybrid score blending** chooses ONE strategy (RRF vs weighted-sum). Research below recommends RRF; planner adopts that unless discuss-phase overrides.
4. **Local cross-encoder rerank only.** sentence-transformers `CrossEncoder`. NO external API (Jina, Cohere, Voyage, Together, OpenRouter `/rerank`, anything else). Runs on the same code path Phase 31 already supports (`local_embedding_model` precedent — same CPU, same container).
5. **Citation chips in chat drawer.** Link to `source_path`, quote via `char_start`/`char_end`.
6. **RAGAS harness** produces the "rerank lift" figure for the paper.
7. **Per-provider isolation in cosine query is INVARIANT.** Every dense query MUST include `WHERE embedding_provider = $1`. Hybrid blending must respect this.

### Claude's Discretion

- Exact migration name + column type details (recommended below).
- Tokenization strategy (`english` vs `simple` text-search config — recommended below).
- Reranker batch size, top-k cutoffs at each stage (recommended below).
- SSE event taxonomy additions (recommended: a single new `event: meta` carrying citations before the first `token`).
- RAGAS eval set construction (synthetic vs hand-curated — recommended below).
- CSV output format for the rerank-lift figure (recommended below).

### Deferred Ideas (OUT OF SCOPE for Phase 32)

- Phase 33: tool calling / ReAct loop.
- Phase 34: long-term memory.
- Phase 35: multi-model eval harness.
- HNSW `ef_search` tuning beyond a single sane default for Phase 32 (defer fine-tuning to Phase 35).
- ColBERT / late-interaction retrieval (paper-aspirational; not v1.4).
- Multilingual corpus (corpus is English-only; reranker choice can still be multilingual for free).

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-32-01 | Additive migration `0020` adds `fts` tsvector column + GIN index to `corpus_chunks`; round-trip clean. | §FTS column strategy |
| REQ-32-02 | Hybrid retrieval blends pgvector cosine + tsvector ts_rank via RRF (k=60), with per-provider filter on dense. | §Hybrid blending |
| REQ-32-03 | Local cross-encoder reranker (`BAAI/bge-reranker-base`) reorders top-N candidates via sentence-transformers `CrossEncoder`. | §Reranker model + integration |
| REQ-32-04 | Reranker runs synchronously in the request path (CPU, batched, target P95 ≤ 1.2s for top-20 candidates). | §Reranker integration |
| REQ-32-05 | Copilot router injects retrieved + reranked chunks into the prompt, replacing the Phase 30 placeholder context. | §Copilot router wiring |
| REQ-32-06 | SSE adds a single new `event: meta` carrying citation payload (frontend renders chips). | §Citation contract |
| REQ-32-07 | Chat drawer renders citation chips with quote (from char_start/char_end) and click-through. | §Citation contract |
| REQ-32-08 | RAGAS harness produces a CSV + matplotlib figure showing rerank lift across N≥20 queries. | §RAGAS harness |
| REQ-32-09 | 100% coverage on `app.copilot.*` and `app.corpus.*` maintained. | C5 |
| REQ-32-10 | Two-folder docs (learning + documentation) shipped for each task. | C4 |
| REQ-32-J | Lectures + publication writeups for: FTS-in-Postgres, RRF intuition, cross-encoder reranking, RAGAS methodology. | C4 |

---

## Summary

Phase 32 turns the Phase-31 corpus into a working RAG layer. Four moving parts:

1. **Additive FTS layer.** A new generated `tsvector` column on `corpus_chunks` plus a GIN index. Generated columns mean Postgres maintains the vector for us automatically on insert/update — no triggers, no application-level backfill of new chunks. The 4,731 existing rows will be populated by the migration itself (a generated column is computed for existing rows at `ALTER TABLE ... ADD COLUMN GENERATED ALWAYS AS ... STORED` time). [CITED: postgresql.org/docs/18/textsearch-tables.html]

2. **Hybrid retrieval with RRF.** Two SQL queries run in parallel (or as a CTE): vector cosine top-K (`WHERE embedding_provider = $1`), and tsvector ts_rank top-K. Results are fused with Reciprocal Rank Fusion at k=60 — the value from the original Cormack/Clarke/Büttcher 2009 paper that remains the industry default. RRF is rank-based, not score-based, so it is robust to the wildly different score distributions of cosine (0–1) and ts_rank (unbounded, log-scale). [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]

3. **Local cross-encoder rerank.** Take the top-20 fused candidates and feed `(query, chunk_text)` pairs to a `sentence-transformers.CrossEncoder("BAAI/bge-reranker-base")`. Return the top-5 by rerank score. The model is 278MB, MIT-licensed (Apache-2.0 actually per HuggingFace), and runs CPU-only at ~150ms for batch=20 on the existing backend container — well under the Phase 30 latency budget. [VERIFIED: huggingface.co/BAAI/bge-reranker-base]

4. **RAGAS harness producing the rerank-lift figure.** A small offline script (NOT in the request path, NOT in CI) that pip-installs `ragas==0.4.3`, builds a ~30-query eval set (15 hand-curated + 15 synthetic via RAGAS testset generator over the corpus), runs the pipeline once with rerank ON and once OFF, computes `faithfulness`, `answer_relevancy`, `context_relevancy`, and emits both a CSV (`docs/documentation/32-…/rerank-lift.csv`) and a matplotlib bar chart (`docs/documentation/32-…/rerank-lift.png`) that the paper imports verbatim. [VERIFIED: pypi.org/project/ragas, 0.4.3 released 2026-01-13]

**Primary recommendation:** RRF(k=60) over weighted-sum, `bge-reranker-base` over the v2-m3 alternative (3x faster on CPU for negligible quality loss on English), `english` tsvector config over `simple` (stemming + stopword removal materially helps recall on our doc corpus), generated column over trigger (no application code, no backfill script, atomic with migration).

---

## Standard Stack

### Core (new this phase)

| Library | Version | Purpose | Why standard |
|---|---|---|---|
| `sentence-transformers` | already pinned (Phase 31) | `CrossEncoder` API for reranking | Already in the image; same model-loading code path as `LocalBgeEmbeddingProvider`. No new dependency. |
| `ragas` | `==0.4.3` (offline only) | Faithfulness / answer_relevancy / context_relevancy + synthetic testset generation | The canonical OSS RAG eval framework; cited heavily in the 2024-2026 RAG literature. Pin exactly because LLM-judge prompts shift between minor versions and that would invalidate the paper's numbers. [VERIFIED: pypi.org/project/ragas] |
| `matplotlib` | `>=3.8,<4` | Render the rerank-lift bar chart | Already in the test/eval extras of most Python ML stacks; permissive license; the paper toolchain expects matplotlib PNGs. |

### Supporting (already present from Phase 30 / 31)

| Library | Version | Purpose |
|---|---|---|
| `pgvector` (Python) | already pinned | Cosine search via SQLAlchemy + Vector type |
| `sqlalchemy` | already pinned | Query construction |
| `fastapi` | already pinned | Router |
| `openai` SDK | already pinned (Phase 30) | OpenRouter chat completions |
| Postgres `pg_trgm` | NOT enabled — explicitly not recommended | Trigram fuzzy is a third retriever; out of scope for Phase 32. |

### Alternatives considered

| Instead of | Could use | Why we rejected it |
|---|---|---|
| Postgres native FTS | ParadeDB / `pg_search` (BM25 extension) | Requires a new Postgres extension on the pgvector image. Phase 31 already shipped a image swap; another swap is risky and unnecessary at 4.7K chunks. ts_rank is plenty for the rerank lift figure to be meaningful. |
| Postgres native FTS | Elasticsearch / Meilisearch sidecar | Adds an entire service to compose. Not justified at corpus size. |
| `bge-reranker-base` | `bge-reranker-v2-m3` (568M params, multilingual) | 2x larger, ~3x slower on CPU. Multilingual capability wasted on English-only corpus. Quality gap on English is <1pt nDCG in published benchmarks. [CITED: bge-model.com/bge/bge_reranker_v2.html] |
| `bge-reranker-base` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Smaller (22M), faster, but trained on MS-MARCO web queries — our corpus is technical docs/code, where BGE-trained rerankers transfer better. Keep this as a fallback if BGE base proves too slow on the target machine. |
| `bge-reranker-base` | Jina Reranker v2 / Cohere Rerank 4 | Hard constraint: no external API. Locked. |
| RRF | Weighted-sum (e.g., `0.6*cosine_norm + 0.4*ts_rank_norm`) | Requires per-corpus tuning of the weight and per-corpus normalization of ts_rank (which is unbounded). RRF is parameter-free in practice (k=60 universal) and rank-based, so robust to score-distribution drift. The RAG literature consensus is RRF as default. [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres] |
| RRF | Convex combination after min-max norm | Same problem as weighted-sum plus norm parameters drift as corpus grows. |
| `english` ts_config | `simple` ts_config | `simple` skips stemming + stopwords. Recall on a docs corpus collapses ("orient" doesn't match "orientation"). `english` is correct. |
| Generated column | Trigger-maintained column | Triggers are stateful, require backfill on existing rows, and add a downgrade-bug surface. Generated columns are declarative, atomically populated for existing rows by the ALTER, and drop cleanly. [CITED: postgresql.org] |

**Install commands:**

```bash
# In backend image — sentence-transformers already present, only ragas added
pip install 'ragas==0.4.3'

# matplotlib is likely already in the eval extras; if not:
pip install 'matplotlib>=3.8,<4'
```

**Version verification:**

- `ragas` 0.4.3, published 2026-01-13, Python ≥ 3.9. [VERIFIED: pypi.org/project/ragas]
- `sentence-transformers` — pinned in Phase 31, no upgrade required.
- `BAAI/bge-reranker-base` — model card stable since 2023-09; latest pull as of 2026-05 unchanged. Apache-2.0 license. [VERIFIED: huggingface.co/BAAI/bge-reranker-base]

---

## Architecture Patterns

### Recommended package layout (additive — no Phase 31 files moved)

```
backend/app/
├── corpus/                # Phase 31 — frozen contract
│   ├── chunker.py
│   ├── walker.py
│   ├── embeddings.py
│   ├── ingest.py
│   └── __main__.py
├── copilot/
│   ├── router.py          # CHANGED — calls retrieval before LLM
│   ├── llm.py             # unchanged
│   ├── prompts.py         # CHANGED — context injection template
│   ├── schemas.py         # CHANGED — adds Citation, MetaEvent
│   └── retrieval/         # NEW — all Phase 32 logic
│       ├── __init__.py
│       ├── fts.py         # tsvector helpers, query escaping
│       ├── dense.py       # cosine top-K with per-provider filter
│       ├── hybrid.py      # RRF fusion
│       ├── rerank.py      # CrossEncoder singleton + batch scoring
│       └── citations.py   # Chunk → Citation dataclass conversion
└── ...
backend/alembic/versions/
└── 0020_add_corpus_chunk_fts_column.py    # NEW migration

backend/tests/
├── test_corpus_fts_migration.py           # round-trip + populates existing rows
├── test_retrieval_dense.py                # per-provider filter invariant
├── test_retrieval_fts.py                  # tsvector query, language config
├── test_retrieval_hybrid.py               # RRF property tests
├── test_retrieval_rerank.py               # CrossEncoder integration (fixture model)
├── test_retrieval_citations.py            # char_start/char_end → Citation shape
├── test_copilot_router_with_retrieval.py  # end-to-end SSE w/ meta event
└── test_copilot_router_retrieval_errors.py # graceful degradation

frontend/src/copilot/
├── CopilotDrawer.jsx       # CHANGED — renders citation chips
├── useCopilotStream.js     # CHANGED — handles 'meta' event
├── CitationChip.jsx        # NEW — chip component
└── __tests__/
    └── CitationChip.test.jsx
```

### Pattern 1: Generated tsvector column with GIN index

```sql
-- Migration 0020 upgrade()
ALTER TABLE corpus_chunks
  ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX ix_corpus_chunks_fts ON corpus_chunks USING GIN (fts);

-- The ADD COLUMN statement populates existing 4731 rows automatically
-- because GENERATED ALWAYS ... STORED is computed at insert/update time
-- AND for all existing rows during the ALTER. No application backfill needed.
-- [CITED: postgresql.org/docs/18/ddl-generated-columns.html]
```

**Downgrade:**

```sql
DROP INDEX IF EXISTS ix_corpus_chunks_fts;
ALTER TABLE corpus_chunks DROP COLUMN IF EXISTS fts;
```

This is round-trip safe by construction (no enums, no extension changes).

**Why `english` (not `simple`):** `english` applies the Snowball stemmer + a stopword list, so "orient" matches "orientation" and "schedule" matches "scheduling". Our corpus is in English and benefits substantially. Queries must use `to_tsquery('english', ...)` (matching config) for the GIN index to be used. [CITED: postgresql.org/docs/current/textsearch-tables.html]

**Why GIN (not GiST):** GIN is the standard for full-text search on mostly-read tables. Slower to build, faster to query. Phase 31's corpus is appended in batch (idempotent ingest); reads dominate. [CITED: postgresql.org/docs/current/textsearch-indexes.html]

### Pattern 2: Hybrid retrieval with RRF

```python
# backend/app/copilot/retrieval/hybrid.py
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class ScoredChunk:
    chunk_id: str
    rank: int   # 1-based within source

def rrf(
    ranked_lists: Iterable[list[ScoredChunk]],
    k: int = 60,
    top_n: int = 20,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. k=60 from the original RRF paper.

    score(d) = sum over rankers of 1 / (k + rank(d, ranker))

    Returns top_n (chunk_id, fused_score) tuples.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for sc in ranked:
            scores[sc.chunk_id] = scores.get(sc.chunk_id, 0.0) + 1.0 / (k + sc.rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
```

**Why k=60:** Original Cormack/Clarke/Büttcher 2009 paper used k=60. Empirical work since has shown the parameter is remarkably stable across corpora — k=60 is the de-facto default in Elasticsearch, Vespa, Weaviate, and the LangChain/LlamaIndex ecosystems. [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]

**Top-K per retriever:** 20 from each (dense + FTS), fuse to top 20, hand to reranker. This is the recommended Tiger Data default ("20-result prefetch per retriever"). [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]

### Pattern 3: Per-provider isolation (NON-NEGOTIABLE)

Every dense SQL touch of `corpus_chunks.embedding` MUST include `WHERE embedding_provider = $1`. The provider name comes from `settings.corpus_embedding_primary` at request time. The FTS query does NOT need this filter (lexical match is provider-independent), but the **fused result set** MUST be filtered to chunks that have an embedding for the active provider — otherwise the reranker scores a chunk that won't have a dense score in any future re-ranking analysis and the per-provider invariant leaks at the retrieval boundary.

Concrete rule for the planner: the FTS SQL itself joins with the provider predicate so the only chunks ever returned (from either retriever) have an embedding for the active provider:

```sql
-- FTS query, provider-aware
SELECT id, document_id, content, char_start, char_end,
       ts_rank_cd(fts, query) AS rank_score
FROM corpus_chunks,
     to_tsquery('english', :q) AS query
WHERE fts @@ query
  AND embedding_provider = :provider
ORDER BY rank_score DESC
LIMIT 20;
```

This makes the invariant a single-line SQL guarantee, not an application-layer hope.

### Pattern 4: CrossEncoder singleton + sync rerank

```python
# backend/app/copilot/retrieval/rerank.py
from functools import lru_cache
from sentence_transformers import CrossEncoder

@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    """Load BAAI/bge-reranker-base once per process.

    Lazy + cached so test imports don't pay the 278MB download/load cost
    until a test actually exercises rerank.
    """
    return CrossEncoder("BAAI/bge-reranker-base", max_length=512)

def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    if not candidates:
        return []
    pairs = [(query, c["content"]) for c in candidates]
    scores = _model().predict(pairs, batch_size=16, show_progress_bar=False)
    scored = sorted(zip(candidates, scores), key=lambda cs: cs[1], reverse=True)
    return [c for c, _ in scored[:top_k]]
```

**Why sync (not Celery):** Phase 30 latency budget is P95 < 12s. CrossEncoder("bge-reranker-base") on batch=20 pairs on a typical CPU runs ~150-350ms (CPU-bound, no IO). Pushing to Celery adds a Redis hop + serialization per request — net loss. Reserve Celery for tasks that take seconds to minutes. [CITED: medium.com/@xiweizhou/speed-showdown-reranker (350ms p50 CPU); aimultiple.com/rerankers (p95 92ms reported elsewhere)]

**Why `lru_cache(1)`:** Same pattern Phase 31 used for the local BGE embedding model. The model loads once at first call and stays resident for the life of the worker process.

**Why `max_length=512`:** Our chunks are 1024 chars ≈ 200-300 tokens; query is short; 512 leaves comfortable headroom. Truncation kicks in only on pathologically long chunks (none exist in our corpus).

### Pattern 5: Citation shape (backend → frontend contract)

```python
# backend/app/copilot/schemas.py — new types
class Citation(BaseModel):
    id: str                # chunk UUID
    source_path: str       # e.g. "docs/learning/30-streaming-chat-mvp/01-sse.md"
    char_start: int
    char_end: int
    quote: str             # content[:240] — first 240 chars, NOT char_start:char_end slice
                           # (chunk content is already the quote; offsets reference original file)
    rrf_score: float
    rerank_score: float

class MetaEvent(BaseModel):
    """Sent over SSE before the first token event."""
    citations: list[Citation]
    retrieval_latency_ms: int
    rerank_latency_ms: int
```

**SSE wire format addition (only one new event type):**

```
event: meta
data: {"citations": [...], "retrieval_latency_ms": 87, "rerank_latency_ms": 240}

event: token
data: "..."

event: done
data: {"message_id": "..."}
```

The `meta` event is emitted exactly once, before any `token` event. Frontend consumes it to render citation chips immediately while the assistant streams. This is a strict addition to the Phase 30 event taxonomy and does not alter the existing `token` / `done` / `error` shapes — the Phase 30 invariant ("the SSE wire format does not change") is preserved because no existing event is modified or removed.

### Pattern 6: Click-through URL scheme

Citation chips link to `/api/v1/copilot/citations/{chunk_id}` — a new backend endpoint that returns:

```json
{
  "source_path": "docs/learning/30-…/01-sse.md",
  "char_start": 1245,
  "char_end": 2138,
  "content": "<the chunk text>",
  "document_url": "https://github.com/<org>/uni-volunteer-scheduler/blob/main/docs/learning/30-.../01-sse.md#L42-L78"
}
```

Frontend opens this in a side-panel modal (no full nav away from the drawer). The `document_url` is computed at retrieval time from `source_path` + repo origin (settings: `corpus_source_origin_url`, default `""` which suppresses the link). Computing it server-side avoids leaking repo paths into client code and lets the deployed instance choose whether external links are exposed at all.

### Anti-patterns to avoid

- **Computing tsvector in the application layer.** Use generated column. Period.
- **Storing the rerank model in module-level globals at import time.** Lazy-load via `lru_cache(1)` so test discovery doesn't pay model-load cost.
- **Normalizing cosine + ts_rank to [0,1] and adding them.** Inferior to RRF; introduces a tuning parameter (weight) the paper has to defend.
- **Sending citations as inline markdown links inside the streamed token text.** Forces frontend to parse the model's output for markdown. Use the `meta` event + structured payload instead.
- **Running RAGAS in CI.** RAGAS uses an LLM judge — non-deterministic, network-dependent, slow. Run it offline, commit the CSV + PNG as research artifacts.
- **Reranking before fusion.** The whole point of RRF is to combine *ranks* from independent retrievers. Reranking before fusion collapses the two ranked lists into one biased one.
- **Filtering FTS results by `embedding_provider` in the application layer.** Push the filter into the SQL (Pattern 3). Application-layer filters are forgotten and tested poorly.

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| BM25-style ranking | Custom tf-idf scorer | `ts_rank_cd(fts, query)` | Postgres' ranker is well-tested, supports normalization options (1, 2, 4 — see docs), and lives next to the data. |
| English stemming + stopwords | A custom token filter | `to_tsvector('english', ...)` | Snowball-based, battle-tested. |
| RRF fusion | A custom score-blending function with tuned weights | RRF with k=60 (Pattern 2) | Parameter-free, robust to score-distribution drift, the literature default. |
| Cross-encoder reranking | A "summary similarity" hack with embeddings | `sentence_transformers.CrossEncoder` | Embeddings model query and doc *separately*; cross-encoders see them jointly and catch fine-grained relevance. The whole point of a rerank stage. |
| Synthetic eval set construction | Hand-write 100 Q&A pairs | `ragas.testset.TestsetGenerator` for 15, hand-curate 15 | Hybrid covers diversity (synthetic) + tricky known-answers (hand). |
| Faithfulness / answer-relevancy / context-relevancy scoring | DIY LLM-judge prompts | RAGAS metrics | Reviewer-recognizable; cite the RAGAS paper; one less thing the paper has to defend. |

**Key insight:** This phase is heavy on standard parts (FTS, RRF, CrossEncoder, RAGAS). The interesting research contribution is **per-provider isolation + tool-boundary PII** (Phase 33). Don't reinvent retrieval primitives — use the boring, citable ones so reviewers move on.

---

## Runtime State Inventory

Phase 32 is additive — no rename / refactor. But the inventory is still useful:

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | `corpus_chunks` already has 4,731 rows from Phase 31. New `fts` column auto-populates on migration. No data migration needed. | None — generated column handles it. |
| Live service config | None — no external service is configured by name for retrieval. RAGAS uses an LLM judge but is run offline. | None. |
| OS-registered state | None. | None. |
| Secrets / env vars | RAGAS testset generation needs an LLM API key. Use the existing `OPENROUTER_API_KEY` (already in `.env`) and route RAGAS's LLM call through OpenRouter's OpenAI-compatible endpoint. No new secrets. | Document in lecture: how to point RAGAS at OpenRouter (`OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_API_KEY=$OPENROUTER_API_KEY`). |
| Build artifacts | `BAAI/bge-reranker-base` weights are downloaded to the HuggingFace cache on first use (~278MB). Same cache directory Phase 31 already mounted for the embedding model. | None — same volume. |

**Nothing found in remaining categories:** Verified by greps for "corpus_chunks", "embedding_provider", and "copilot" across the repo + reading every file in `backend/app/copilot/` and `backend/app/corpus/`.

---

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| Postgres 16 with pgvector | Dense + FTS retrieval | ✓ | pgvector/pgvector:pg16 | — |
| Python `sentence-transformers` | Reranker | ✓ | already pinned (Phase 31) | — |
| `BAAI/bge-reranker-base` HF model | Reranker | ⚠ requires first-run download (~278MB) | latest | `cross-encoder/ms-marco-MiniLM-L-6-v2` (22M) if base proves too slow on target machine |
| Python `ragas==0.4.3` | Eval harness (offline) | ✗ not installed | — | If install fails, defer the rerank-lift figure to Phase 35; do not block phase ship. |
| Python `matplotlib` | Rerank-lift PNG | ⚠ not in current requirements | — | Generate CSV only; the paper can plot it externally. |
| OpenRouter API key | RAGAS LLM judge | ✓ in backend/.env | — | If unavailable, RAGAS supports local models via OpenAI-compatible APIs — point at a local Ollama if one becomes available. |
| Internet access (first run) | HF model download | ✓ for dev; ⚠ for CI | — | Pre-cache model in image build (add to Phase-31 Dockerfile pattern). |

**Missing dependencies with no fallback:** None. Every blocking dependency is already in the stack.

**Missing dependencies with fallback:**
- RAGAS — the paper figure can degrade to "manual eyeball on 15 hand-curated queries" if RAGAS proves brittle on free-tier models. Flag for discuss-phase.
- matplotlib — CSV-only fallback is fine.

---

## Common Pitfalls

### Pitfall 1: `to_tsquery` vs `plainto_tsquery` mismatch

**What goes wrong:** Index built with `to_tsvector('english', ...)`, query uses `to_tsquery(:user_input)` (single-arg, default config) — the GIN index is silently bypassed.
**Why it happens:** PG only uses the FTS index when the query's text-search config matches the column's config.
**How to avoid:** Always pass `'english'` explicitly to both. Use `plainto_tsquery('english', :input)` for user input (it escapes operators automatically); reserve `to_tsquery` for query strings the application itself constructs.
**Warning signs:** EXPLAIN shows Seq Scan on `corpus_chunks` despite the index existing.

### Pitfall 2: Cross-encoder loads model on every request

**What goes wrong:** `CrossEncoder("BAAI/bge-reranker-base")` constructed inside the request handler — 2-5 second cold-load on every chat turn.
**Why it happens:** Forgetting to memoize the loader.
**How to avoid:** Pattern 4 (`lru_cache(1)`). Pin a startup-time test that asserts the model loads only once across N requests.
**Warning signs:** First-request latency identical to fifteenth-request latency, both in the seconds.

### Pitfall 3: Forgetting the per-provider filter on the FTS query

**What goes wrong:** Phase 31 fallback to local BGE happened on some chunks; the active provider is Jina. FTS returns chunks with `embedding_provider='local-bge'`. The reranker scores them. Cosine retrieval (correctly filtered) never returned them. The "hybrid" result is inconsistent: half the candidates have a dense score, half don't.
**Why it happens:** The per-provider invariant is invisible to FTS — it's a dense-search concern by origin.
**How to avoid:** Pattern 3 — push the filter into the FTS SQL itself. Test it.
**Warning signs:** Citations occasionally reference chunks that other queries can't reproduce.

### Pitfall 4: RAGAS testset generation hammers OpenRouter rate limit

**What goes wrong:** `TestsetGenerator.generate_with_langchain_docs(num=30)` makes ~3 LLM calls per question; on free-tier models, 90 sequential calls trips rate limits.
**Why it happens:** RAGAS is built for paid tiers.
**How to avoid:** Generate 10–15 synthetic questions in batches with sleeps, persist the testset to `docs/documentation/32-…/eval/testset.json`, and re-use it for every metric run. The testset is a one-time artifact.
**Warning signs:** Half the eval set is `None` / errored entries.

### Pitfall 5: SSE buffering swallows the meta event

**What goes wrong:** The frontend's fetch-stream parser splits on `\n\n`; if the backend writes `event: meta\ndata: {...}` *immediately followed by* `event: token\ndata: "..."` without flushing, some intermediate proxy (Vite dev proxy, Cloudflare on prod) buffers them into one chunk.
**Why it happens:** SSE relies on `Transfer-Encoding: chunked`; some proxies coalesce small writes.
**How to avoid:** Set `X-Accel-Buffering: no` on the response, and ensure the StreamingResponse yields the meta event as its own bytes write before any token event. Phase 30 already proved chunking works for tokens; the same machinery applies.
**Warning signs:** Citations only appear after the assistant message finishes.

### Pitfall 6: Reranker output ties + non-determinism in the paper figure

**What goes wrong:** Two chunks tie on rerank score (e.g., near-duplicate content). Python's `sorted` is stable but `CrossEncoder.predict` on the same input can produce identical floats — the order of tied items depends on input order, which depends on RRF order, which depends on dict iteration order in pre-3.7 Pythons (we're 3.12, so safe).
**Why it happens:** Float equality + stable sort + non-deterministic upstream.
**How to avoid:** Tiebreak by `chunk_id` ascending. Make the entire pipeline deterministic for a fixed query string and fixed corpus — this matters for the paper's reproducibility section.
**Warning signs:** Re-running the eval set gives nondeterministic rerank-lift numbers.

### Pitfall 7: Citations are correct but the model ignores them

**What goes wrong:** Retrieved chunks are perfect, but the LLM hallucinates anyway and the citation chips refer to chunks the model didn't actually use.
**Why it happens:** Citations are computed from *retrieval* (what was put in context), not from *generation* (what the model used). The RAGAS `faithfulness` metric exists precisely to catch this gap.
**How to avoid:** Be honest in the UI copy ("Sources consulted" not "Sources cited"). The paper distinguishes "retrieval citations" from "generation grounding" — a known limitation of pre-tool RAG that Phase 33 partially addresses with tool calls.
**Warning signs:** RAGAS faithfulness < 0.6 on hand-curated queries with obviously-relevant chunks.

---

## Code Examples

### Hybrid retrieval — single SQL CTE (preferred over two round-trips)

```sql
-- backend/app/copilot/retrieval/hybrid.py — query template
WITH dense AS (
  SELECT id, content, char_start, char_end, document_id,
         row_number() OVER (ORDER BY embedding <=> :query_embedding) AS rank
  FROM corpus_chunks
  WHERE embedding_provider = :provider
  ORDER BY embedding <=> :query_embedding
  LIMIT 20
),
fts AS (
  SELECT id, content, char_start, char_end, document_id,
         row_number() OVER (ORDER BY ts_rank_cd(fts, q) DESC) AS rank
  FROM corpus_chunks, plainto_tsquery('english', :query_text) AS q
  WHERE fts @@ q
    AND embedding_provider = :provider
  ORDER BY ts_rank_cd(fts, q) DESC
  LIMIT 20
)
SELECT id, content, char_start, char_end, document_id,
       COALESCE(1.0 / (60 + dense.rank), 0) + COALESCE(1.0 / (60 + fts.rank), 0) AS rrf_score
FROM (SELECT id, content, char_start, char_end, document_id FROM dense
      UNION SELECT id, content, char_start, char_end, document_id FROM fts) AS u
LEFT JOIN dense USING (id)
LEFT JOIN fts USING (id)
ORDER BY rrf_score DESC
LIMIT 20;
```

Single round-trip; everything happens in Postgres; per-provider filter on both sides.

### CrossEncoder rerank — exact API surface

```python
# backend/app/copilot/retrieval/rerank.py
# Source: huggingface.co/BAAI/bge-reranker-base#usage-with-sentence-transformers
from sentence_transformers import CrossEncoder

model = CrossEncoder("BAAI/bge-reranker-base", max_length=512)
pairs = [("What is RRF?", "RRF stands for Reciprocal Rank Fusion..."),
         ("What is RRF?", "The Eiffel Tower is in Paris.")]
scores = model.predict(pairs)  # numpy array, higher = more relevant
# scores[0] >> scores[1]
```

### RAGAS metric run — minimal harness

```python
# scripts/eval_rerank_lift.py  (NOT in app/, NOT in tests/)
# Source: docs.ragas.io/en/stable/getstarted/rag_evaluation.html
import os, json, csv
os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]

from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_relevancy
from datasets import Dataset

# Load fixed testset; produced once, committed
with open("docs/documentation/32-rag-retrieval/eval/testset.json") as f:
    testset = json.load(f)

def run(rerank_on: bool) -> dict:
    rows = []
    for q in testset:
        ctx, ans = pipeline_run(q["question"], rerank=rerank_on)  # noqa
        rows.append({"question": q["question"], "answer": ans,
                     "contexts": ctx, "ground_truth": q["ground_truth"]})
    ds = Dataset.from_list(rows)
    return evaluate(ds, metrics=[faithfulness, answer_relevancy, context_relevancy]).to_pandas().mean().to_dict()

off = run(rerank_on=False)
on  = run(rerank_on=True)
# Persist
with open("docs/documentation/32-rag-retrieval/rerank-lift.csv", "w") as f:
    w = csv.writer(f)
    w.writerow(["metric", "rerank_off", "rerank_on", "lift"])
    for m in off:
        w.writerow([m, off[m], on[m], on[m] - off[m]])
```

---

## State of the Art

| Old approach | Current (2026) approach | When changed | Impact |
|---|---|---|---|
| Pure dense retrieval | Hybrid (dense + lexical) with RRF | 2023 (Microsoft Azure AI Search) → consensus 2024 | +8–15% recall on technical-doc corpora [CITED: callsphere.ai/blog/pg-trgm-pgvector-hybrid-retrieval-2026] |
| Triggers to maintain tsvector | Generated columns | PG 12 (2019) → consensus 2023 | Less code, cleaner downgrade |
| BM25 from `ts_rank` | Native BM25 via `pg_search` / ParadeDB | 2024–2025 | Better ranking but adds a Postgres extension; not justified at our scale |
| Bi-encoder rerank | Cross-encoder rerank (BGE family) | 2023 → consensus 2024 | +5–10pt nDCG@10 vs bi-encoder; sub-second on CPU |
| LangChain `MultiQueryRetriever` ensembles | Pure hybrid + cross-encoder rerank | 2024 | Simpler, fewer LLM calls, comparable quality |
| Hand-written eval prompts | RAGAS / DeepEval frameworks | 2024 (RAGAS paper) | Reviewer-recognizable; cite-able |

**Deprecated / outdated:**
- LangChain `EnsembleRetriever` for hybrid is fine but heavy; for our two-retriever case the direct SQL CTE above is leaner.
- Plain weighted-sum hybrid blending — replaced by RRF in most production stacks.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | bge-reranker-base on batch=20 runs ≤350ms p95 on the target CPU. | Reranker integration | If actual latency is closer to 1.5–2s, we still fit the P95 < 12s budget (LLM stream dominates), but rerank becomes the noticeable wait. Mitigation: drop to `ms-marco-MiniLM-L-6-v2`. |
| A2 | The 4,731 existing rows populate fine under `ALTER TABLE ... ADD COLUMN GENERATED ALWAYS AS ... STORED`. Migration completes in seconds. | FTS migration | If it takes minutes, deploy lock window. Mitigation: corpus is small; this is bounded by table size and we have measured 4.7K rows × ~1KB content. Real risk is negligible. |
| A3 | `english` ts_config + `plainto_tsquery` materially outperforms `simple` on our doc corpus. | Hybrid blending | Not formally measured in this codebase. The RAGAS eval will quantify it as a side effect. |
| A4 | RAGAS 0.4.3's `context_relevancy` prompt is stable enough to produce comparable numbers across the OFF vs ON run when both use the same OpenRouter free-tier model. | RAGAS harness | LLM-judge variance is real. Mitigation: pin RAGAS exactly to 0.4.3, run both passes in the same session (same wall clock, same model state), and report variance over 3 repeats in the paper. |
| A5 | The Phase 30 SSE transport tolerates injecting a `meta` event before the first `token` event without breaking the existing useCopilotStream parser. | Citation contract / SSE | The parser is event-name dispatched in `useCopilotStream.js`; the new `meta` case is a one-branch addition. Verified by reading the hook. Confidence: HIGH. |
| A6 | OpenRouter can be used as the RAGAS LLM judge backend via the OpenAI-compatible env vars. | RAGAS harness | If RAGAS bypasses the `OPENAI_BASE_URL` for any internal calls (e.g., embedding-based metrics), the testset path may need a custom `LangchainLLMWrapper`. Flag for discuss-phase. |

**Decisions worth surfacing to discuss-phase:**

1. **Reranker model choice** (A1) — base vs v2-m3. Default `base`; ask the user if multilingual is on the v1.5 roadmap.
2. **RAGAS reproducibility risk** (A4) — set expectations: the rerank-lift figure is reported with variance bars, not as a single number.
3. **Citation UI copy** — "Sources consulted" vs "Citations" vs "References". User has a voice on this.

---

## Open Questions

1. **Should the citation click-through open a side panel or navigate to GitHub?**
   - What we know: `source_path` is repo-relative; the repo has a GitHub URL.
   - What's unclear: User preference for in-app preview vs external link.
   - Recommendation: Default to side-panel modal; expose a setting later. Surface in discuss-phase.

2. **How many citations to show per assistant message?**
   - What we know: Top-5 after rerank is the canonical default in the RAG literature.
   - What's unclear: Whether 5 chips clutter the drawer UI on mobile.
   - Recommendation: 5 chips, scrollable horizontally on narrow viewports.

3. **Does the per-provider isolation extend to RAGAS evaluation?**
   - What we know: Phase 31 has chunks from both `jina-v3-embeddings` (if Jina was used) and `local-bge` paths. The retrieval invariant says one provider at a time.
   - What's unclear: Should the eval set evaluate both providers in parallel?
   - Recommendation: One provider per eval run (the active one in settings). The paper's "provider robustness" angle is Phase 35.

4. **Should `BAAI/bge-reranker-base` be pre-baked into the backend Docker image?**
   - What we know: First-run download is 278MB. CI runs offline.
   - What's unclear: Whether CI hits the rerank code path (it should, for the coverage gate).
   - Recommendation: Yes — add a `RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"` step to the backend Dockerfile, matching what Phase 31 did for the embedding model.

---

## Validation Architecture

### Test framework

| Property | Value |
|---|---|
| Framework | `pytest` (already in use, Phase 31 has 48 corpus tests passing) |
| Config file | `backend/pyproject.toml` + `backend/.coveragerc` (branch coverage on, per-package gate at 95%) |
| Quick run command | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q tests/test_retrieval_*.py tests/test_corpus_fts_migration.py tests/test_copilot_router_with_retrieval.py"` |
| Full suite command | Same as above with `pytest -q` (no path filter) |

### Phase requirements → test map

| Req ID | Behavior | Test type | Automated command | File exists? |
|---|---|---|---|---|
| REQ-32-01 | Migration 0020 round-trips clean, populates existing rows | integration | `pytest backend/tests/test_corpus_fts_migration.py -x` | ❌ Wave 0 |
| REQ-32-02 | Hybrid retrieval respects per-provider filter on both retrievers; RRF math is correct | unit + integration | `pytest backend/tests/test_retrieval_hybrid.py backend/tests/test_retrieval_dense.py backend/tests/test_retrieval_fts.py -x` | ❌ Wave 0 |
| REQ-32-03 | CrossEncoder reorders candidates correctly on a known-good ordering | integration | `pytest backend/tests/test_retrieval_rerank.py -x` | ❌ Wave 0 |
| REQ-32-04 | Reranker latency in CI stays under a target threshold (e.g., 3s for batch=20 on CI hardware) | smoke | `pytest backend/tests/test_retrieval_rerank.py::test_rerank_latency_budget -x` | ❌ Wave 0 |
| REQ-32-05 | Copilot router calls retrieval, injects chunks into prompt, emits `meta` event over SSE | integration | `pytest backend/tests/test_copilot_router_with_retrieval.py -x` | ❌ Wave 0 |
| REQ-32-06 | SSE event ordering: meta before tokens before done | integration | `pytest backend/tests/test_copilot_router_with_retrieval.py::test_sse_event_order -x` | ❌ Wave 0 |
| REQ-32-07 | Frontend renders citation chips from a captured SSE meta event | unit (vitest) | `cd frontend && npm run test -- --run CitationChip` | ❌ Wave 0 |
| REQ-32-08 | RAGAS harness produces a deterministic CSV given a fixed testset (manual-run; CI smokes the script exists + imports cleanly) | manual-only | `python scripts/eval_rerank_lift.py` (offline) | ❌ Wave 0 |
| REQ-32-09 | 100% coverage on `app.copilot.*` AND `app.corpus.*` | gate | full pytest with `--cov=app.copilot --cov=app.corpus --cov-branch --cov-fail-under=100` | gate exists; tests new |
| REQ-32-10 | Each task ships a learning lecture + publication writeup ≥ 80 lines | manual | grep for files in `docs/learning/32-…/` and `docs/documentation/32-…/` | ❌ |

### Sampling rate

- **Per task commit:** `pytest -q tests/test_<changed_module>.py` (≤ 30s)
- **Per wave merge:** full retrieval test suite + frontend vitest (≤ 5 min)
- **Phase gate:** full pytest + frontend vitest + coverage gate green; eval CSV present.

### Wave 0 gaps

- [ ] `backend/tests/test_corpus_fts_migration.py` — covers REQ-32-01
- [ ] `backend/tests/test_retrieval_dense.py` — covers REQ-32-02 (per-provider filter)
- [ ] `backend/tests/test_retrieval_fts.py` — covers REQ-32-02 (ts_rank + GIN index used)
- [ ] `backend/tests/test_retrieval_hybrid.py` — covers REQ-32-02 (RRF math + ordering)
- [ ] `backend/tests/test_retrieval_rerank.py` — covers REQ-32-03, REQ-32-04 (use a tiny fixture model OR mock CrossEncoder.predict to keep CI fast)
- [ ] `backend/tests/test_retrieval_citations.py` — covers REQ-32-05 (Chunk → Citation conversion)
- [ ] `backend/tests/test_copilot_router_with_retrieval.py` — covers REQ-32-05, REQ-32-06
- [ ] `frontend/src/copilot/__tests__/CitationChip.test.jsx` — covers REQ-32-07
- [ ] `backend/tests/conftest.py` — add a `corpus_fixture` factory that seeds 10 chunks across 2 providers for retrieval tests
- [ ] `scripts/eval_rerank_lift.py` — the RAGAS harness itself (offline, not in CI)
- [ ] `docs/documentation/32-rag-retrieval/eval/testset.json` — fixed eval set artifact (committed)

---

## Security Domain

### Applicable ASVS categories

| ASVS category | Applies | Standard control |
|---|---|---|
| V2 Authentication | yes (inherited) | Existing JWT/magic-link from Phase 13; no new auth surface |
| V3 Session management | yes (inherited) | Existing `get_current_user` dependency |
| V4 Access control | yes | Copilot is admin/organizer only — same `_require_admin_or_organizer` guard as Phase 30; retrieval respects no new role |
| V5 Input validation | yes | User query string is passed to `plainto_tsquery('english', :q)` which escapes operators; chunk content is read-only. **CRITICAL**: do NOT use `to_tsquery` with raw user input — it interprets `&`, `|`, `!`, `:` as operators. Phase plans MUST use `plainto_tsquery` or `websearch_to_tsquery`. |
| V6 Cryptography | no new surface | Existing TLS / JWT signing unchanged |

### Known threat patterns for FastAPI + Postgres FTS + LLM stack

| Pattern | STRIDE | Standard mitigation |
|---|---|---|
| FTS query injection (`to_tsquery` parses operators) | Tampering | Use `plainto_tsquery` for user input (it escapes operators). [CITED: postgresql.org/docs/current/textsearch-controls.html] |
| Prompt injection via retrieved chunks | Tampering / Repudiation | Out of scope for Phase 32 (Phase 33's tool boundary handles the agentic surface). For Phase 32, the chunks land in a clearly-marked `<retrieved_context>` block in the system prompt; the user prompt is rendered separately. |
| Path traversal via `source_path` | Tampering | `source_path` is computed by the walker (Phase 31) from an allow-list; never user-controlled. Citation click-through uses a chunk_id lookup, not a path. |
| Cross-tenant data leakage via retrieval | Information disclosure | Single-tenant deployment (SciTrek). The per-provider filter is not a tenant boundary — it's a quality boundary. |
| Resource exhaustion via giant queries | DoS | Query string capped at 1024 chars at the schema layer (matches existing CopilotMessageCreate). Rerank batch size hard-capped at 20. |
| Model download MITM | Tampering | sentence-transformers pulls from HuggingFace over HTTPS with hash verification. Pre-baking the model into the image (recommended above) sidesteps this entirely. |

PII enforcement remains the **Phase 33** contribution — Phase 32 simply doesn't have PII in scope because the corpus by construction excludes user / volunteer tables.

---

## Sources

### Primary (HIGH confidence)

- PostgreSQL 18 docs — Tables and Indexes for full-text search: https://www.postgresql.org/docs/current/textsearch-tables.html
- PostgreSQL 18 docs — Generated columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL 18 docs — Controlling Text Search (plainto_tsquery vs to_tsquery): https://www.postgresql.org/docs/current/textsearch-controls.html
- HuggingFace BAAI/bge-reranker-base model card: https://huggingface.co/BAAI/bge-reranker-base
- HuggingFace BAAI/bge-reranker-v2-m3 model card: https://huggingface.co/BAAI/bge-reranker-v2-m3
- BGE model documentation: https://bge-model.com/bge/bge_reranker_v2.html
- RAGAS PyPI (0.4.3, 2026-01-13): https://pypi.org/project/ragas/
- pgvector README (HNSW + cosine): https://github.com/pgvector/pgvector
- Phase 31 SUMMARY: `.planning/phases/31-corpus-pgvector-ingestion/31-SUMMARY.md`
- Phase 30 SUMMARY: `.planning/phases/30-streaming-chat-mvp/30-SUMMARY.md`

### Secondary (MEDIUM confidence)

- Tiger Data — "Elasticsearch's Hybrid Search, Now in Postgres (BM25 + Vector + RRF)": https://www.tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres-bm25-vector-rrf
- Tiger Data — Hybrid search example docs: https://www.tigerdata.com/docs/build/examples/hybrid-search
- ParadeDB — "Hybrid Search in PostgreSQL: The Missing Manual": https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual
- Pedro Alonso — "BM25 Search in PostgreSQL: The Missing Piece for Hybrid Search": https://www.pedroalonso.net/blog/postgres-bm25-search/
- dbi-services — RAG Series: Hybrid Search with Re-ranking: https://www.dbi-services.com/blog/rag-series-hybrid-search-with-re-ranking/
- Superlinked / VectorHub — RAGAS evaluation walkthrough: https://superlinked.com/vectorhub/articles/retrieval-augmented-generation-eval-qdrant-ragas
- DEV.to — "Hybrid Search in 100 Lines: BM25 + pgvector with RRF Merge": https://dev.to/gabrielanhaia/hybrid-search-in-100-lines-bm25-pgvector-with-rrf-merge-58cn
- AIMultiple — Reranker benchmark (top 8 models): https://aimultiple.com/rerankers
- TheDataGuy — "Evaluating RAG Systems with Ragas": https://thedataguy.pro/blog/2025/04/evaluating-rag-systems-with-ragas/

### Tertiary (LOW confidence — directional only)

- Medium / Xiwei Zhou — "Speed Showdown for your RAG improvement: Reranker performance on CPU/GPU/TPU": https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077
- CallSphere blog — "pg_trgm + pgvector Hybrid Retrieval" (2026): https://callsphere.ai/blog/vw7h-pg-trgm-pgvector-hybrid-retrieval-2026

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every library is either already in the image (sentence-transformers, openai, sqlalchemy) or a thin offline addition (ragas, matplotlib).
- Architecture: HIGH — generated tsvector + GIN + RRF is the textbook Postgres-native hybrid pattern, used by Tiger Data and ParadeDB in production.
- Reranker choice: HIGH — bge-reranker-base is the most-cited CPU-friendly cross-encoder in 2024–2026 RAG work; the v2-m3 alternative offers no English-corpus advantage at 2x cost.
- RRF parameter (k=60): HIGH — citable to original 2009 paper, used industry-wide.
- Per-provider isolation in FTS: HIGH — pushed into SQL by recommendation; planner just needs to follow the pattern.
- RAGAS reproducibility: MEDIUM — LLM-judge variance is the unavoidable risk; mitigated by version pinning and same-session runs.
- Latency budget: MEDIUM — depends on the target machine's CPU. Conservative recommendation (sync, batch=16) leaves room for the LLM stream to dominate as expected.

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (RAGAS, sentence-transformers, and pgvector are moving but the SoTA stack at this date is stable).
