---
phase: 31
plan: 03
subsystem: corpus
tags: [corpus, chunker, walker, pure-python, wave-2]
dependency_graph:
  requires: [31-01, 31-02]
  provides:
    - app.corpus.chunker.chunk_text (deterministic recursive splitter)
    - app.corpus.walker.walk_sources (allow-list filesystem walker)
    - Chunk dataclass (content, char_start, char_end)
    - SourceDocument dataclass (source_path, source_kind, title, content, byte_size)
  affects: []
tech_stack:
  added: []  # no new runtime deps — pure stdlib (ast, re, pathlib, dataclasses)
  patterns:
    - "Recursive character splitter (LangChain-style, hand-rolled)"
    - "Gitignore-semantics glob → regex translation for ** support"
    - "AST-based docstring extraction (bodies never read)"
key_files:
  created:
    - backend/app/corpus/__init__.py
    - backend/app/corpus/chunker.py
    - backend/app/corpus/walker.py
  modified:
    - backend/tests/test_corpus_chunker.py
    - backend/tests/test_corpus_walker.py
decisions:
  - "Char-fallback piece size = chunk_overlap (not chunk_size) so merge stage can preserve exact overlap"
  - "Custom **-aware glob translator instead of fnmatch (fnmatch's * crosses /, gitignore semantics don't)"
  - "Exhaustive _classify dispatch (no None return) — every allow-listed path is one of md/.py/.jsx-family"
metrics:
  duration_min: ~25
  tests_added: 6 (chunker) + 5 (walker) = 11
  coverage_pct: 100
  completed_date: 2026-05-11
---

# Phase 31 Plan 03: Corpus chunker + walker — Summary

Pure-Python building blocks of the ingest pipeline: a deterministic recursive character chunker and an allow-list filesystem walker, both DB-free, both 100%-covered. Plan 04 composes them into the ingest CLI.

## What changed

### `backend/app/corpus/chunker.py` (new, 87 lines)

- `chunk_text(text, *, chunk_size=1024, chunk_overlap=128, separators=SEPARATORS) -> list[Chunk]` — deterministic recursive character splitter. Tries separators in order (`\n\n` → `\n` → `". "` → `" "` → `""`) until every piece is ≤ `chunk_size`, then greedily merges into windows with `chunk_overlap` characters of overlap.
- `CHUNKER_VERSION = "v1-recursive-char-1024-128"` — version pin so re-embedding decisions in plan 04 can key off chunker semantics.
- `Chunk(content, char_start, char_end)` — frozen dataclass. Absolute offsets into the original input — the load-bearing invariant for Phase 32 citation rendering.
- No external deps. No randomness, no time, no env reads, no I/O. Identical bytes in → identical chunks out.

### `backend/app/corpus/walker.py` (new, 146 lines)

- `walk_sources(*, root: Path) -> list[SourceDocument]` — single public entrypoint. Reads files only; opens zero DB connections.
- `SOURCE_GLOBS_V1` and `DENY_LIST` exactly per RESEARCH §Step 3.
- Source kinds emitted: `markdown`, `alembic_migration`, `python_module`, `python_function`, `frontend_component`.
- AST-based extraction for Python: `ast.parse` → walk `Module`/`ClassDef`/`FunctionDef`/`AsyncFunctionDef` and emit one document per docstring. **Function bodies are never read** (verified by test).
- CRLF→LF normalization + per-line trailing-whitespace strip before hashing, so the same logical content has the same `byte_size` and content hash across editor configurations.
- Output sorted lexicographically by `source_path` for deterministic ordering.
- Custom recursive-glob → regex translator (`_glob_to_regex`) handles `**` as "zero or more path segments" because Python's `fnmatch` treats `*` as crossing `/` (wrong semantics for our deny-list).

### Tests

- `backend/tests/test_corpus_chunker.py`: 3 xfail stubs from plan 01 flipped to green + 3 new boundary tests (separator-first split, substring invariance, exact overlap on flat input). 6 tests total.
- `backend/tests/test_corpus_walker.py`: 3 xfail stubs flipped + 2 new boundary tests (Python docstring-only extraction with body-leak assertion, LF/CRLF byte-size + content-hash equivalence). 5 tests total.

## Coverage

