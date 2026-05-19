# Embedding Provider Selection: Jina v3 Primary with Local BGE Fallback

## Summary

The retrieval pipeline embeds each chunk into a 1024-dimensional
vector using a pluggable provider interface. The default provider
is **Jina Embeddings v3** [CITED: jina.ai/embeddings], a 1024-native
multilingual text embedding model accessible via a free API tier.
The fallback is **`BAAI/bge-small-en-v1.5`**
[CITED: huggingface.co/BAAI/bge-small-en-v1.5], a 384-dimensional
open-weights model executed locally inside the backend container
via the `sentence-transformers` library. Fallback vectors are
right-padded with zeros to match the column's 1024-dimensional
schema. The choice of providers is constrained by the project's
zero-budget operational requirement (REQ-31-04) and the schema's
fixed-width vector column (REQ-31-11).

## Provider interface

The interface is defined in `backend/app/corpus/embeddings.py`:

```python
class EmbeddingProvider(Protocol):
    name: str
    model_id: str
    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]: ...
```

Each call returns the vectors plus an `EmbedMeta` record containing
provider name, model ID, API call count, total latency in
milliseconds, and provider-reported token count where available.
These metadata fields propagate to per-run telemetry columns
described in writeup 04.

## Primary: Jina Embeddings v3

Model: `jina-embeddings-v3`. Native output dimension 1024. Context
window 8192 tokens. Trained with Matryoshka Representation Learning
[CITED: Kusupati et al., 2022], which preserves semantic structure
under truncation; this property is unused at Phase 31 but is
preserved as a future option for dimensionality experiments.

Free-tier service limits, as of 2026-05-10:

| Limit | Value |
|---|---|
| Requests per minute | 100 |
| Tokens per minute | 100,000 |
| Concurrent connections | 2 |
| Daily IP cap | 10,000 requests / 60 seconds |

The ingestion CLI is structured to respect these limits via
batching and exponential backoff on HTTP 429 responses. Larger
corpora may exhaust the free tier; the fallback path engages in
that case and is recorded in `ingestion_runs.notes`.

## Fallback: BAAI bge-small-en-v1.5

Model: `BAAI/bge-small-en-v1.5`. Native output dimension 384. Model
size ≈ 130 MB. License: MIT (permits commercial and research use).
Executes locally via `sentence-transformers` 3.x inside the backend
container; no network egress is required. Latency is CPU-bound at
roughly 30-50 milliseconds per chunk on the project's reference
hardware.

The fallback's 384-dim output is padded to 1024 by appending zeros.
Cosine similarity between two padded BGE vectors equals cosine
similarity between the unpadded originals; padding does not
distort the BGE embedding space. Cosine similarity between a
padded BGE vector and a Jina vector is **not** meaningful — the
two models live in unrelated embedding spaces (writeup 04 details
the per-chunk `embedding_provider` filter that enforces isolation
at retrieval time).

## Why not OpenRouter for embeddings

The chat layer (Phase 30) uses OpenRouter as a multi-vendor proxy.
Extending this choice to embeddings was considered and rejected.
OpenRouter's embedding endpoint exists [CITED:
openrouter.ai/docs/api/reference/embeddings] but the free-tier
embedding model lineup is currently sparse and unstable: models
join and leave the free tier without notice. Additionally, coupling
the embedding pipeline to chat-tier availability would create a
single point of failure across two otherwise independent subsystems.

## Why not paid providers in production

The project operates under a zero-budget constraint. Paid providers
(OpenAI text-embedding-3-large, Voyage 3.5, Cohere Embed v3) are
preserved as candidates for the Phase 35 evaluation, where direct
comparison may be appropriate. The interface is designed to admit
additional providers without schema change: each provider supplies
its own `name` and `model_id`, both recorded per-chunk.

## Selection logic and fallback path

The CLI's `--provider` flag selects the primary provider. The
default value is `settings.corpus_embedding_primary` (currently
`"jina"` in production, `"local"` for offline runs and tests).
When the primary raises `RateLimitError`, the ingestion loop
transparently retries on the configured fallback. The transition
is recorded in `ingestion_runs.notes` as
`"primary={primary_name} rate-limited; fell back to {fallback_name}"`.
Per-chunk `embedding_provider` and `embedding_model` columns
record the *actual* provider that produced each row, not the
configured primary; this distinction matters at retrieval time
because cross-provider cosine comparisons are not semantically
valid.

## References

- Jina AI. "Jina Embeddings v3." Model card and free-tier limits.
  https://jina.ai/embeddings (accessed 2026-05-10).
- BAAI. "bge-small-en-v1.5." Model card.
  https://huggingface.co/BAAI/bge-small-en-v1.5 (accessed
  2026-05-10).
- Kusupati, A., et al. (2022). "Matryoshka Representation Learning."
  arXiv:2205.13147.
- OpenRouter. "Embeddings API reference."
  https://openrouter.ai/docs/api/reference/embeddings (accessed
  2026-05-10).
- Voyage AI. "Embedding output dimensions."
  https://docs.voyageai.com (accessed 2026-05-10).
- Reimers, N., & Gurevych, I. (2019). "Sentence-BERT." arXiv:1908.10084.
  Provides the architectural lineage for BGE-small.
