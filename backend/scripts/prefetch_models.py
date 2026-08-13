"""Download the two local model weights into the image's HF cache at build time.

BASE-CONFIG-02. Both models are loaded lazily, in-process, on first use:
``BAAI/bge-small-en-v1.5`` (~130MB) for embeddings and
``BAAI/bge-reranker-base`` (~1.1GB) for reranking. Nothing cached them, so every
fresh container downloaded ~1.3GB from huggingface.co the first time somebody
asked the copilot a question — and paid for it again after every restart, every
scale-out, and every rebuild. Two consequences, one worse than the other: the
first real question after a deploy times out, and the app cannot start serving
that feature at all if huggingface.co is unreachable or rate-limiting.

Baking them into a layer fixes both, and does it in the one place that is
guaranteed to have network and to be cached: the build. Runtime becomes a pure
disk read from ``HF_HOME``.

This runs before ``COPY . /app`` in the Dockerfile so the layer is keyed on
requirements.txt only — editing application code does not re-download 1.3GB.

Run by hand with: ``python scripts/prefetch_models.py``
"""
import os
import sys
import time

# Import the names from config rather than hardcoding them: the point of baking
# is that the cached weights are the ones the app will actually ask for, and a
# copy-paste drift here would silently restore the cold-start download.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RERANKER_MODEL = "BAAI/bge-reranker-base"  # app/copilot/retrieval/rerank.py


def main() -> int:
    from app.config import settings  # noqa: E402  (after sys.path fix)

    cache = os.environ.get("HF_HOME", "(default ~/.cache/huggingface)")
    print(f"prefetching model weights into {cache}", flush=True)

    started = time.time()
    from sentence_transformers import CrossEncoder, SentenceTransformer

    embedding_model = settings.local_embedding_model
    print(f"  embeddings: {embedding_model}", flush=True)
    SentenceTransformer(embedding_model)

    print(f"  reranker:   {RERANKER_MODEL}", flush=True)
    CrossEncoder(RERANKER_MODEL, max_length=512)

    print(f"done in {time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
