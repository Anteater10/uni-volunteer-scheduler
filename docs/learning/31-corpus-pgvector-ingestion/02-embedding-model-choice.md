# Choosing an Embedding Model on a Zero-Dollar Budget

## Why this matters

The model that turns text into vectors is the *quietest* decision in
the entire copilot, and probably the one that does the most damage if
we get it wrong. A bad chat model says something embarrassing and we
notice. A bad embedding model retrieves the wrong chunks; the chat
model then answers fluently but cites the wrong section of the
codebase, and we may not notice for weeks. The paper would be wrong
and the demo would still look great. So this decision matters more
than its visibility suggests.

We also have a hard constraint: **zero inference budget**. The
project is a UCSB SciTrek staff tool with no operations budget for
paid APIs. The embedding provider has to be either free-tier or
local-CPU. That eliminates the obvious answers (OpenAI
text-embedding-3-large, Voyage 3.5, Cohere Embed v3) for production
use; we keep them in mind as comparison points for Phase 35.

## The intuition

An embedding is a *fixed-length numerical fingerprint of meaning*.
Feed in a sentence; get out a list of, say, 1024 numbers between -1
and 1. Two embeddings are "close" (high cosine similarity) when the
underlying sentences mean similar things. That is the entire
contract.

The model that does the embedding is itself a neural network — almost
always a transformer — trained on enormous text corpora with a
contrastive loss: similar texts should produce similar vectors,
dissimilar texts should produce dissimilar vectors. The training
details matter less than two practical properties:

1. **Embeddings from different models live in different spaces.** A
   Jina vector and a BGE vector for the same sentence are not
   meaningfully comparable. Cosine distance between them is noise.
2. **Dimensionality is a deliberate choice, not a measurement.** A
   768-dim model and a 1024-dim model are not just "different sizes
   of the same thing" — they are different models that happen to
   output different-shaped arrays.

These two facts force Phase 31's plumbing: we lock the column at
`vector(1024)` and we record the provider per chunk so the retrieval
layer can filter by it.

## The free-tier landscape as of May 2026

| Provider | Model | Native dim | Free-tier shape | Verdict |
|---|---|---|---|---|
| Jina AI | jina-embeddings-v3 | 1024 | 100 RPM / 100K TPM, 2 concurrent, 10K req per 60s IP cap | **primary** |
| BAAI (Hugging Face) | bge-small-en-v1.5 | 384 | local — permanently free | **fallback** |
| OpenAI | text-embedding-3-large | 3072 (truncatable) | paid only | rejected (C4) |
| Voyage AI | voyage-3 | 1024 | paid only | rejected (C4) |
| OpenRouter | various | varies | embedding free-tier is thin and churning | rejected (D6) |

Two providers survived the screen. Jina v3 wins on quality: it is
MRL-trained (Matryoshka Representation Learning) so dimensions can
be truncated post-hoc without retraining, and it is currently the
strongest free-tier general-purpose embedding model. BGE-small wins
on availability: a 130MB model that runs CPU-only inside the backend
container with no network dependency at all.

## Why we chose primary plus fallback

If we hardwire Jina, a rate-limit blip during ingestion stops the
phase. If we hardwire BGE, ingestion runs offline but the paper has
to live with a 384-dim fallback's recall. Combining gives us the
best of both: Jina runs as long as it can, and the moment a 429 or
network error hits, the in-process BGE provider takes over
mid-batch and finishes the run. The combination is recorded in
`ingestion_runs.notes` so paper-quality runs can be filtered to
"Jina-only".

The handoff is implemented in `_embed_with_fallback` in
`backend/app/corpus/ingest.py`. It is two `try`/`except` blocks and
a noted record of the fallback event. That is the whole mechanism.

## The padding trick (384 → 1024)

`vector(1024)` is fixed; BGE outputs 384. We right-pad BGE vectors
with zeros to reach 1024. This is mathematically harmless inside the
BGE space — adding zeros to a vector and then taking cosine distance
to another zero-padded BGE vector gives the exact same answer as
cosine distance between the unpadded versions. The padding zeros do
not change the relative geometry between BGE-derived vectors.

What padding *cannot* do is make BGE and Jina vectors comparable.
Their underlying spaces are completely different. A Jina-embedded
chunk near a BGE-padded query will look "close" by cosine numerics
without meaning anything semantically.

The defense is **provider isolation at query time**: the retrieval
layer (Phase 32) must `WHERE embedding_provider = $1`. We bake this
affordance in at Phase 31 by recording `embedding_provider` on every
chunk row. Forget that filter and the retrieval results turn to
noise the moment a fallback event lands in the corpus.

## Why we rejected OpenRouter for embeddings

OpenRouter is our chat provider (Phase 30) and an obvious candidate
for embeddings too. We checked the option and rejected it. Three
reasons:

1. OpenRouter's free-tier embedding lineup is thin compared to its
   chat lineup. The current options are unstable: models join and
   leave the free tier with no notice.
2. Tying the embedding pipeline's reliability to the chat pipeline's
   reliability creates a single point of failure. A chat outage
   should not block an ingestion job.
3. None of the chat-side free models we currently use (`gpt-oss-120b`,
   `llama-3.3-70b`) expose embeddings at all. The two surfaces are
   separate concerns at OpenRouter and at every other multi-model
   gateway we evaluated.

We may revisit this if Phase 35 wants a paid embedding model for
comparison; OpenRouter would be a one-line swap because the API
surface is identical.

## Check-in question

If a future contributor argues "let's add OpenAI text-embedding-3-large
as a third provider for higher quality in Phase 35," what is the
minimum set of schema and code changes required? And which existing
chunks in `corpus_chunks` does that new provider make obsolete? Try
to answer before reading Phase 32's plan.

## What to read next

- [Jina Embeddings v3 model card](https://jina.ai/embeddings) — native
  dim, MRL, free-tier limits.
- [BAAI bge-small-en-v1.5 model card](https://huggingface.co/BAAI/bge-small-en-v1.5)
  — architecture, training data, license.
- [Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147)
  — the paper that explains why Jina v3 lets you truncate dimensions
  after training.
- [BEIR benchmark](https://github.com/beir-cellar/beir) — standard
  evaluation suite for retrieval, useful for replicating our model
  ranking in Phase 35.
