"""Phase 32-03 — tests for the Citation pydantic model + chunks_to_citations.

Citation shape is load-bearing (Plan 32-04 router serializes it):

* ``chunk_id: UUID`` (NOT a string — strong typing at the contract boundary)
* ``source_path: str``
* ``char_start: int``
* ``char_end: int`` (must be ``>= char_start`` — validator enforces)
* ``quote: str`` (``content[:240]``)
* ``rrf_score: float | None``
* ``rerank_score: float | None``
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _hit(chunk_id: UUID, content: str = "hello world", *, doc_id: str = "doc-1") -> dict:
    return {
        "id": str(chunk_id),
        "document_id": doc_id,
        "content": content,
        "char_start": 100,
        "char_end": 100 + len(content),
        "rrf_score": 0.42,
        "rerank_score": 0.87,
    }


def _resolver(mapping: dict[str, str]):
    def _inner(doc_id: str) -> str:
        return mapping[doc_id]

    return _inner


# ---------------------------------------------------------------------------
# Citation model
# ---------------------------------------------------------------------------


def test_citation_model_shape():
    """Hard-locked field set + types — Plan 32-04 depends on this exactly."""
    from app.copilot.schemas import Citation

    cid = uuid4()
    c = Citation(
        chunk_id=cid,
        source_path="docs/learning/32-rag-retrieval/03-cross-encoder-rerank.md",
        char_start=0,
        char_end=10,
        quote="hello",
        rrf_score=0.5,
        rerank_score=0.9,
    )
    assert c.chunk_id == cid
    assert isinstance(c.chunk_id, UUID)
    assert c.source_path.endswith(".md")
    assert c.char_start == 0
    assert c.char_end == 10
    assert c.quote == "hello"
    assert c.rrf_score == 0.5
    assert c.rerank_score == 0.9


def test_citation_scores_nullable():
    """rrf_score and rerank_score are optional (float | None)."""
    from app.copilot.schemas import Citation

    c = Citation(
        chunk_id=uuid4(),
        source_path="x.md",
        char_start=0,
        char_end=1,
        quote="q",
        rrf_score=None,
        rerank_score=None,
    )
    assert c.rrf_score is None
    assert c.rerank_score is None


def test_citation_validation_rejects_invalid_offsets():
    """char_end < char_start must raise pydantic ValidationError."""
    from app.copilot.schemas import Citation

    with pytest.raises(ValidationError):
        Citation(
            chunk_id=uuid4(),
            source_path="x.md",
            char_start=50,
            char_end=10,  # less than start — invalid
            quote="q",
            rrf_score=0.0,
            rerank_score=0.0,
        )


def test_citation_validation_accepts_equal_offsets():
    """char_end == char_start is valid (zero-length range, e.g., empty chunk)."""
    from app.copilot.schemas import Citation

    c = Citation(
        chunk_id=uuid4(),
        source_path="x.md",
        char_start=10,
        char_end=10,
        quote="",
        rrf_score=0.0,
        rerank_score=0.0,
    )
    assert c.char_end == c.char_start


# ---------------------------------------------------------------------------
# chunks_to_citations
# ---------------------------------------------------------------------------


def test_chunks_to_citations_empty_list_returns_empty():
    from app.copilot.retrieval.citations import chunks_to_citations

    assert chunks_to_citations([], path_resolver=lambda d: "x") == []


def test_chunks_to_citations_shape():
    from app.copilot.retrieval.citations import chunks_to_citations
    from app.copilot.schemas import Citation

    cid = uuid4()
    hit = _hit(cid, content="Volunteers help SciTrek run modules.")
    out = chunks_to_citations(
        [hit],
        path_resolver=_resolver({"doc-1": "docs/repo/README.md"}),
    )
    assert len(out) == 1
    cit = out[0]
    assert isinstance(cit, Citation)
    assert cit.chunk_id == cid
    assert cit.source_path == "docs/repo/README.md"
    assert cit.char_start == 100
    assert cit.char_end == 100 + len("Volunteers help SciTrek run modules.")
    assert cit.quote == "Volunteers help SciTrek run modules."
    assert cit.rrf_score == pytest.approx(0.42)
    assert cit.rerank_score == pytest.approx(0.87)


def test_chunks_to_citations_quote_truncation():
    """Quote must be content[:240]; longer content truncated."""
    from app.copilot.retrieval.citations import chunks_to_citations

    long = "A" * 500
    short = "B" * 30
    hits = [_hit(uuid4(), content=long), _hit(uuid4(), content=short, doc_id="doc-2")]
    out = chunks_to_citations(
        hits,
        path_resolver=_resolver({"doc-1": "long.md", "doc-2": "short.md"}),
    )
    assert len(out[0].quote) == 240
    assert out[0].quote == "A" * 240
    assert out[1].quote == short  # unchanged


def test_chunks_to_citations_preserves_order():
    """Output order must match input order — reranker already chose the order."""
    from app.copilot.retrieval.citations import chunks_to_citations

    ids = [uuid4() for _ in range(4)]
    hits = [_hit(i, content=f"chunk-{n}") for n, i in enumerate(ids)]
    out = chunks_to_citations(hits, path_resolver=lambda d: f"/{d}.md")
    assert [c.chunk_id for c in out] == ids


def test_chunks_to_citations_handles_missing_scores():
    """If rrf_score or rerank_score absent from the hit dict, citation gets None."""
    from app.copilot.retrieval.citations import chunks_to_citations

    cid = uuid4()
    hit = {
        "id": str(cid),
        "document_id": "doc-1",
        "content": "x",
        "char_start": 0,
        "char_end": 1,
        # no rrf_score, no rerank_score
    }
    out = chunks_to_citations([hit], path_resolver=lambda d: "p.md")
    assert out[0].rrf_score is None
    assert out[0].rerank_score is None


def test_chunks_to_citations_validation_propagates():
    """If a hit has invalid offsets, pydantic ValidationError must surface."""
    from app.copilot.retrieval.citations import chunks_to_citations

    bad = {
        "id": str(uuid4()),
        "document_id": "doc-1",
        "content": "x",
        "char_start": 50,
        "char_end": 10,
        "rrf_score": 0.1,
        "rerank_score": 0.2,
    }
    with pytest.raises(ValidationError):
        chunks_to_citations([bad], path_resolver=lambda d: "p.md")


def test_chunks_to_citations_exported_from_retrieval_package():
    from app.copilot.retrieval import chunks_to_citations

    assert callable(chunks_to_citations)
