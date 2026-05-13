# Source Walker and Deterministic Recursive Character Chunker

## Summary

Corpus content is selected and segmented by two components: a
deterministic source walker
(`backend/app/corpus/walker.py`) that enumerates ingestible files
under an explicit allow-list, and a recursive character splitter
(`backend/app/corpus/chunker.py`) that segments document bodies
into 1024-character chunks with 128 characters of overlap.
Together these components are designed to satisfy three project
constraints: PII deny-by-construction (REQ-31-05), deterministic
output across runs (REQ-31-07, REQ-31-03), and offset-correct
chunk-to-document attribution for citation (REQ-31-04).

## Allow-list source walker

The walker uses an explicit allow-list of source globs rather than
a deny-list:

```python
SOURCE_GLOBS_V1 = [
    "docs/*.md",
    "docs/learning/**/*.md",
    "docs/documentation/**/*.md",
    "docs/copilot-journal/**/*.md",
    "backend/alembic/versions/*.py",
    "backend/app/**/*.py",
    "frontend/src/**/*.{jsx,js,ts,tsx}",
    ".planning/REQUIREMENTS-*.md",
    ".planning/ROADMAP.md",
    ".planning/phases/**/*.md",
    "*.md",
]
```

A complementary deny-list excludes test fixtures, `node_modules`,
`__pycache__`, environment files, and the project's private notes
directory. The allow-list approach ensures that introducing a new
file type to the repository does not silently expand the corpus;
addition requires both a glob entry and a typed emitter.

Five emitters convert files into `SourceDocument` records:

| Source kind | Extracted content |
|---|---|
| `markdown` | Full document body, title from first H1 |
| `alembic_migration` | Module docstring only; title from `revision` constant |
| `python_module` | Module-level docstring |
| `python_function` | Each function/class docstring (bodies excluded) |
| `frontend_component` | Leading file-level block comment |

Python source code is parsed via `ast`; function and class bodies
are never read into the corpus. The pattern reduces noise (code
bodies are rarely useful retrieval targets) and preserves the
property that only narrative content enters the embedding pipeline.

## Determinism guarantees

The walker enforces three determinism invariants:

1. Glob match results are sorted lexicographically by repository-
   relative POSIX path before processing.
2. File bytes are CRLF-normalized to LF and trailing whitespace is
   stripped per line before hashing or byte-count computation.
3. No system clock, random seed, or file timestamp influences
   either the document set or the chunk content.

The walker opens no database connections and reads no JSON, CSV,
or binary content. This is enforced by a unit test
(`test_corpus_walker.py::test_walker_opens_no_db_connection`)
that introspects the module for SQLAlchemy session usage.

## Recursive character splitter

The splitter implements an algorithm equivalent to LangChain's
`RecursiveCharacterTextSplitter` [CITED: LangChain text-splitters],
hand-implemented without dependencies. Parameters:

| Parameter | Value | Rationale |
|---|---|---|
| `CHUNK_SIZE` | 1024 characters | Mid-range for 8K-context embedders |
| `CHUNK_OVERLAP` | 128 characters | 12.5% overlap preserves boundary context |
| `SEPARATORS` | `["\n\n", "\n", ". ", " ", ""]` | Tried in strict order |
| `CHUNKER_VERSION` | `"v1-recursive-char-1024-128"` | Recorded per run |

The algorithm attempts to split on the strongest separator
(paragraph break) first. Pieces exceeding `CHUNK_SIZE` are
recursively split on the next separator. The base case
(`SEPARATORS[-1] = ""`) is a raw character slice. Pieces are then
re-glued with 128 characters of overlap between adjacent output
chunks.

## Character-offset invariant

Every chunk carries `char_start` and `char_end` offsets into the
source document. The invariant
`document.content[chunk.char_start : chunk.char_end] == chunk.content`
holds for every emitted chunk and is pinned by
`test_corpus_chunker.py::test_chunker_offsets_consistent`. The
invariant exists to support the Phase 32 citation layer, which
quotes specific line ranges back to the user; an offset drift would
silently misattribute model outputs.

## Token estimation

Chunks record a `token_estimate` value computed as
`max(1, len(content) // 4)`. This is a deliberate undercount for
operational planning; the canonical token count for embedding cost
analysis is the provider-reported `embedding_tokens_total` on
`ingestion_runs`. The per-chunk estimate is informational only.

## Reproducibility contract

Given the corpus state defined by:

- a git commit SHA,
- the set of source globs in effect at that commit,
- the chunker version recorded with the ingestion run,
- the embedding provider and model recorded per chunk,

an external reproducer can recompute the identical corpus by
checking out the same commit and re-running ingestion with the
same provider configuration. The chunker is deterministic and the
walker is deterministic; embedding providers may exhibit minor
non-determinism in their numerical outputs but the `content_sha256`
field is byte-identical across runs, enabling reproducibility at
the retrieval-target level.

## References

- LangChain text-splitters source —
  https://github.com/langchain-ai/langchain/tree/master/libs/text-splitters
  (accessed 2026-05-10).
- Python `ast` module —
  https://docs.python.org/3/library/ast.html (accessed 2026-05-10).
- Greg Kamradt. "The 5 Levels Of Text Splitting For Retrieval."
  (2024). YouTube. https://www.youtube.com/watch?v=8OJC21T2SL4.
- pytest documentation, fixture composition —
  https://docs.pytest.org/en/7.x/explanation/fixtures.html
  (accessed 2026-05-10).
