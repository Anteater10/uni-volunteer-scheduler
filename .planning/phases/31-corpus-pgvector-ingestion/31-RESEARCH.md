# Phase 31 — Knowledge corpus + pgvector ingestion — RESEARCH

**Researched:** 2026-05-10
**Owner:** Andy (solo)
**Milestone:** v1.4 — AI Onboarding Copilot
**Confidence:** HIGH on stack/schema, MEDIUM on embedding-provider choice (free-tier reliability), HIGH on chunking strategy.

---

## Project Constraints (from CLAUDE.md + REQUIREMENTS-v1.4.md + Phase 30 SUMMARY)

These are non-negotiable for Phase 31. The planner must honor every line.

| # | Constraint | Source |
|---|---|---|
| C1 | DB/Redis are **not exposed to host**. Ingestion must run inside the compose network (`docker compose run --rm backend ...`) or as a one-off container on `uni-volunteer-scheduler_default`. | CLAUDE.md |
| C2 | Alembic revisions use **slug-form IDs** (e.g. `0019_enable_pgvector_corpus_tables`), not short hex. `env.py` pre-widens `version_num` to VARCHAR(128). | CLAUDE.md |
| C3 | Migrations must be **round-trip safe** (upgrade → downgrade → upgrade clean). Phase 30 (`0018`) verified this. Drop enums and the `vector` extension on downgrade. | CLAUDE.md, Phase 30 SUMMARY |
| C4 | **Free-tier inference only** for primary embedding model + fallback. Paid models forbidden in prod. | REQUIREMENTS-v1.4.md |
| C5 | **No PII tables embedded.** The corpus ingests docs, schemas, and code comments — *not* volunteer rows, signups, users, magic-link tokens, audit logs, or anything that references a real person. | REQUIREMENTS-v1.4.md |
| C6 | **Structured telemetry from day one.** Every ingestion run logs equivalent paper-grade columns to what `copilot_messages` already does. No backfill at Phase 35. | REQUIREMENTS-v1.4.md, Phase 30 |
| C7 | **Two-folder docs rule.** Every function/task produces a `docs/learning/31-…/` lecture AND a `docs/documentation/31-…/` publication writeup before it counts as done. | REQUIREMENTS-v1.4.md |
| C8 | Phase 31 **does not** change the SSE wire format, narrow Phase 30 telemetry columns, or drop below 100% coverage on `app.copilot.*`. | Phase 30 SUMMARY (locked invariants) |
| C9 | Admin feature flag remains the surface gate; ingestion is admin/CLI only (no organizer-facing entry point). | REQUIREMENTS-v1.4.md |

---

## Executive Summary

Phase 31 stands up the retrieval substrate that Phase 32 will query. The work splits cleanly into four layers:

1. **Extension + schema.** Enable `pgvector` via a slug-form Alembic migration on the compose database (the current image is plain `postgres:16` with no extension preinstalled — the docker-compose image must change to `pgvector/pgvector:pg16`). Add `corpus_documents`, `corpus_chunks` (with `embedding vector(N)`), and a paper-grade `ingestion_runs` telemetry table.
2. **Source walker.** A deterministic, idempotent walker over an explicit allow-list of paths (`docs/learning/**`, `docs/documentation/**`, `docs/*.md`, `backend/alembic/versions/*.py` headers, `backend/app/**/*.py` module + function docstrings, top-level frontend component comments). Files outside the allow-list are *not* read. Volunteer-bearing tables (`volunteers`, `signups`, `users`, `magic_link_tokens`, `audit_logs`, `sent_notifications`, `signup_responses`, `custom_answers`, `orientation_credits`, `volunteer_preferences`, `notifications`, `csv_imports`) are explicitly excluded — the walker reads no DB rows.
3. **Chunker + embedder.** Deterministic recursive character splitter (LangChain-style algorithm, hand-implemented, no LangChain dep) with a fixed seed-free policy: same input bytes → same chunks every run. Embeddings via a swappable provider interface; default provider = **Jina Embeddings v3 free tier (1024-dim)**, fallback = **local BGE-small-en-v1.5 (384-dim) via sentence-transformers** running in the backend container. Dimensionality is locked at **1024** for the `vector(N)` column; the fallback right-pads to 1024 with zeros — see "Dimensionality lock-in" below.
4. **Idempotent CLI.** `python -m app.corpus.ingest` reads every allow-listed file, computes a `sha256` content hash per document and per chunk, upserts on `(source_path, content_sha256)`, only re-embeds chunks whose hash changed, and writes one `ingestion_runs` row per invocation with full telemetry. Resumable: a failed run leaves the database in a consistent state because each document is committed in its own transaction.

