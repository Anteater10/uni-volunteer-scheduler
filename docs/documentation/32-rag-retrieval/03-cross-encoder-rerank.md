# Documentation 03 — Local cross-encoder reranker (BAAI/bge-reranker-base)

**Plan:** 32-03
**Module:** `backend/app/copilot/retrieval/rerank.py`
**Status:** Shipped on `feature/v1.4-phase-32-rag-retrieval`.

## Purpose

Reorder the top-N hybrid-retrieval candidates by a learned
cross-encoder relevance score so the LLM prompt is grounded in the
top-K most relevant chunks (default `K=5`). This is the second
retrieval stage in the Phase 32 RAG pipeline.

## Locked decisions

### D-32-03-A: Local-only reranker, no external rerank API (constraint C6)

The reranker runs entirely in-process via
`sentence_transformers.CrossEncoder`. We do **not** call Jina
Reranker, Cohere Rerank, Voyage Reranker, or any other hosted rerank
service. The test suite enforces this with a literal `grep` over the
module source
(`test_rerank_no_external_apis`) — any future commit that introduces
one of the forbidden vendor names breaks CI.

Rationale:
* **Data governance.** The chunk text is repository documentation,
  not user PII (Phase 31 corpus walker deny-lists user tables), but
  the policy is "no third-party retrieval surfaces" by default.
* **Cost predictability.** Hosted rerankers are priced per token at
  query time. Local rerank is a one-time model download.
* **Latency.** Network rerank adds an extra round-trip on top of LLM
  streaming. CPU rerank is in-process.

### D-32-03-B: `BAAI/bge-reranker-base` as the model choice

[CITED: huggingface.co/BAAI/bge-reranker-base] — Apache-2.0 licensed,
110 M parameters, 278 MB on disk, English-strong. Alternative
candidates considered and rejected in the RESEARCH document:

| Rejected alternative           | Reason                                |
|--------------------------------|---------------------------------------|
| `bge-reranker-v2-m3`           | 5x larger, 3x slower, multilingual quality wasted on English corpus [CITED: bge-model.com/bge/bge_reranker_v2.html] |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Trained on web search; transfers poorly to technical-doc corpus per AIMultiple reranker benchmark |
| Jina Reranker v2 / Cohere Rerank 4 | Violates D-32-03-A (constraint C6) |

### D-32-03-C: Sync, in request path (not Celery)

The cross-encoder is invoked synchronously inside the chat-turn
request handler. Pushing it to Celery would add a Redis hop and
serialization overhead per request for no latency win — the
inference itself is ~150-350 ms on CPU for batch=20, well inside the
Phase 30 P95 < 12 s budget [CITED:
medium.com/@xiweizhou/speed-showdown-reranker;
aimultiple.com/rerankers]. Celery is reserved for jobs that take
seconds to minutes (corpus ingestion, email sending), not
sub-second CPU work.

### D-32-03-D: `lru_cache(maxsize=1)` singleton for model lifecycle

The model loader is wrapped in `functools.lru_cache(maxsize=1)` so
the 278 MB weights load exactly once per worker process and stay
resident for the life of the process. This mirrors the Phase 31
`LocalBgeEmbeddingProvider._ensure_loaded` pattern. The test
`test_rerank_singleton_model_load` enforces this with a mocked
constructor and a call-count assertion.

### D-32-03-E: `max_length=512` token cap

Our chunks are ~1024 chars (~200-300 tokens) and queries are short,
so 512 tokens of model context is comfortable headroom. Truncation
only kicks in on pathologically long inputs, which the corpus
chunker does not produce.

## API surface

```python
from app.copilot.retrieval import rerank

reranked = rerank(query="how does signup work?", candidates=hybrid_hits, top_k=5)
```

* `query: str` — the user's chat turn.
* `candidates: list[dict]` — hybrid retriever output. Required keys:
  `id`, `content`. Other keys (`document_id`, `char_start`,
  `char_end`, `rrf_score`) pass through unchanged.
* `top_k: int = 5` — maximum number of results.
* Returns: `list[dict]` of at most `top_k` candidates ordered by
  descending rerank score, each augmented with `rerank_score:
  float`. Tiebreak on equal scores is by `id` ascending
  (deterministic).

## Citation contract (paired with Plan 32-04)

```python
class Citation(BaseModel):
    chunk_id: UUID
    source_path: str
    char_start: int
    char_end: int
    quote: str                    # content[:240]
    rrf_score: float | None
    rerank_score: float | None
```

A `field_validator` on `char_end` rejects `char_end < char_start`
with a `pydantic.ValidationError`. This shape is consumed verbatim by
Plan 32-04's router and Plan 32-05's frontend — do not rename fields
without coordinating downstream.

## Latency contract

| Stage                        | Budget   | Source                                |
|------------------------------|----------|---------------------------------------|
| Reranker inference, batch=20 | P95 ≤ 1.2 s | REQ-32-04                          |
| Reranker model cold load     | one-time at worker boot | RESEARCH §Pitfall 2 |
| Reranker per turn (warm)     | ~150-350 ms p50 | [CITED: medium.com/@xiweizhou/speed-showdown-reranker] |

P95 ≤ 1.2 s gives a 3-4x safety margin over published CPU benchmarks
and accommodates the occasional GC pause or thread-pool contention.

## Operational notes

* The 278 MB model is downloaded to the HuggingFace cache on first
  use. The cache directory is the same volume Phase 31 mounted for
  the embedding model — no additional infrastructure required.
* **Open question for Plan 32-04 smoke:** is the model pre-baked into
  the Docker image at build time, or does the first request pay the
  download cost? Recorded in `32-03-SUMMARY.md` for follow-up.
* In tests, the constructor is monkeypatched so CI never pays the
  download cost. Production code paths still load the real model.

## Coverage

`backend/app/copilot/retrieval/rerank.py` and `citations.py` are
100% line + 100% branch covered by `tests/test_retrieval_rerank.py`
and `tests/test_retrieval_citations.py` (22 tests total). The
per-package gate `app/copilot/*` ≥ 95% line and branch is enforced
by the existing CI script from Phase 31.

## References

* [CITED: huggingface.co/BAAI/bge-reranker-base] — model card,
  license, recommended usage with `CrossEncoder(max_length=512)`.
* [CITED: bge-model.com/bge/bge_reranker_v2.html] — BGE family
  comparison.
* [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]
  — the "20-result prefetch per retriever, single rerank" pattern.
* [CITED: medium.com/@xiweizhou/speed-showdown-reranker] — CPU
  reranker latency benchmark.
* [CITED: aimultiple.com/rerankers] — reranker model comparison.
