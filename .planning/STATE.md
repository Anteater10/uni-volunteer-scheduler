---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: milestone
status: in-progress
last_updated: "2026-05-23T18:00:00.000Z"
last_activity: 2026-05-23 — Phase 33 shipped (tool calling + ReAct + PII tool boundary — paper contribution #1). 12 tools (8 read + 4 write) flow through a uniform invoke() that chains a three-layer boundary (schema filter / role scope / redactor) plus an audit-log writer; write tools gated behind a TTL confirmation card. Agent loop (`run_turn`) caps at 6 tool calls + 2 malformed-response retries. Adversarial suite green at 35/35 across 7 categories (Cat 1–3 100% at 100% pass bar; Cat 4–7 100% at ≥80% pass bar). New audit table `copilot_tool_calls` via Alembic `0021`. Agent loop wired into /api/copilot/chat behind `COPILOT_AGENT_LOOP_ENABLED` (defaults off; Phase 30/32 token-stream behavior preserved). Backend copilot tests: 99 agent unit + 35 adversarial. Frontend copilot tests: 42 (ConfirmationCard, ToolCallIndicator, drawer integration). Phase 34 (memory + multi-turn / conversation summarisation) is the next action.
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 25
  completed_plans: 18
  percent: 75
---

# Project State

**Project:** Uni Volunteer Scheduler (UCSB Sci Trek)
**Initialized:** 2026-04-08
**Mode:** Autonomous · Standard granularity · Sequential execution · Research/Plan-Check/Verifier all ON
**Deadline:** Phase 30 before graduation; full milestone + paper by week 16.

## Current Position

Milestone: **v1.4 AI Onboarding Copilot** — in progress
Phase: 33 (Tool calling + ReAct + PII tool boundary) — ✅ shipped
Branch: `feature/v1.4-phase-33-tool-calling-react` — ready to merge
**Last activity:** 2026-05-23 — Phase 33 shipped (paper contribution #1). 12 tools (8 read + 4 write) registered through a `Tool` dataclass + role-scoped registry; uniform `invoke()` chains the three-layer boundary (schema filter → role scope → redactor) and writes the audit log. Write tools gated behind a TTL `_PENDING` confirmation store and surfaced via `ConfirmationCard` + a `POST /api/v1/copilot/confirm/{call_id}` endpoint. Agent loop (`run_turn`) caps at 6 tool calls + 2 malformed-response retries; SSE event taxonomy is strictly additive to Phase 30 (`tool_use` / `tool_result` / `confirmation_required`). Adversarial 35/35 across 7 categories; CSV at `docs/documentation/33-tool-calling-react/adversarial-pass-rates.csv`. Audit log table `copilot_tool_calls` via Alembic `0021`. See `.planning/phases/33-tool-calling-react/SUMMARY.md` for full handoff to Phase 34.

**2026-05-20 — Phase 32 Plan 06 shipped (citation chips frontend):** `useCopilotStream` consumes the new `event: meta` SSE branch additively (Phase 30 token/done/error untouched). New `CitationChip` (`[N] filename` + tooltip + keyboard-accessible) and `CitationPanel` (side-panel modal, "Source consulted" header, conditional external link) components. Per-message citation snapshot keeps multi-turn history coherent. New `e2e/copilot-citations.spec.js` covered by all 6 Playwright projects via the default testMatch glob (Case A — no CI workflow edit). 243/243 vitest green, chromium Playwright green. Paired learning + publication docs (126 + 187 lines).

**2026-05-20 — Phase 32 Plan 07 shipped (RAGAS rerank-lift harness):** Offline harness at `scripts/eval_rerank_lift.py` drives the Phase 32 pipeline twice (rerank ON / OFF) over a frozen 30-question testset and emits `docs/documentation/32-rag-retrieval/rerank-lift.{csv,png}` with the paper-locked column header `metric,rerank_off,rerank_on,lift`. Eval deps pinned (`ragas==0.4.3`) in a separate `backend/requirements-eval.txt` so the request-path image stays slim (constraint C6). CI smoke (`backend/tests/test_eval_script_smoke.py`) guards the artifact shapes via `pytest.importorskip("ragas")` — 2 passed / 1 skipped. `scripts/generate_testset.py` drives RAGAS `TestsetGenerator` in batches of 5 with sleeps (Pitfall 4). Paired learning + publication docs (124 + 152 lines). Real CSV/PNG values + curated/synthetic testset population are deferred to Andy's offline run (checkpoint:human-action per plan); placeholders ship with correct shape so the figure path and CI guard work end-to-end.

## Current Status

- ✓ v1.0 phases 0–7 shipped (2026-04-08) — drifted from no-accounts thesis, then realigned in v1.1
- ✓ v1.1 phases 08–13 shipped (2026-04-10) — account-less realignment + admin shell + 16/16 Playwright E2E green
- ✓ v1.2-prod phases 14–20 shipped (2026-04-16) — production-ready by role (participant, admin, organizer) + cross-role integration
- ✓ v1.3 phases 21, 22, 23, 24, 25, 26, 28, 29 shipped (2026-04-17) — feature expansion complete
- ⏸ Phase 27 (SMS reminders + no-show nudges, AWS SNS) — **deferred** to a later milestone (TCPA + flag-gated; not a blocker)
- ▶ v1.4 (AI Onboarding Copilot) — Phases 30 + 31 + 32 + 33 shipped; phases 34–38 ahead

**v1.3 phase outcomes (9 phases, 21–29):**

- ✓ Phase 21: Orientation credit engine — `(volunteer, module_family)` credit table + organizer override + admin grant/revoke
- ✓ Phase 22: Custom form fields — organizer-editable signup questions with module-template defaults; CSV export
- ✓ Phase 23: Recurring event duplication — admin "Duplicate to weeks N…M" with atomic commit + conflict warning
- ✓ Phase 24: Scheduled reminder emails — Celery Beat kickoff + 24h + 2h with idempotency, opt-out, quiet hours
- ✓ Phase 25: Waitlist + auto-promote — public, organizer, admin surfaces; cancel-triggers-promote atomic path
- ✓ Phase 26: Broadcast messages — organizer/admin → email all signups, rate-limited + audited + dedup
- ⏸ Phase 27: SMS reminders + no-show nudges — **deferred** (AWS SNS, TCPA-gated; revisit post-v1.4)
- ✓ Phase 28: QR check-in — **shipped with deviation:** organizer-displayed event-QR + volunteer self-check-in by email (PLAN/SUMMARY written retroactively 2026-05-08; see `.planning/phases/28-qr-check-in/`)
- ✓ Phase 29: Slot swap + signup locking + past-event hiding + cross-feature integration

**Out of scope (carryover for later milestones):** UCSB production deployment, payments/donations, SSO, multi-tenant, branding, bulk QR sticker sheets.

## Next Action

Merge Phase 33 to `main`, then start Phase 34 (Memory + multi-turn context — conversation
summarisation and token-budget management). Phase 34 inherits the Phase 33 agent loop's SSE
event taxonomy (`tool_use` / `tool_result` / `confirmation_required`), the audit log table
`copilot_tool_calls`, the three-layer boundary (which memory recall must re-apply at read
time so cached tool results don't bypass redaction), and the `COPILOT_AGENT_LOOP_ENABLED`
flag (Phase 34 should not flip the default — ship behind the same flag until Phase 37).
Locked invariants for Phase 34: do not touch the Phase 33 tool surface (additive new tools
only — no rename/reshape of `list_modules`, `get_module_roster`, etc.), do not change the
`_PENDING` confirmation contract (Phase 37 swaps the backing store; the interface stays
stable), keep the Phase-30 SSE `token` / `done` / `error` taxonomy additive-only, and re-
apply the redactor whenever previously-retrieved tool data is surfaced from memory.

**v1.1 closing notes (still relevant for v1.2-prod handoff):**

- Test-helper backend endpoints (`seed-cleanup`, `event-signups-cleanup`) gated by `EXPOSE_TOKENS_FOR_TESTING=1` enable idempotent Playwright reruns despite UNIQUE(volunteer_id, slot_id) constraint
- Rate-limit bypass when `EXPOSE_TOKENS_FOR_TESTING=1` is required so parallel Playwright workers (sharing localhost IP) don't exhaust the 10/min limit
- Slot capacity 200 for E2E events prevents exhaustion across 4 parallel workers

## Accumulated Context

### v1.2-prod sequencing risks (flagged in ROADMAP.md notes)

- **Admin and organizer share code surface** — both pillars touch event create/edit and magic-link infrastructure. Phase 19 (organizer) waits until Phase 18 (admin LLM imports) lands so the two worktrees don't fight over shared files. Deliberate sequencing choice; alternative is more merge conflicts than two devs can absorb in a 6-week window.
- **`frontend/src/lib/api.js`, `frontend/src/App.jsx` (routes), and shared component files are PR-only edits** — must be called out in COLLAB-03 file-ownership table to keep the participant + admin worktrees from colliding during the parallel Phase 15 + 16 window.
- **Phase 18 (LLM CSV import) is the milestone's biggest net-new feature.** Everything else is audit + polish + targeted fills. If Phase 18 slips, plan a focused recovery rather than spreading the LLM work across other phases.

### Stage 0 findings (still relevant for v1.2-prod phases)

- Alembic chain uses slug-style revision IDs; `alembic/env.py` pre-widens `version_num` to VARCHAR(128). Do not regress.
- ~~Enum downgrade leak~~ RESOLVED in Phase 08 — `2465a60b9dbc_initial_schema.py` now drops `signupstatus`, `userrole`, `notificationtype`, `privacymode`. Round-trip gate passes.
- Docker stack quirk: db/redis not exposed to host. Tests run via one-off container on `uni-volunteer-scheduler_default` network. See CLAUDE.md.
- Phase 5.07 LLM CSV extraction: **NO LONGER BLOCKED** — Andy holds the CSV file. Ships in Phase 18.

### Phase 08 handoff for Phase 09 / 12 (historical, still relevant for context)

- App does **not boot** cleanly until Phase 09 wires the new volunteer-keyed code paths.
- Test baseline: 76 passed / 74 skipped / 0 failed (was 185/185). The 74 skips are runtime breakages at `signup.user` sites, marked with "Phase 09" reasons.
- `backend/app/schemas.py` keeps `PrereqOverrideRead` as stubs for `admin.py` compatibility — Phase 12 removes both.
- `backend/app/services/prereqs.py` has a try/except import guard for the same reason.
- `SlotFactory.slot_type` defaults to `SlotType.PERIOD`; Slot model has no `server_default` on `slot_type` (migration handles it).
- See `08-SUMMARY.md` + `08-VERIFICATION.md` for the full handoff list.

### v1.0 surface map

- **Retired in v1.1:** Phase 2 account-confirmation flow (repurposed magic-link infra), Phase 4 prereq enforcement, Phase 7 override UI, student login/register frontend pages.
- **Lingering for v1.2-prod cleanup:** `Overrides` admin sidebar nav item — closes the v1.1 Phase 12 retirement loop. ADMIN-01 in Phase 16.
- **Keeping:** Phase 0 schema scaffolding, Phase 1 Tailwind design system + components, Phase 3 check-in state machine + organizer roster, Phase 5 CSV template import (deterministic parts), Phase 6 notifications, Phase 7 audit log / analytics / CCPA export.

## Key Decisions Log

See `.planning/PROJECT.md` → Key Decisions.

## Open Questions

See `.planning/PROJECT.md` → Open Questions and `.planning/REQUIREMENTS-v1.2-prod.md` → Open Questions (to resolve during planning).

**Phase 31 outcome (knowledge corpus + pgvector ingestion):**

- ✓ pgvector enabled via `0019_enable_pgvector_corpus_tables` (round-trip safe)
- ✓ Three tables: `corpus_documents`, `corpus_chunks` (with `vector(1024)`), `ingestion_runs`
- ✓ Deterministic chunker (`v1-recursive-char-1024-128`) + allow-list walker (no DB, no PII)
- ✓ Embedding providers: Jina v3 primary + BGE-small fallback (1024-dim locked)
- ✓ Idempotent CLI: `python -m app.corpus.ingest --source <dir> [--commit | --dry-run | --rebuild | --build-index]`
- ✓ Paper-grade telemetry: `ingestion_runs` row per CLI invocation with all 22 columns populated
- ✓ HNSW index built post-ingest with `vector_cosine_ops` (provably used by planner — `test_corpus_hnsw_index.py`)
- ✓ Real smoke against the running compose stack: 619 documents / 4731 chunks (status=succeeded, dim=1024)
- ✓ 100% coverage on `app.corpus.*` (matches Phase 30 invariant for `app.copilot.*`)
- ✓ 48 corpus tests green
- ✓ 8 docs (4 lectures + 4 publication writeups under `docs/learning/31-…/` and `docs/documentation/31-…/`)

**Phase 32 outcome (RAG retrieval — hybrid + rerank + citations):**

- ✓ Alembic `0020_add_corpus_chunk_fts_column` — additive tsvector GENERATED column + GIN index (round-trip safe)
- ✓ Hybrid retrieval (`app.copilot.retrieval`): dense + FTS + RRF in one SQL CTE; per-provider invariant pushed into SQL on both branches
- ✓ Local CrossEncoder rerank (`BAAI/bge-reranker-base`); no external rerank API (C6 honored)
- ✓ `event: meta` SSE frame fires before first token; strictly additive to Phase-30 taxonomy
- ✓ `GET /api/v1/copilot/citations/{chunk_id}` click-through endpoint with UUID validation
- ✓ Frontend: `CitationChip` + `CitationPanel` + `useCopilotStream` meta branch; per-message snapshot; Playwright spec across all 6 projects
- ✓ RAGAS rerank-lift offline harness (`scripts/eval_rerank_lift.py`) with frozen 30-Q testset and shape-locked CSV/PNG (real numbers deferred to Andy's offline run)
- ✓ Coverage gates ≥95%: `app.copilot` 99.38%, `app.copilot.retrieval` 100%, `app.corpus` 98.51%; CI gates locked + regression test pinning thresholds
- ✓ Live smoke 2026-05-20 green: meta-event-first, 5 chips, side-panel, chip replacement, grounded answers
- ✓ Corpus consumed: 6054 chunks @ local-bge / `BAAI/bge-small-en-v1.5+pad1024`
- ✓ Paired learning + documentation writeups for all 7 topic lectures + the phase-overview indexes

**Phase 33 outcome (Tool calling + ReAct + PII tool boundary):**

- ✓ Alembic `0021_add_copilot_tool_calls` — audit log table; session_id / caller_id UUID FKs; ORM relationship
- ✓ Three-layer PII boundary in `app.copilot.agent.boundary`: `schema_filter` → `role_scope` → `redactor`
- ✓ `Tool` dataclass + role-scoped registry; uniform `invoke()` chains audit + redactor for every tool result
- ✓ 12 tools shipped: 8 read (`list_modules`, `get_module_roster`, `find_understaffed_modules`, `participant_history`, `signup_stats_for_week`, `signup_trend`, `find_module_by_name`, `current_user_context`) + 4 write (`send_reminder_email`, `nudge_understaffed_module`, `create_module_from_template`, `move_participant`)
- ✓ Confirmation gate with TTL (`_PENDING` in-memory store; Phase 37 swaps to DB-backed); `execute_after_confirmation(call_id, db)` runs the deferred write only after explicit approval
- ✓ Agent loop `run_turn()` caps at 6 tool calls + 2 malformed-response retries per turn; SSE events `tool_use` / `tool_result` / `confirmation_required` strictly additive to Phase-30 taxonomy
- ✓ Router: `POST /api/v1/copilot/confirm/{call_id}`; agent loop wired into `/api/copilot/chat` behind `COPILOT_AGENT_LOOP_ENABLED` (defaults off; Phase 30/32 token-stream behavior preserved)
- ✓ Frontend: `ConfirmationCard` + `ToolCallIndicator`; drawer renders confirmation cards and posts decisions; 42 frontend copilot tests green
- ✓ F1–F5 functional scenarios green (organizer/admin × read/write × multi-hop)
- ✓ Adversarial suite 35/35 across 7 categories — Cat 1–3 100% at 100% pass bar, Cat 4–7 100% at ≥80% pass bar; CSV at `docs/documentation/33-tool-calling-react/adversarial-pass-rates.csv`
- ✓ Backend copilot tests: 99 agent unit + 35 adversarial (~134 total for this phase)
- ✓ Paired learning + documentation writeups for all 10 sub-phase topics (01–09 + 11)

**Phase 33 known issues / deferred:**

- `Module` → `Event` model-name discrepancy handled by adaptation; LLM-facing tool names retained as `*_module*` to match org domain vocabulary
- `_dispatch` seams in `send_reminder_email` and `nudge_understaffed_module` need production wiring to the real Celery tasks (Phase 37)
- `participant_history` derives `school` from latest event because the `Volunteer` model has no `school` column
- `_PENDING` is in-memory — acceptable for v1 single-worker local; Phase 37 swaps to a DB-backed pending store

---
*Last updated: 2026-05-23 — Phase 33 shipped end-to-end. v1.4 milestone 4/9 phases complete; next action is Phase 34 planning (Memory + multi-turn context).*