**Primary recommendation:** Lock dimensionality to 1024, use Jina v3 with a local-BGE fallback, build HNSW index with `vector_cosine_ops` *after* the first bulk ingest, and gate every retrieval-shape decision on the four `ingestion_runs` columns described below so Phase 32 inherits a reproducible corpus.

---

## Domain Decisions (locked at research time — planner should not re-decide)

| # | Decision | Value | Reason |
|---|---|---|---|
| D1 | Postgres image | `pgvector/pgvector:pg16` | Plain `postgres:16` does not include the `vector` extension. The official pgvector image is `pg16-bookworm` based and is a drop-in for the existing volume. `[CITED: hub.docker.com/r/pgvector/pgvector]` |
| D2 | Extension enablement | `CREATE EXTENSION IF NOT EXISTS vector;` inside the upgrade migration; `DROP EXTENSION IF EXISTS vector;` on downgrade — but only if no other table depends on the type (we will be the only consumer in Phase 31). | Standard pgvector docs `[CITED: github.com/pgvector/pgvector]` |
| D3 | Embedding dimensionality | **1024** for the `vector(N)` column | Jina v3 native = 1024; BGE-small fallback padded to 1024; future swap to Voyage 3.5 (default 1024) requires no schema change. Once written, the column type is immutable without a full re-embed. `[VERIFIED: jina.ai/embeddings]` `[VERIFIED: docs.voyageai.com]` |
| D4 | Primary embedding provider | **Jina Embeddings v3** (`jina-embeddings-v3`, 1024-dim, 8192 token context) | Free tier: 100 RPM / 100K TPM / 2 concurrent / 10K req per 60s IP cap. MRL-trained so dimensions are truncatable later. `[VERIFIED: jina.ai/embeddings, 2026-05-10]` |
| D5 | Fallback embedding provider | **Local `BAAI/bge-small-en-v1.5` (384-dim) via `sentence-transformers`** running in the backend container, padded to 1024 | Permanently free, no rate limit, 130MB model. Used when (a) Jina rate-limited, or (b) ingestion run flagged `--offline`. `[VERIFIED: huggingface.co/BAAI/bge-small-en-v1.5]` |
| D6 | NOT OpenRouter for embeddings | Excluded as primary | OpenRouter does host an `/embeddings` endpoint, but the free-tier embedding model lineup is thin and unstable; the chat free-tier shortlist (gpt-oss-120b, llama-3.3-70b) doesn't expose embeddings. Don't tie embedding-pipeline reliability to chat-model availability. `[CITED: openrouter.ai/docs/api/reference/embeddings]` |
| D7 | Index type | **HNSW** with `vector_cosine_ops` | Corpus is small (~thousands of chunks at peak), data arrives incrementally during paper drafting, recall matters more than build time. Industry consensus 2026: HNSW is the safer default for <1M rows. `[CITED: github.com/pgvector/pgvector + dbi-services pgvector DBA guide, March 2026]` |
| D8 | Index timing | Create HNSW index **after** the first bulk ingest, in a separate Alembic data-migration step OR via the ingestion CLI's `--build-index` flag (post-MVP) | HNSW build is faster on populated tables than on empty ones; avoids "index every row at insert time" cost during the first ingest. `[CITED: pgvector README]` |
| D9 | Chunker | Hand-rolled deterministic recursive character splitter: split on `\n\n` → `\n` → `". "` → ` ` → fallback char-slice. Chunk size = **1024 chars**, overlap = **128 chars**. No tiktoken dep. | Deterministic (paper reproducibility), tokenizer-agnostic, runs without network. 1024/128 is the standard mid-range for 8K-context embedders. `[CITED: LangChain RecursiveCharacterTextSplitter docs]` |
| D10 | Idempotency key | `(source_path, content_sha256)` on documents; `(document_id, chunk_index, chunk_sha256)` on chunks. Re-ingestion of an unchanged file is a no-op. | Standard content-addressed ingestion pattern. |
| D11 | Telemetry table | `ingestion_runs` — one row per CLI invocation, paper-grade columns (see schema below) | Mirrors Phase 30's `copilot_messages` discipline: log the raw data once, never backfill. |
| D12 | No retrieval surface | Phase 31 ships **zero** API endpoints | All retrieval/citation work is Phase 32. Phase 31's deliverable is "a row appears in `corpus_chunks`" — verified by SQL + smoke test. |

---

## Recommended Approach

### Step 1 — Migration: `0019_enable_pgvector_corpus_tables`

