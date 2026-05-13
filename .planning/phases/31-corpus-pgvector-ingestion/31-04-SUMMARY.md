---
phase: 31
plan: 04
subsystem: corpus
tags: [corpus, ingestion, embeddings, pgvector, cli, wave-3]
dependency_graph:
  requires: [31-01, 31-02, 31-03]
  provides:
    - app.corpus.embeddings.JinaEmbeddingProvider (HTTPS v3, 1024-dim native)
    - app.corpus.embeddings.LocalBgeEmbeddingProvider (sentence-transformers, padded 384→1024)
    - app.corpus.embeddings.RateLimitError (signals fallback engagement)
    - app.corpus.embeddings.get_primary_and_fallback (settings-driven selection)
    - app.corpus.ingest.run_ingestion (idempotent orchestrator + telemetry)
    - app.corpus.ingest.build_hnsw_index (idempotent HNSW cosine index)
    - app.corpus.ingest.IngestionResult (dataclass returned to CLI / callers)
    - app.corpus.__main__.main (argparse CLI: --source/--commit/--dry-run/--provider/--rebuild/--build-index)
  affects:
    - ingestion_runs (rows written, one per CLI invocation; status running→succeeded|partial|failed)
    - corpus_documents (rows upserted on (source_path, content_sha256))
    - corpus_chunks (vector(1024) embeddings written via pgvector adapter)
tech_stack:
  added:
    - httpx (Jina HTTPS client — already a copilot dep, reused here)
    - sentence-transformers (local BGE provider; weights cached under ~/.cache/huggingface)
    - numpy (right-pad 384→1024)
    - pgvector.sqlalchemy.Vector (codec registration before raw-SQL chunk inserts)
  patterns:
    - "Primary→fallback embedding provider (mirrors app.copilot.llm._RETRYABLE discipline)"
    - "content_sha256-keyed idempotency (UPSERT-by-hash on corpus_documents)"
    - "Per-document SQLAlchemy transactions so a mid-run provider failure leaves earlier docs intact (REQ-31-09)"
    - "Raw-SQL INSERTs via session.execute(text(...)) — pgvector codec handles list[float] → vector() binding"
    - "Run row written at start with status='running' so audit trail survives an aborted process (T-31-08 mitigation)"
    - "Argparse CLI factored into _build_parser() so tests can call main(['--help']) without spawning subprocesses"
key_files:
  created:
    - backend/app/corpus/ingest.py
    - backend/app/corpus/__main__.py
    - backend/tests/test_corpus_cli.py
  modified:
    - backend/tests/conftest.py
    - backend/tests/test_corpus_ingest_idempotency.py
  preexisting_from_prior_run:
    - backend/app/corpus/embeddings.py (committed in 2df4072; verified, no rewrite)
    - backend/tests/test_corpus_embeddings.py (12 tests, already comprehensive)
decisions:
  - "Reuse salvage/ingest.py.partial verbatim — read against plan spec, matched all 11 behavior bullets and the threat-model mitigations, so no point rewriting"
  - "Replaced the 'real-git' integration test with monkeypatched subprocess.check_output tests — the backend Docker image has no git binary on PATH, and patching subprocess covers both the happy/dirty branches AND the FileNotFoundError fallback for 100% coverage"
  - "Added an ``if __name__ == '__main__'`` guard inside ingest.py that delegates to __main__.py:main so both ``python -m app.corpus`` and ``python -m app.corpus.ingest`` reach the same entry point (plan's acceptance criteria require the latter invocation)"
  - "CLI tests stub SessionLocal, JinaEmbeddingProvider, LocalBgeEmbeddingProvider, and run_ingestion to avoid any network IO or model loading — the orchestrator itself is covered end-to-end against real Postgres in test_corpus_ingest_idempotency.py"
  - "Final ``status`` enum follows RESEARCH §Step 2 (running/succeeded/partial/failed) but collapses partial→failed when any doc fails — keeps REQ-31-09 reading cleanly while still recording how many docs got through"
