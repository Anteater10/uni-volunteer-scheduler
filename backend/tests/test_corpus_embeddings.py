"""Wave 0 stub - REQ-31-11. Provider implementations land in plan 04."""
import pytest


@pytest.mark.xfail(strict=True, reason="REQ-31-11 dim-locked-to-1024 lands in plan 04")
def test_embedding_dim_locked_to_1024():
    from app.corpus.embeddings import EMBEDDING_DIM, LocalBgeEmbeddingProvider
    assert EMBEDDING_DIM == 1024
    p = LocalBgeEmbeddingProvider()
    vecs, _meta = p.embed(["hello"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 1024  # 384 native, padded to 1024
