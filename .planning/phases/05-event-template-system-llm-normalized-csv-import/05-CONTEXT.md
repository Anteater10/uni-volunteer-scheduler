---
name: Phase 5 Context
description: Event template system + LLM-normalized CSV import — decisions locked autonomously (BLOCKED on real CSV sample)
type: phase-context
---

# Phase 5: Event Template System + LLM-Normalized CSV Import — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning (with flagged blocker — see specifics)
**Mode:** Autonomous (recommended defaults selected by Claude)

<domain>
## Phase Boundary
An organizer uploads a raw Sci Trek CSV; a two-stage pipeline normalizes it via an LLM (stage 1, creative) then validates it deterministically (stage 2, strict). The user sees a preview with row-level validation, can't commit low-confidence rows without resolution, and on commit the whole batch is inserted atomically or rolled back. Every raw→normalized pair is logged to a corpus file. The `module_templates` stub from phase 4 is promoted to a full CRUD resource here.

Success criteria (ROADMAP.md):
1. Templates CRUD via admin UI; seeded on fresh deploy.
2. Preview within 30s.
3. Low-confidence rows can't be committed without manual resolution.
4. Atomic commit / rollback on failure.
5. Raw→normalized corpus logged for eval.
</domain>

<decisions>
## Implementation Decisions (locked)

### Module templates — full schema
Extend phase 4's stub with:
- `default_capacity INT NOT NULL DEFAULT 20`
- `duration_minutes INT NOT NULL DEFAULT 90`
- `materials TEXT[] NOT NULL DEFAULT '{}'`
- `description TEXT`
- `metadata JSONB NOT NULL DEFAULT '{}'`
- `deleted_at TIMESTAMPTZ` (soft delete)

### LLM stage 1 — extraction
- **Model:** `gpt-4o-mini` via OpenAI API (configurable via `OPENAI_MODEL` env var).
- **Instructor + Pydantic structured output** (`instructor` library) — enforces schema at the SDK layer.
- Schema: `ExtractedEvents = list[ExtractedEvent(module_slug, location, start_at, end_at, capacity, instructor_name, _confidence: float 0-1)]`.
- Few-shot examples: 2-3 hand-crafted examples inline in the prompt (placeholder `TODO(data)` until Hung provides a real CSV sample).
- Token budget: 8k max output; single-shot for up to 40 rows, chunked above that.
- Cost ceiling: log estimated cost per import; refuse imports estimated > $5 with a clear error.

### LLM stage 2 — deterministic importer
- Takes stage-1 JSON, validates against the live `module_templates` table (slug must exist or a new template must be proposed in the same batch).
- Checks time collisions (existing events overlapping the same location + time).
- Marks rows `low_confidence` if `_confidence < 0.85` OR module_slug is unknown OR fields are missing.
- Returns a preview payload: `{rows: [{status, normalized, warnings[]}], summary: {to_create, to_review, conflicts}}`.

### Preview UI
- `/admin/import` page. Upload CSV → POST to `/admin/imports`, which kicks Celery task and returns an `import_id`.
- Frontend polls `/admin/imports/{id}` every 2s until `status == "ready"`.
- Preview table highlights `low_confidence` rows in amber; each row is editable (edit normalized fields inline before commit).
- "Commit" button disabled while any low-confidence row remains unresolved.

### Atomic commit
- `POST /admin/imports/{id}/commit` opens a single transaction, inserts all events + slots, rolls back on any constraint violation.
- On success: returns `{created_count, events[]}`. On failure: returns `{error, failing_row_index, reason}`.

### Corpus logging
- Every successful stage-1 run appends `{timestamp, raw_csv_hash, raw_csv_bytes, normalized_json, model, confidence_distribution}` to `backend/data/corpus/csv_imports.jsonl`.
- Raw CSV bytes are stored verbatim for future eval (not PII — CSVs contain event data only).
- File is `.gitignore`'d; a nightly cron (future) can sync it to object storage.

### Admin template CRUD
- `GET /admin/module-templates` — list
- `POST /admin/module-templates` — create (unique slug)
- `PATCH /admin/module-templates/{slug}` — update
- `DELETE /admin/module-templates/{slug}` — soft delete (sets `deleted_at`)
- Frontend page `/admin/templates` uses a table with inline edit.

### Seeding
- A new Alembic data migration or `seed_templates.py` script populates `TODO(data)` templates. Hung replaces with real Sci Trek modules on the laptop.

### Claude's Discretion
- Exact few-shot examples (TODO(data) until Hung provides CSV).
- Column-detection heuristics if CSV headers are inconsistent.
- Retry strategy on LLM timeouts (planner picks: exponential backoff, max 2 retries).
</decisions>

<code_context>
- No `instructor` or `openai` dep in `backend/pyproject.toml` yet — planner adds.
- Celery already present from phase 0; Celery task `tasks/import_csv.py` runs stage 1 async.
- `.env.example` will need `OPENAI_API_KEY` added; real key lives in Hung's local `.env` — marked `TODO(secret)`.
</code_context>

<specifics>
## Specific Requirements / BLOCKER flag
- **ROADMAP open-question gate:** A real past-year Sci Trek CSV sample is required before the LLM prompt and few-shot examples can be written. **Hung has pre-authorized frontend placeholder work, but this phase's LLM stage 1 needs real data.** Per `.planning/remote-run-instructions.md`, this is a structural decision I can't resolve with a placeholder — the phase will PAUSE during planning if the planner determines stage-1 prompt authoring requires the real CSV.
- **Mitigation:** Plan stages the work so stage-2 validator, schema, CRUD, preview UI, atomic commit, and corpus logging are ALL implementable without the real CSV — only stage-1 prompt + eval dataset require it. Planner should split plans so stage-1 ends up as the last plan, and we proceed with the rest autonomously.
- Cost ceiling: $5/import hard refuse.
- `low_confidence = confidence < 0.85`.
</specifics>

<deferred>
- Multi-model ensemble (gpt-4o + claude) — out of scope.
- Fine-tuned extraction model — out of scope.
- Bulk template upload via CSV — out of scope (admin UI is one at a time).
</deferred>

<canonical_refs>
- `.planning/ROADMAP.md` — Phase 5 success criteria + open-question gate
- `.planning/phases/04-prereq-eligibility-enforcement/04-CONTEXT.md` — stub module_templates schema
- Instructor library: https://python.useinstructor.com/
- OpenAI structured outputs: https://platform.openai.com/docs/guides/structured-outputs
</canonical_refs>