Slug-form revision after `0018`. Single migration introduces:

1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. `corpus_documents` table.
3. `corpus_chunks` table with `embedding vector(1024)`.
4. `ingestion_runs` table.
5. **No index on `embedding` yet** — built after first bulk ingest, either by a follow-up migration or a `--build-index` invocation of the CLI. This is intentional (D8).

**Round-trip safety:** downgrade drops tables in FK-reverse order, then `DROP EXTENSION IF EXISTS vector;`. Local round-trip test required (matches CLAUDE.md note on enum downgrade bug — be explicit about dropping the extension or upgrade-after-downgrade fails. Using `IF NOT EXISTS` / `IF EXISTS` everywhere makes it safe).

### Step 2 — Schema

```sql
-- corpus_documents: one row per source file
CREATE TABLE corpus_documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_path   TEXT NOT NULL,                      -- repo-relative, POSIX, e.g. "docs/learning/30-…/sse-streaming.md"
  source_kind   TEXT NOT NULL,                      -- 'markdown' | 'python_module' | 'python_function' | 'alembic_migration' | 'frontend_component'
  title         TEXT,                                -- first H1 for markdown; module name for python; etc.
  content_sha256 CHAR(64) NOT NULL,                  -- hash of normalized raw bytes
  byte_size     INTEGER NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE RESTRICT,
  UNIQUE (source_path, content_sha256)              -- idempotency anchor
);

CREATE INDEX ix_corpus_documents_source_path ON corpus_documents (source_path);

-- corpus_chunks: one row per embedding-sized slice
CREATE TABLE corpus_chunks (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   UUID NOT NULL REFERENCES corpus_documents(id) ON DELETE CASCADE,
  chunk_index   INTEGER NOT NULL,                   -- 0-based position within document
  content       TEXT NOT NULL,                       -- the actual chunked text
  content_sha256 CHAR(64) NOT NULL,
  char_start    INTEGER NOT NULL,                   -- offset in source document (deterministic-chunker invariant)
  char_end      INTEGER NOT NULL,
  token_estimate INTEGER,                           -- char/4 heuristic; informational only
  embedding     vector(1024) NOT NULL,
  embedding_model TEXT NOT NULL,                    -- 'jina-embeddings-v3' or 'bge-small-en-v1.5+pad1024'
  embedding_provider TEXT NOT NULL,                 -- 'jina' | 'local-bge'
  ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE RESTRICT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

-- Built AFTER the first bulk ingest, not in this migration:
-- CREATE INDEX ix_corpus_chunks_embedding_hnsw
--   ON corpus_chunks USING hnsw (embedding vector_cosine_ops)
--   WITH (m = 16, ef_construction = 64);

-- ingestion_runs: paper-grade telemetry, one row per CLI invocation
CREATE TABLE ingestion_runs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at          TIMESTAMPTZ,
  status                TEXT NOT NULL DEFAULT 'running',  -- 'running' | 'succeeded' | 'partial' | 'failed'
  git_commit_sha        CHAR(40),                          -- captured from `git rev-parse HEAD` at start
  git_dirty             BOOLEAN NOT NULL DEFAULT false,    -- working tree clean check
  source_globs          JSONB NOT NULL,                    -- allow-list snapshot (for replay)
  embedding_provider    TEXT NOT NULL,                     -- primary used for the run
  embedding_model       TEXT NOT NULL,
  embedding_dim         INTEGER NOT NULL,                  -- 1024
  chunker_version       TEXT NOT NULL,                     -- 'v1-recursive-char-1024-128'
  files_scanned         INTEGER NOT NULL DEFAULT 0,
  files_unchanged       INTEGER NOT NULL DEFAULT 0,        -- hash matched, skipped
  files_ingested        INTEGER NOT NULL DEFAULT 0,
  files_failed          INTEGER NOT NULL DEFAULT 0,
  chunks_emitted        INTEGER NOT NULL DEFAULT 0,
  chunks_embedded       INTEGER NOT NULL DEFAULT 0,        -- chunks_emitted - cache hits
  embedding_api_calls   INTEGER NOT NULL DEFAULT 0,
  embedding_latency_ms_total BIGINT NOT NULL DEFAULT 0,
  embedding_tokens_total INTEGER NOT NULL DEFAULT 0,       -- provider-reported when available
  error_class           TEXT,                              -- if failed
  error_message         TEXT,
  notes                 TEXT
);

CREATE INDEX ix_ingestion_runs_started_at ON ingestion_runs (started_at DESC);
```