metrics:
  duration_min: ~30
  tests_added:
    embeddings: 12 (already present from 2df4072; verified, no edits)
    ingest_idempotency: 11 (1 xfail flipped + 10 new)
    cli: 7 (all new)
    delta_this_plan: 18
  total_corpus_tests: 47
  coverage_pct: 100
  coverage_breakdown:
    app/corpus/__init__.py: "3/3 stmts (100%)"
    app/corpus/__main__.py: "37/37 stmts (100%)"
    app/corpus/chunker.py: "87/87 stmts (100%)"
    app/corpus/embeddings.py: "79/79 stmts (100%)"
    app/corpus/ingest.py: "117/117 stmts (100%)"
    app/corpus/walker.py: "146/146 stmts (100%)"
    total: "469/469 stmts (100%)"
  completed_date: 2026-05-13
---

# Phase 31 Plan 04: Corpus ingestion orchestrator + CLI — Summary

Idempotent ingestion pipeline that walks the project's allow-listed sources, chunks them deterministically, embeds them via Jina v3 (with local BGE fallback on rate-limit), and lands them in `corpus_documents` / `corpus_chunks` / `ingestion_runs` with paper-grade telemetry — exposed via a `python -m app.corpus.ingest` CLI.

## Tasks delivered

| # | Task | Status | Commit |
|---|------|--------|--------|
| 1 | Embedding providers (Jina + Local BGE, 1024-dim lock) | verified (no changes) | `2df4072` (pre-existing) |
| 2 | Ingest orchestrator + 11 integration tests + 3 fixtures | done | `198a2ae` |
| 3 | CLI entry (`__main__.py`) + 7 wiring tests | done | `c786bd9` |

## Final coverage report (`app.corpus.*`)

```
Name                       Stmts   Miss  Cover
app/corpus/__init__.py         3      0   100%
app/corpus/__main__.py        37      0   100%
app/corpus/chunker.py         87      0   100%
app/corpus/embeddings.py      79      0   100%
app/corpus/ingest.py         117      0   100%
app/corpus/walker.py         146      0   100%
TOTAL                        469      0   100%
```

47 tests across 7 files, all green. Matches the Phase 30 invariant (`app.copilot.*` at 100%) — re-verified `pytest -q tests/test_copilot_router.py` = 29/29 passing after this plan's changes.

## CLI dry-run output (against `docs/`)

```json
$ docker run --rm --network uni-volunteer-scheduler_default \
    -v $PWD:/repo -v $PWD/backend:/app -w /app \
    uni-volunteer-scheduler-backend \
    python -m app.corpus.ingest --source /repo/docs --dry-run --provider local
{
  "run_id": "dry-run",
  "files_scanned": 6,
  "files_unchanged": 0,
  "files_ingested": 0,
  "files_failed": 0,
  "chunks_emitted": 48,
  "chunks_embedded": 0,
  "status": "succeeded"
}
```

Six markdown documents in `docs/` chunk down to 48 segments at the configured `chunk_size=1024, chunk_overlap=128`. Dry-run writes zero rows to any of the three corpus tables (verified by `test_ingest_dry_run_writes_nothing`).

## Test count summary

| File | Tests | Purpose |
|------|------:|---------|
| `test_corpus_chunker.py` | 6 | Determinism, substring invariant, overlap |
| `test_corpus_walker.py` | 5 | Allow-list, deny-list, source kinds |
| `test_corpus_migration_round_trip.py` | 3 | Alembic up/down/up cycle (plan 02) |
| `test_corpus_logger.py` | 3 | Pre-Phase-31 service logger |
| `test_corpus_embeddings.py` | 12 | Jina + Local + dim lock + threat mitigations |
| `test_corpus_ingest_idempotency.py` | 11 | Idempotency, resumability, fallback, telemetry, HNSW, rebuild |
| `test_corpus_cli.py` | 7 | Argparse, build-index short-circuit, exit codes, wiring |
| **Total** | **47** | |

## Requirements closed by this plan

- **REQ-31-08** — Idempotency on unchanged repo (`test_ingest_idempotent_on_unchanged_repo`).
- **REQ-31-09** — Resumable on provider failure (`test_ingest_resumable_on_provider_failure`, `test_ingest_marks_failed_when_every_doc_fails`).
- **REQ-31-10** — Fallback engages on rate-limit (`test_ingest_fallback_provider_engages`).
- **REQ-31-11** — Embedding dim locked to 1024 (`test_embedding_dim_locked_to_1024` plus pad/truncate guards).
- **REQ-31-12** — HNSW index built idempotently via `--build-index` (`test_build_hnsw_index_is_idempotent`).
- **REQ-31-14** — Full telemetry columns populated on every run (`test_ingest_writes_telemetry_columns_populated`).

