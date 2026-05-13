# Chunking, Walking, and the Discipline of Reproducibility

## Why this matters

Before we can embed anything, we have to decide what *one thing* is.
A 200-line markdown file does not become one vector — it becomes
several. A Python module's docstring is its own vector even though it
lives inside a 500-line file. A frontend component's leading comment
is a vector but the body is not. Every one of these decisions is
encoded in two small modules: `walker.py` decides what to read, and
`chunker.py` decides how to slice what we read.

Get these wrong and the rest of the pipeline is fast and accurate at
finding the wrong things. The retrieval layer in Phase 32 has no way
to recover from a chunk that does not exist or does not align with a
sentence boundary. So these two modules deserve the lecture treatment
even though their entire surface is fewer than 600 lines of Python.

## Why chunking exists

Embedding models have a context window. Even Jina v3, with its
generous 8192-token window, struggles to produce a useful single
vector for a long document — the resulting embedding averages over
too many concepts to be a useful retrieval target. The smaller, more
focused the chunk, the sharper the embedding.

The other reason is *retrieval granularity*. If we retrieve a whole
file and dump it into the LLM prompt, we waste context window on
sections the user didn't ask about. If we retrieve a single sentence,
we lose the surrounding context that makes the sentence make sense.
The sweet spot for general technical prose is somewhere around 500-
1500 characters per chunk, with overlap between adjacent chunks so a
sentence that straddles a boundary appears in both. We picked
**1024 characters with 128 of overlap** — slightly smaller than the
LangChain default of 4000/200, because our docs are dense and we
prefer to err toward more, smaller chunks.

## The recursive character splitter, walked through

The algorithm is small enough to fit in a paragraph:

> Take the input. Try to split it on the strongest separator
> (`\n\n` — paragraph break). If any resulting piece is longer than
> the chunk size, recurse into that piece with the next-strongest
> separator (`\n` — line break), then (`. ` — sentence boundary),
> then (` ` — word boundary), then finally (`""` — character slice).
> Once every piece fits, glue them back together with `overlap`
> characters of context from the previous chunk.

Worked example. Imagine a 3000-character document. The splitter
first tries `\n\n` and gets three paragraphs of roughly 1000
characters each. One of them is 1400 characters; that one recurses
on `\n`, which produces five lines averaging 280 characters. Those
lines get re-glued, with the previous chunk's last 128 characters
prepended to the next chunk's first character, until every chunk
is ≤ 1024.

Two properties earn the algorithm its keep:

1. **Boundary respect.** It prefers paragraph breaks over line
   breaks over sentence boundaries over word boundaries over raw
   characters. A chunk almost never ends mid-word.
2. **Determinism.** Same input bytes → same output chunks, byte for
   byte. No random seeds, no time-of-day, no language model in the
   loop.

The implementation in `backend/app/corpus/chunker.py` is hand-rolled
(no LangChain dependency). It is ~200 lines and 100% test-covered.

## The `char_start` / `char_end` invariant

Each chunk records the byte offsets it occupies in the original
document. We test that this is consistent: the original document
sliced from `char_start` to `char_end` equals the chunk's
`content`. This invariant exists for one reason: Phase 32's citation
UI quotes "lines 42–58 of `docs/learning/30-…/sse-streaming.md`",
and you cannot trust the citation if the offset is approximate.
Drifting offsets are a silent paper-killer: the citation looks
plausible, but the section it points to is not the one the model
actually used.

The test that pins this invariant is
`test_corpus_chunker.py::test_chunker_offsets_consistent`. It runs
on every commit. If you ever see it red, you almost certainly broke
either the recursive split or the overlap stitching — both have
been written carefully exactly because this assertion is so easy to
break by accident.

## The walker — allow-list philosophy

The walker is the *other* small module. Its job is to enumerate
every file in the repo that belongs in the corpus and emit a
`SourceDocument` for each. The design choice you should notice
immediately: we have an **allow-list**, not a deny-list, for what
to read.

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

Compare this to the alternative: walk every file under the repo,
exclude `.git`, `node_modules`, etc. The allow-list approach
guarantees that adding a new data type to the repo does not silently
add it to the corpus. If we drop a CSV of volunteer emails into
`docs/imports/`, the walker will not pick it up unless we
*explicitly* add `docs/imports/*.csv` to the allow-list and write a
new emitter for it.

This is **PII deny-by-construction**. The walker reads no `.json`,
no `.csv`, no SQL dumps; opens no database connections; never
touches any of the volunteer tables (`signups`, `users`,
`magic_link_tokens`, `audit_logs`, etc.). The proof is in
`test_corpus_walker.py::test_walker_opens_no_db_connection`, which
introspects the module for SQLAlchemy session usage.

## Why determinism matters for the paper

This work is destined for a workshop paper. A reviewer will (rightly)
ask: "can I reproduce your retrieval results?" The honest answer is
yes, but only because we baked determinism into every stage where
we control the inputs:

- The walker sorts its results lexicographically before processing.
- The chunker is deterministic.
- The content hash (`sha256` of normalized bytes) is recorded per
  document and per chunk.
- The embedding model and provider are recorded per chunk.
- The git commit SHA is recorded per ingestion run.

Given a git commit and an `ingestion_run_id`, anyone with the same
codebase can re-derive the same chunks and (with the same provider)
the same embeddings. That is the level of reproducibility the paper
will claim.

## Check-in question

We deliberately excluded `**/test_*.py` from the walker. Why? What
goes wrong if we add Playwright test fixtures to the corpus, and
what is the lightest-weight defense if a contributor later argues
"the test fixtures explain the project really well, let's include
them"? See Pitfall 6 in `31-RESEARCH.md` for the answer.

## What to read next

- [LangChain `RecursiveCharacterTextSplitter` source](https://github.com/langchain-ai/langchain/blob/master/libs/text-splitters/langchain_text_splitters/character.py)
  — the algorithm we mirror, without the LangChain dependency.
- [Greg Kamradt, "5 Levels of Text Splitting"](https://www.youtube.com/watch?v=8OJC21T2SL4)
  — the canonical walk-through of chunking strategies, from
  character splits to semantic splits.
- [The `ast` module](https://docs.python.org/3/library/ast.html) —
  how we extract Python docstrings without parsing function bodies.