**Notes:**
- `corpus_documents.UNIQUE(source_path, content_sha256)` is the idempotency anchor — re-running the CLI with no file changes inserts zero documents and zero chunks; only a fresh `ingestion_runs` row gets written (with `files_unchanged == files_scanned`).
- `corpus_chunks.ingestion_run_id` uses `ON DELETE RESTRICT` — historical chunks survive even if their originating run row is targeted for delete. (We don't expect to delete run rows in practice; this is paper-data hygiene.)
- `ingestion_run_id` on documents uses `ON DELETE RESTRICT` for the same reason.
- Forward declaration: `ingestion_runs` must be created **before** `corpus_documents` and `corpus_chunks` in the migration body because of the FK.

### Step 3 — Source-set walker

**Allow-list (deterministic, alphabetised, configurable but defaulted):**

```python
SOURCE_GLOBS_V1 = [
    "docs/*.md",                                        # top-level repo docs (CCPA, COLLAB, smoke checklist, etc.)
    "docs/learning/**/*.md",                            # every two-folder lecture
    "docs/documentation/**/*.md",                       # every two-folder publication writeup
    "docs/copilot-journal/**/*.md",                     # session journal (v1.4 paper input)
    "backend/alembic/versions/*.py",                    # migration docstrings + revision/down_revision
    "backend/app/**/*.py",                              # module + function docstrings only (not bodies)
    "frontend/src/**/*.{jsx,js,ts,tsx}",                # top-of-file block comments only
    ".planning/REQUIREMENTS-*.md",
    ".planning/ROADMAP.md",
    ".planning/phases/**/*.md",
]

DENY_LIST = [
    "**/__pycache__/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/.venv/**",
    "**/test_*.py", "**/*.test.*", "**/__tests__/**",   # tests are not retrieval-worthy
    "backend/.env*", "frontend/.env*",
    ".planning/notes/private-*",                         # private notes opt-out hook
]
```

**Hard PII deny-by-construction:** the walker reads only files. It opens **no database connections** and reads **no JSON/CSV** for content. PII never enters the pipeline by construction. The deny-list above also rejects test fixtures, which historically have synthetic-but-realistic PII.

**Determinism:** glob results sorted lexicographically before processing; file bytes normalized to LF line endings; trailing whitespace stripped per-line before hashing. Same repo state → same hashes → same chunks → (with deterministic provider) same embedding vectors.

**Python comment extraction:** Use `ast.parse()` → walk `Module`, `ClassDef`, `FunctionDef`, `AsyncFunctionDef`; emit one document per docstring with `source_kind='python_function'` (or `'python_module'`). Bodies excluded. This keeps the corpus dense and signal-heavy.

**Frontend comment extraction:** Read top-of-file block comment only (`/** ... */` or leading `//` block before first non-comment line). Cheap, deterministic, and the convention in this codebase is that top-of-file comments describe intent.

### Step 4 — Chunker

```python
# backend/app/corpus/chunker.py
CHUNKER_VERSION = "v1-recursive-char-1024-128"
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]  # tried in order
```

Algorithm: recursive split on `SEPARATORS` until every piece ≤ `CHUNK_SIZE`, then re-glue with `CHUNK_OVERLAP` characters of overlap between adjacent chunks. Maintain `char_start` / `char_end` invariants so retrieval can quote source location.

**Test contract:**
- `chunk("a" * 1024) == [Chunk(text="a"*1024, start=0, end=1024)]`
- `chunk(text)` called twice with identical input returns identical list (no random seeds, no time-dependent behavior).
- `chunk(text)` for a 4KB markdown doc returns chunks whose concatenation (minus overlap regions) equals the original input.

### Step 5 — Embedder provider interface

```python
# backend/app/corpus/embeddings.py
class EmbeddingProvider(Protocol):
    name: str
    model_id: str
    dim: int  # native dim; padding to 1024 handled downstream
    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]: ...
```

Two implementations:

- `JinaEmbeddingProvider` — POST `https://api.jina.ai/v1/embeddings`, model `jina-embeddings-v3`, returns 1024-dim. Batched, with exponential backoff on 429. Reports `prompt_tokens`.
- `LocalBgeEmbeddingProvider` — `sentence-transformers` SDK, model `BAAI/bge-small-en-v1.5`, native 384-dim, **right-padded to 1024 with zeros** before write. Lazy-loaded on first call to keep cold-start cheap.

Selection: env var `COPILOT_EMBEDDING_PROVIDER=jina|local` (default `jina`). On Jina rate-limit / network failure, the CLI auto-falls-back to `local` for the rest of the run and records both providers in `ingestion_runs.notes`.

**Why padding instead of two embedding columns:** the schema column is locked at `vector(1024)` once written. A future swap to a different 1024-dim model needs no schema change; only re-running ingestion does the work. Padding the 384-dim BGE vectors to 1024 lets the fallback co-exist with primary vectors in the same column without a separate index. Cosine distance between a Jina vector and a BGE-padded vector is **not** meaningful — Phase 32's retrieval layer must filter by `embedding_provider` to keep comparisons honest. The `embedding_provider` column on every chunk row is the affordance Phase 32 will use.

### Step 6 — CLI

```bash
# Inside the compose network — the canonical invocation
docker compose run --rm backend \
  python -m app.corpus.ingest \
    --provider jina \
    --since-commit HEAD~10 \      # optional: only re-walk files changed since this commit
    --dry-run                       # optional: walk + chunk + hash, no embeddings, no DB writes
```

Flags:

- `--provider {jina,local}` (default `jina`)
- `--dry-run` (no DB writes, prints the run summary it *would* have written)
- `--since-commit REF` (only re-walk files git says have changed since `REF` — fast incremental ingestion)
- `--rebuild` (truncate `corpus_chunks` first, re-embed everything; explicit, never default)
- `--build-index` (one-shot: `CREATE INDEX … USING hnsw`; idempotent)

Transaction shape: one transaction per document (so a single failure on chunk-37-of-200 leaves docs 1..N-1 fully committed). Each successful document commits an `ingestion_runs` update with incremented counters (no separate row per doc).

### Step 7 — Phase 32 hooks to expose now

Phase 31 must leave these affordances ready so Phase 32 doesn't need a schema change:

1. **`embedding_provider` column on every chunk.** Phase 32 retrieval filters on this to avoid cross-provider cosine comparisons.
2. **`corpus_documents.source_kind` + `source_path`.** Phase 32 surfaces citation chips that link to source files; both columns must be set on every row.
3. **`char_start`/`char_end` on chunks.** Phase 32 quoting "lines 42–58 of file X" needs exact offsets, not paraphrases.
4. **Stable `(source_path, content_sha256)` idempotency.** Phase 32 caching layer will key off `content_sha256`.
5. **HNSW index built and `ANALYZE`d.** Even though no retrieval ships in Phase 31, the index must exist by phase close so Phase 32's first run is representative.
6. **`ingestion_run_id` foreign key**. Phase 32's "rerank lift" figure will likely group results by ingestion run for paper reproducibility — leave the FK in.

---

## Technical Stack

### New backend dependencies

| Package | Version pin | Purpose | Tier |
|---|---|---|---|
| `pgvector` (Python adapter) | `>=0.3,<1.0` | SQLAlchemy `Vector` type; psycopg2 codec | required |
| `httpx` | already in `httpx==0.27.2` | Jina API calls | reuse existing |
| `sentence-transformers` | `>=3.0,<4` | Local BGE fallback | required |
| `torch` (CPU build) | `>=2.2,<3` (CPU wheel) | sentence-transformers dependency | required, CPU-only |

`torch` CPU wheels add ~200MB to the backend image. Acceptable for a research deployment; gate behind an `[embeddings]` extra in pyproject if image size becomes a concern.

### Docker change

`docker-compose.yml`:

```yaml
db:
-   image: postgres:16
+   image: pgvector/pgvector:pg16
```

Volume `pgdata` is reused (data format identical). After image swap, the `0019` migration runs `CREATE EXTENSION vector;` on `uni_volunteer` and on the test DB.

**Migration order for the human:**
1. Update `docker-compose.yml`.
2. `docker compose pull db && docker compose up -d db`.
3. `alembic upgrade head` runs `0019`.

If the image swap is forgotten, `0019` fails at `CREATE EXTENSION vector` with a clear error — that's the right failure mode.

---

## Validation Architecture (Nyquist-style, per project convention)

### Test framework

| Property | Value |
|---|---|
| Framework | pytest (existing) |
| Test DB | `test_uvs` on the compose `db` service |
| Quick run | `pytest backend/tests/test_corpus_*.py -x` |
| Full suite | per CLAUDE.md docker incantation, all `pytest -q` |
| Coverage gate | 100% on `app.corpus.*` (mirrors `app.copilot.*` gate) |

### Phase 31 requirements → test map

| ID | Behavior | Test type | Automated command |
|---|---|---|---|
| REQ-31-01 | Migration `0019` upgrade clean on test DB | migration | `pytest backend/tests/test_corpus_migration.py::test_upgrade_creates_extension_and_tables` |
| REQ-31-02 | Migration `0019` upgrade → downgrade → upgrade round-trip clean | migration | `pytest …::test_round_trip_clean` |
| REQ-31-03 | Chunker is deterministic: same input → same output | unit | `pytest …::test_chunker_deterministic` |
| REQ-31-04 | Chunker preserves char_start/char_end invariants | unit | `pytest …::test_chunker_offsets_consistent` |
| REQ-31-05 | Walker excludes PII tables by construction (no DB cursor opened) | unit (introspection) | `pytest …::test_walker_opens_no_db_connection` |
| REQ-31-06 | Walker excludes deny-list paths (.env, node_modules, test_*) | unit | `pytest …::test_walker_respects_deny_list` |
| REQ-31-07 | Walker is deterministic: stable ordering of glob results | unit | `pytest …::test_walker_deterministic_order` |
| REQ-31-08 | Idempotency: re-running on unchanged repo emits 0 new documents, 0 new chunks | integration | `pytest …::test_ingest_idempotent` |
| REQ-31-09 | Partial-failure resumability: simulated mid-run Jina 503 leaves committed docs intact | integration | `pytest …::test_ingest_resumable_on_provider_failure` |
| REQ-31-10 | Fallback provider engages on Jina rate-limit; ingestion_runs.notes records both providers | integration | `pytest …::test_fallback_provider_engages` |
| REQ-31-11 | Embedding dimensionality is exactly 1024 (Jina native or BGE-padded) | unit | `pytest …::test_embedding_dim_locked_to_1024` |
| REQ-31-12 | HNSW index builds and is used by `EXPLAIN` for a sample cosine query | integration | `pytest …::test_hnsw_index_used` |
| REQ-31-13 | Real smoke: one full ingest against the live repo populates ≥ N documents | smoke (manual + CI) | `docker compose run --rm backend python -m app.corpus.ingest --provider local` |
| REQ-31-14 | `ingestion_runs` row records all paper-grade columns populated | integration | `pytest …::test_telemetry_columns_populated` |

### Sampling rate

- **Per task commit:** quick run (`pytest backend/tests/test_corpus_*.py -x`)
- **Per phase merge:** full suite green + REQ-31-13 manual smoke
- **Phase gate (before `/gsd-verify-work`):** all 14 above green, two-folder docs written

### Wave 0 gaps (planner must address before Wave 1)

- [ ] `backend/tests/test_corpus_migration.py` — does not exist
- [ ] `backend/tests/test_corpus_chunker.py` — does not exist
- [ ] `backend/tests/test_corpus_walker.py` — does not exist
- [ ] `backend/tests/test_corpus_ingest.py` — does not exist
- [ ] `backend/tests/conftest_corpus.py` — shared fixtures (temp git repo, fake provider, in-memory walker)
- [ ] Backend image rebuild to include `sentence-transformers` + `pgvector` + `torch` CPU wheel — must complete before any test runs
- [ ] `pgvector/pgvector:pg16` image swap on `db` service — must complete before the migration test runs

---

## Common Pitfalls

### Pitfall 1: forgetting the docker image swap
**What goes wrong:** Migration fails at `CREATE EXTENSION vector` with `ERROR: could not open extension control file`.
**Why it happens:** Plain `postgres:16` doesn't bundle the extension; only `pgvector/pgvector:pg16` (and a few cloud-managed flavors) do.
**Avoid:** First task in the phase must be the image swap and a verification `psql -c '\dx'` query.

### Pitfall 2: enum / extension downgrade leak
**What goes wrong:** Round-trip test (`upgrade → downgrade → upgrade`) fails with `DuplicateObject: extension "vector" already exists`.
**Why it happens:** CLAUDE.md flags this exact bug for enums in the existing codebase. Same trap applies to extensions: `CREATE EXTENSION vector` without `IF NOT EXISTS` after a partial downgrade.
**Avoid:** `CREATE EXTENSION IF NOT EXISTS vector` in upgrade; `DROP EXTENSION IF EXISTS vector` in downgrade. Add round-trip test.

### Pitfall 3: dimensionality lock-in regret
**What goes wrong:** Three months in, you want Voyage-3-large at 2048 dim → schema change requires re-embedding everything.
**Why it happens:** `vector(N)` is a fixed-width type; you can't widen without a column drop.
**Avoid:** Lock at 1024 now (D3). All free-tier and most paid models support 1024. If you ever go higher, do it as a new column (`embedding_v2 vector(2048)`) backfilled in place.

### Pitfall 4: cross-provider cosine comparisons
**What goes wrong:** Phase 32 retrieves top-k by cosine; some chunks were embedded by Jina, others by BGE-padded. Results look noisy.
**Why it happens:** Different embedding spaces aren't cosine-comparable; padding zeros don't change that.
**Avoid:** Phase 32 query layer must filter `WHERE embedding_provider = $1`. The `embedding_provider` column on every chunk row is the affordance.

### Pitfall 5: HNSW build on empty table is slow per-row
**What goes wrong:** Building the index *before* the first bulk ingest means every `INSERT` pays a tree-rebalance cost.
**Why it happens:** Pgvector HNSW is incremental but bulk-load + post-index is materially faster.
**Avoid:** D8 — build the index after the first ingest, via `--build-index` flag.

### Pitfall 6: smuggling PII via "innocent" docs
**What goes wrong:** A Playwright test fixture (`tests/fixtures/volunteers.json`) is markdown-adjacent and gets walked.
**Why it happens:** Test fixtures often contain real-looking PII that someone added during debugging.
**Avoid:** Deny-list explicitly excludes `**/test_*`, `**/__tests__/**`, `**/*.test.*` (REQ-31-06). The walker reads no JSON for content (only `.md` and `.py`).

### Pitfall 7: paper-grade telemetry skipped on success path
**What goes wrong:** Engineer writes the run-row insert only on failure, so successful runs leave no audit trail.
**Why it happens:** Pre-Phase 30 instinct ("logs are for errors").
**Avoid:** Every CLI invocation writes one row at start (`status='running'`), updates counters per document, and stamps `completed_at` + `status='succeeded'` at end. Failed runs flip `status='failed'`. Phase 35 will diff runs to track corpus evolution.

---

## Open Questions for Planner

1. **Backend image growth.** Adding `torch` CPU + `sentence-transformers` adds ~200MB. Acceptable for this milestone, but planner should confirm there's no CI image-size budget being violated. (Phase 30 image was lean.)
2. **Should `0019` ship in two migrations or one?** Splitting (`0019_enable_pgvector`, `0020_corpus_tables`) is more orthodox. Combining is simpler and still round-trip safe. Recommend **one migration** unless the planner sees a reason to separate. The HNSW index ships as `0020` (run after first ingest) regardless.
3. **`docs/copilot-journal/**` inclusion.** Andy's memory flags this as session journaling for paper writeup. Including journal entries in the corpus means the copilot can answer "when did we decide X?" — high paper value. Confirm planner wants this in v1; easy to remove later.
4. **Frontend comment harvest precision.** Top-of-file block comments are the conservative version. The planner can choose to also extract JSDoc block comments above exported functions. Recommend **defer** — minimal yield, more complexity.
5. **Should `ingestion_runs.git_commit_sha` be `NOT NULL`?** Recommend `NOT NULL` — paper reproducibility hard requirement. Planner confirms.
6. **STATE.md drift.** The `## Next Action` block in `.planning/STATE.md` still says Phase 31 is "conversation history + session list UI" — that was an earlier plan, since superseded by ROADMAP.md. Planner must refresh STATE.md at phase open so the harness doesn't pick up the stale description.

---

## Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Jina free tier becomes unreliable mid-phase | Medium | Local BGE fallback already in scope (D5); no schema dependency on provider. |
| R2 | Backend image rebuild breaks unrelated CI | Medium | Stage the image change in its own task with full test suite as the gate. |
| R3 | Docker image swap (`postgres:16` → `pgvector/pgvector:pg16`) causes data-volume incompatibility | Low | Both images are based on the same upstream `postgres:16`; `pgdata` volume is binary-compatible. Verify on a throwaway copy of the volume first if paranoid. `[CITED: pgvector/pgvector Dockerfile]` |
| R4 | Chunker bug silently shifts char_start/char_end → bad citations in Phase 32 | High (paper) | REQ-31-04 explicitly tests offset invariants. Property-based test recommended (Hypothesis lib already common in pytest). |
| R5 | Determinism breaks under different glob ordering on different OSes | Low | Walker sorts results before processing. Test on Linux container only (the canonical environment). |
| R6 | "Two-folder docs rule" forgotten on a sub-task | Medium | Definition-of-Done gate: phase doesn't merge until both folders have a `31-*/` entry per implementation task. |
| R7 | Phase 31 STATE.md "next action" line is stale | Low | Planner updates STATE.md at phase open; ROADMAP/REQUIREMENTS are authoritative. |

---

## Sources

### Primary (HIGH confidence)
- pgvector official README and Docker docs — index types, operator classes, image tags. `[CITED: github.com/pgvector/pgvector, hub.docker.com/r/pgvector/pgvector]`
- Jina Embeddings v3 official page — free-tier limits, 1024 native dim, MRL. `[CITED: jina.ai/embeddings, 2026-05-10]`
- BAAI bge-small-en-v1.5 Hugging Face model card — 384 dim, 130MB, free local use. `[CITED: huggingface.co/BAAI/bge-small-en-v1.5]`
- Voyage AI docs — supported `output_dimension` values (2048, 1024, 512, 256). Establishes that 1024 is a portable choice. `[CITED: docs.voyageai.com]`
- Project codebase: `backend/app/models.py`, `backend/alembic/versions/0018_*.py`, `backend/app/config.py`, `backend/app/copilot/llm.py`, `docker-compose.yml`, `CLAUDE.md`, REQUIREMENTS-v1.4.md, ROADMAP.md, Phase 30 SUMMARY.

### Secondary (MEDIUM confidence, cross-verified)
- "pgvector: a guide for DBA — Part 2: Indexes (update March 2026)" (dbi-services) — HNSW vs IVFFlat selection in 2026, default-to-HNSW reasoning. `[CITED: dbi-services.com]`
- "IVFFlat vs HNSW in pgvector" (DEV community, 2026) — `m=16, ef_construction=200` starter config. `[CITED: dev.to]`
- OpenRouter docs — embeddings endpoint exists but free-tier embedding lineup is unstable; rationale for D6. `[CITED: openrouter.ai/docs/api/reference/embeddings]`

### Tertiary (LOW confidence, training-data assertions to validate during planning)
- `[ASSUMED]` Local BGE-small inference latency in the backend container is acceptable for ~1K chunks (~ a few seconds total). Validate empirically in REQ-31-13 smoke.
- `[ASSUMED]` `torch` CPU wheel is import-safe in the existing backend image's Python 3.11+ runtime. Validate by image rebuild as the first phase task.
- `[ASSUMED]` Hand-rolled deterministic recursive chunker is small enough (<150 LOC) to keep in-tree without pulling LangChain. Confirmed by inspecting LangChain's `RecursiveCharacterTextSplitter` (it's small).

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | Backend container Python runtime supports `torch` CPU wheel without code changes | Stack | Medium — first task is image rebuild; failure surfaces immediately. |
| A2 | Jina free-tier rate limits (100 RPM / 100K TPM) are sufficient for a one-shot ingest of <2000 chunks | CLI design | Low — fallback to local-BGE handles overflow. |
| A3 | `pgvector/pgvector:pg16` is binary-compatible with the existing `pgdata` volume from `postgres:16` | Risks | Low — same Postgres major version; pgvector adds an extension, doesn't change page format. |
| A4 | The chunker producing identical chunks across runs is sufficient for "paper reproducibility" — i.e. Jina v3 itself is deterministic per request | Chunking | Medium — Jina's API is not documented as bit-deterministic across calls (most embedding APIs aren't). Mitigation: record `content_sha256` per chunk so any retrieval is reproducible from cache hits regardless. |