| Module | Statements | Covered | Coverage |
|---|---|---|---|
| `app/corpus/__init__.py` | 3 | 3 | 100% |
| `app/corpus/chunker.py` | 87 | 87 | 100% |
| `app/corpus/walker.py` | 146 | 146 | 100% |
| **TOTAL** | **236** | **236** | **100%** |

Matches the Phase 30 invariant for `app.copilot.*` (100% on the public surface of the new package).

## Walker dry-run on the live repo

Running `walk_sources(root=Path('/repo'))` against the current repo state yields:

| source_kind | count |
|---|---|
| markdown | 244 |
| python_function | 248 |
| python_module | 44 |
| frontend_component | 44 |
| alembic_migration | 20 |
| **TOTAL** | **600** |

This is the corpus size plan 04's ingest CLI will see on first run. 600 source documents → plan 04 will chunk → embed → upsert into `corpus_chunks`.

## Representative chunk dump

Source: `docs/learning/30-streaming-chat-mvp/sse-streaming.md` (5128 bytes after CRLF normalization). Chunked with defaults (`chunk_size=1024`, `chunk_overlap=128`).

- 7 chunks emitted.
- First chunk: `char_start=0`, `char_end=874`. Ends mid-sentence at `"Three protocols give us bytes-as-they-arrive over the web:"`.
- Second chunk: `char_start=816`, `char_end=1827`. The 58-character overlap (874 − 816 = 58) is less than 128 because the chunker preferred a `\n\n` separator boundary over a strict-overlap cut — exactly the intended behavior for paragraph-structured input.

First chunk content (head 300 chars, after CRLF normalization):

```
# Server-Sent Events for LLM Streaming

## Why this matters

LLMs generate text one token at a time. A 200-word answer takes a model
4–10 seconds to produce end-to-end. If we wait for the full response
before replying to the browser, the user stares at a spinner the entire
time. If we stream tokens
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Char-fallback piece size produced no overlap**

- **Found during:** Task 1 (test_chunker_overlap_is_chunk_overlap_chars failed)
- **Issue:** The original char-level fallback sliced text into pieces of exactly `chunk_size`. The merge stage then could not retain any pieces for overlap, because keeping one piece would re-emit the just-flushed chunk in full.
- **Fix:** Char fallback now slices into pieces of `chunk_overlap` (or `chunk_size` when overlap is 0). The merge stage's tail-keeping logic now reliably preserves exactly `chunk_overlap` characters between adjacent windows on flat input.
- **Files modified:** `backend/app/corpus/chunker.py`
- **Commit:** 1710ef0

**2. [Rule 2 — Critical functionality] fnmatch wrong semantics for `**`**

- **Found during:** Task 2 (test_walker_extracts_python_docstrings_not_bodies failed with empty walker output)
- **Issue:** `fnmatch.fnmatch` treats `*` as matching any character including `/`, so `backend/app/**/*.py` failed to match `backend/app/foo.py` (no intermediate slash to consume the `**/`).
- **Fix:** Replaced fnmatch with a custom recursive-glob translator (`_glob_to_regex`) that gives `**` proper gitignore semantics ("zero or more path segments") and treats single `*` as `[^/]*`.
- **Files modified:** `backend/app/corpus/walker.py`
- **Commit:** c100655

### Out of scope

None.

## Known Stubs

None. Both modules are complete public surfaces. Plan 04 (ingest orchestrator) will import from them without further chunker/walker changes.

## Self-Check: PASSED

Verified at commit `c100655` (HEAD):

- `backend/app/corpus/__init__.py` FOUND
- `backend/app/corpus/chunker.py` FOUND
- `backend/app/corpus/walker.py` FOUND
- `backend/tests/test_corpus_chunker.py` FOUND (6 tests, 0 xfail)
- `backend/tests/test_corpus_walker.py` FOUND (5 tests, 0 xfail)
- Commit `1710ef0` (task 1, chunker) FOUND
- Commit `c100655` (task 2, walker) FOUND
- Coverage on `app.corpus.*` = 100% (236/236 statements)
- Adjacent suites (corpus migration round-trip, copilot router, corpus logger/embeddings/ingest stubs) still green: 35 passed, 1 skipped, 1 xfailed.