## Threat model mitigations confirmed

- **T-31-05 (wrong-dim defence)** — `JinaEmbeddingProvider.embed` raises `ValueError` before any DB write when the server returns a non-1024 vector (`test_jina_provider_rejects_wrong_dim`).
- **T-31-06 (rate-limit DoS)** — Primary→fallback retry path covered (`test_ingest_fallback_provider_engages`); `_embed_with_fallback` re-raises when no fallback is configured (`test_embed_with_fallback_reraises_when_no_fallback`).
- **T-31-07 (API key leakage)** — `JinaEmbeddingProvider.__repr__` strips the key; the key only appears in the `Authorization` header (`test_jina_provider_repr_does_not_leak_api_key`).
- **T-31-08 (audit trail)** — Run row written at start with `status='running'` so an aborted process still leaves a record; covered transitively by all five idempotency tests.

## Deviations from plan

1. **[Rule 1 — Bug] Real-git test replaced with monkeypatched test.** The plan's original `test_git_state_against_real_repo` shelled out to `git init` / `git commit` inside a `tmp_path`, but the backend Docker image has no `git` binary on PATH. Test failed with `FileNotFoundError` and `_git_state`'s dirty-detection branch (lines 63-71 of `ingest.py`) went uncovered, dropping coverage to 98%. Replaced with two tests that monkeypatch `subprocess.check_output`: one covers happy + dirty paths, the other covers the `FileNotFoundError` fallback. Net: full coverage, no dependency on a tool that isn't in the image, and the production behavior is preserved (the function still shells to real `git` in the host environment via the CLI). Commit `198a2ae`.
2. **[Rule 3 — Blocking] Added `__main__` guard to `ingest.py`.** The plan's acceptance criteria mandate `docker compose exec backend python -m app.corpus.ingest --help` exiting 0, but `python -m app.corpus.ingest` runs `ingest.py` as a script, not `__main__.py`. Added a thin `if __name__ == "__main__"` block in `ingest.py` that imports and calls `__main__.main()`, so both `python -m app.corpus` and `python -m app.corpus.ingest` reach the same entry point. Two-line addition under `# pragma: no cover` (it's a process boundary). Commit `c786bd9`.
3. **[Reused salvage]** The prior partial-run executor left a 429-line `ingest.py.partial` plus modified `conftest.py` and `test_corpus_ingest_idempotency.py` in `.planning/phases/31-corpus-pgvector-ingestion/salvage/`. Read against the plan spec, matched all 11 `<behavior>` bullets and the four threat-model mitigations — reused verbatim to save ~20 minutes of re-implementation. The salvage directory remains untracked (still on disk for future audit but not committed; treat as scratch).

No architectural deviations (Rule 4 not triggered).

## Open follow-ups

- **Salvage directory cleanup.** `.planning/phases/31-corpus-pgvector-ingestion/salvage/` contains three files preserved from the prior partial run. They're untracked, not in any commit, and can be deleted once Phase 31 ships. Leaving in place for now in case the verifier wants to audit the diff between salvage and what was committed.
- **Plan 05 (documentation + smoke).** Phase 31 is functionally complete after this plan. Plan 05 still needs: STATE/ROADMAP refresh, the journal lecture under `docs/learning/`, the publication writeup under `docs/documentation/`, and a real end-to-end smoke run (`--commit` against the live dev DB with the real Jina key, then `--build-index`, then a `SELECT … ORDER BY embedding <=> '[…]'::vector LIMIT 5` to confirm the HNSW index is being used).

## Self-Check: PASSED

- `backend/app/corpus/ingest.py` — FOUND (committed in `198a2ae`)
- `backend/app/corpus/__main__.py` — FOUND (committed in `c786bd9`)
- `backend/tests/test_corpus_cli.py` — FOUND (committed in `c786bd9`)
- `backend/tests/test_corpus_ingest_idempotency.py` — FOUND (modified in `198a2ae`)
- `backend/tests/conftest.py` — FOUND (modified in `198a2ae`)
- Commit `198a2ae` — FOUND in `git log --oneline`
- Commit `c786bd9` — FOUND in `git log --oneline`
- `app.corpus.*` coverage = 100% (469/469 statements)
- 47 corpus tests passing, 29 copilot tests still passing (Phase 30 invariant preserved)