---

## Phase Requirements (consolidated for planner)

| ID | Description | Research support |
|---|---|---|
| REQ-31-A | Enable pgvector via Alembic in slug-form revision, round-trip safe | Step 1, Pitfall 2 |
| REQ-31-B | Add `corpus_documents`, `corpus_chunks (embedding vector(1024))`, `ingestion_runs` tables | Step 2 |
| REQ-31-C | Deterministic source walker with explicit allow-list, no DB reads, no PII paths | Step 3 |
| REQ-31-D | Deterministic recursive char chunker, 1024/128, char-offset invariants | Step 4, REQ-31-03/04 |
| REQ-31-E | Pluggable embedding provider — Jina v3 primary, local BGE-small (padded to 1024) fallback | Step 5 |
| REQ-31-F | Idempotent ingestion CLI runnable inside the compose network with `--dry-run`, `--since-commit`, `--rebuild`, `--build-index` flags | Step 6 |
| REQ-31-G | One `ingestion_runs` row per CLI invocation with all paper-grade columns populated | Step 2 telemetry, REQ-31-14 |
| REQ-31-H | HNSW index built post-ingest with `vector_cosine_ops` | D7/D8 |
| REQ-31-I | 100% coverage on `app.corpus.*` (matches Phase 30 invariant) | Validation Architecture |
| REQ-31-J | Two-folder docs (learning + documentation) for every implementation task | C7 |
| REQ-31-K | Phase 32 hooks present: `embedding_provider` column, `source_kind`/`source_path`, `char_start`/`char_end`, HNSW index, `ingestion_run_id` FK | Step 7 |

---

## RESEARCH COMPLETE
