---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: milestone
status: in-progress
last_updated: "2026-05-23T23:30:00.000Z"
last_activity: 2026-05-23 — Phase 35 sub-phase 35-01 (human-feedback collection) shipped end-to-end. New tables `copilot_message_ratings` + `copilot_session_ratings` via Alembic `0023` (with unique constraints `(message_id, user_id)` / `(session_id, user_id)` for upsert), four new router endpoints (`POST /messages/{id}/rating`, `POST /sessions/{id}/rating`, `GET /admin/feedback/weekly`, `GET /admin/feedback/bottom-messages`), additive SSE `message_persisted` event emitted after persisting each assistant `copilot_messages` row, `useCopilotStream` captures the id onto the rendered bubble, `MessageRatingButtons` (up persists on click; down opens inline comment box and persists only on submit) + `SessionRatingModal` (coercive — no skip; Cancel keeps the drawer open) + `AdminCopilotFeedbackPage` wired into `AdminLayout.jsx` for both admin and organizer roles. New package `app.copilot.feedback` with `weekly_rollup` (ISO-week via `date_trunc('week', ...)`) + `bottom_messages` (partial-index drill-down over `value = 'down'`). 95% per-package coverage gate added in `.github/workflows/ci.yml` and pinned in `backend/tests/test_coverage_gates.py`. Full backend suite green: **799 passed / 11 skipped**. Frontend green: **274 tests across 42 files**. Phase 35-02+ (multi-model comparison — eval testset replay across 5–8 OpenRouter free models, combining RAGAS scores with the human-feedback signal landed here) is the next action.
progress:
  total_phases: 9
  completed_phases: 6
  total_plans: 25
  completed_plans: 19
  percent: 76
---

# Project State

**Project:** Uni Volunteer Scheduler (UCSB Sci Trek)
**Initialized:** 2026-04-08
**Mode:** Autonomous · Standard granularity · Sequential execution · Research/Plan-Check/Verifier all ON
**Deadline:** Phase 30 before graduation; full milestone + paper by week 16.

## Current Position

Milestone: **v1.4 AI Onboarding Copilot** — in progress
Phase: 35 (Multi-model evaluation harness) — sub-phase 35-01 (human-feedback collection) ✅ shipped; 35-02+ ahead
Branch: `feature/v1.4-phase-35-01-human-feedback` — ready to merge
**Last activity:** 2026-05-23 — Phase 35 sub-phase 35-01 shipped end-to-end (see Phase 35-01 outcome block below). Phase 34 shipped earlier the same day. Within-session summariser (`compress_if_needed`, tiktoken + threshold + rollup) wired into `run_turn`. End-of-session profile extraction via Celery task `extract_profile_facts` re-applies the PII redactor with `declared=False` and drops HIGH-severity outputs. Session-start profile injection through `load_profile_block(db, user_id)` returns an advisory-wrapped string (`"## What you know about this user"` … `"Use this context when it helps; ignore it when irrelevant."`) — structural framing the adversarial suite asserts on. New table `copilot_user_profiles` + three columns on `copilot_sessions` (`closed_at`, `last_message_at`, `profile_extracted_at`) via Alembic `0022`. Celery beat `sweep_idle_sessions` (5-min cadence) closes sessions inactive >30 min and enqueues extraction. Router adds `GET /api/v1/copilot/profile`, `DELETE /api/v1/copilot/profile` (idempotent), `POST /api/v1/copilot/sessions/{id}/close`; message append bumps `last_message_at`. Frontend `CopilotMemorySettings` (loading / empty / populated / forget / cancel) wired into `ProfilePage`. Full backend suite green: 743 passed / 9 skipped. Functional F1–F5 multi-turn scenarios green. Memory adversarial 8/8 active across P8 (memory_pii_leak — 3/3, 100% bar), P9 (profile_injection — 3/3, ≥80% bar, structural 100%), P10 (cross_user_profile_leak — 2/2, 100% bar); P11 rows (`token_budget_exhaustion`, `indirect_injection`) kept as documented surfaces with runner assertions deferred to a later milestone. See `.planning/phases/34-memory-multi-turn/SUMMARY.md` for full handoff to Phase 35.

**2026-05-20 — Phase 32 Plan 06 shipped (citation chips frontend):** `useCopilotStream` consumes the new `event: meta` SSE branch additively (Phase 30 token/done/error untouched). New `CitationChip` (`[N] filename` + tooltip + keyboard-accessible) and `CitationPanel` (side-panel modal, "Source consulted" header, conditional external link) components. Per-message citation snapshot keeps multi-turn history coherent. New `e2e/copilot-citations.spec.js` covered by all 6 Playwright projects via the default testMatch glob (Case A — no CI workflow edit). 243/243 vitest green, chromium Playwright green. Paired learning + publication docs (126 + 187 lines).

**2026-05-20 — Phase 32 Plan 07 shipped (RAGAS rerank-lift harness):** Offline harness at `scripts/eval_rerank_lift.py` drives the Phase 32 pipeline twice (rerank ON / OFF) over a frozen 30-question testset and emits `docs/documentation/32-rag-retrieval/rerank-lift.{csv,png}` with the paper-locked column header `metric,rerank_off,rerank_on,lift`. Eval deps pinned (`ragas==0.4.3`) in a separate `backend/requirements-eval.txt` so the request-path image stays slim (constraint C6). CI smoke (`backend/tests/test_eval_script_smoke.py`) guards the artifact shapes via `pytest.importorskip("ragas")` — 2 passed / 1 skipped. `scripts/generate_testset.py` drives RAGAS `TestsetGenerator` in batches of 5 with sleeps (Pitfall 4). Paired learning + publication docs (124 + 152 lines). Real CSV/PNG values + curated/synthetic testset population are deferred to Andy's offline run (checkpoint:human-action per plan); placeholders ship with correct shape so the figure path and CI guard work end-to-end.

## Current Status

- ✓ v1.0 phases 0–7 shipped (2026-04-08) — drifted from no-accounts thesis, then realigned in v1.1
- ✓ v1.1 phases 08–13 shipped (2026-04-10) — account-less realignment + admin shell + 16/16 Playwright E2E green
- ✓ v1.2-prod phases 14–20 shipped (2026-04-16) — production-ready by role (participant, admin, organizer) + cross-role integration
- ✓ v1.3 phases 21, 22, 23, 24, 25, 26, 28, 29 shipped (2026-04-17) — feature expansion complete
- ⏸ Phase 27 (SMS reminders + no-show nudges, AWS SNS) — **deferred** to a later milestone (TCPA + flag-gated; not a blocker)
- ▶ v1.4 (AI Onboarding Copilot) — Phases 30 + 31 + 32 + 33 + 34 shipped; Phase 35 sub-phase 35-01 (human-feedback collection) shipped 2026-05-23; sub-phases 35-02+ + phases 36–38 ahead

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

Merge Phase 35-01 to `main`, then start Phase 35-02+ (multi-model comparison). Swap the
LLM provider per-request via env override and replay the eval testset across 5–8 OpenRouter
free models, combining RAGAS scores (automated) with the human-feedback signal collected in
35-01 (rating tables landed). Output goes to `docs/documentation/35-eval-results.md` and
produces paper contributions #2 (empirical comparison) and #3 (failure taxonomy).

Locked invariants for Phase 35-02+ (carried from 35-01 handoff + earlier phases): do not
touch the Phase 33 tool surface or three-layer boundary (additive new tools only — no
rename/reshape of `list_modules`, `get_module_roster`, etc.); do not change the `_PENDING`
confirmation contract (Phase 37 swaps the backing store; the interface stays stable); keep
the Phase-30 / Phase-32 SSE token + meta taxonomy additive-only (the `message_persisted`
event added in 35-01-D is the precedent); re-apply the redactor whenever previously-
retrieved tool data is surfaced from memory; preserve the advisory header/footer wrapping
`load_profile_block` (the Phase 34 adversarial suite asserts the exact strings); extend the
adversarial YAML schema (`cases.yaml` + `cases_memory.yaml`) rather than rewriting it; do
not fold ratings into `copilot_user_profiles.profile_text` — sibling rating tables only;
preserve the `(message_id, user_id)` and `(session_id, user_id)` unique constraints on the
new rating tables — overwrites are the contract; extend (don't rewrite) the
`app.copilot.feedback.weekly_rollup` aggregator with a `model` dimension column when
per-model breakdowns land.

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
**Phase 34 outcome (Memory + multi-turn context):**

- ✓ Alembic `0022_add_copilot_user_profiles_and_session_columns` — new table `copilot_user_profiles` + three columns on `copilot_sessions` (`closed_at`, `last_message_at`, `profile_extracted_at`)
- ✓ Within-session summariser `app.copilot.memory.summariser.compress_if_needed` — tiktoken count with safe encoding fallback, threshold-driven, working-set + tool-call rollup
- ✓ Summariser wired into `run_turn` before each `llm.chat()` (sub-phase 34-05)
- ✓ Extractor `app.copilot.memory.extractor` — `build_prompt(transcript, prior_blob)` + `run(...)` with PII redactor at `declared=False`; HIGH-severity outputs dropped, not written
- ✓ Celery task `app.tasks.extract_profile.extract_profile_facts` — idempotent on `profile_extracted_at`
- ✓ Celery beat `sweep_idle_sessions` — 5-min cadence; closes sessions inactive >30 min and enqueues extraction
- ✓ `load_profile_block(db, user_id)` — per-user-scoped loader with advisory header/footer wrapping
- ✓ Profile block injected into the session-start system prompt (sub-phase 34-07)
- ✓ Router: `GET /api/v1/copilot/profile`, `DELETE /api/v1/copilot/profile` (idempotent), `POST /api/v1/copilot/sessions/{id}/close`; `last_message_at` bumped on every message append
- ✓ Frontend `CopilotMemorySettings` wired into `ProfilePage` — loading / empty / populated / forget / cancel states
- ✓ Functional F1–F5 multi-turn integration tests green
- ✓ Memory adversarial 8/8 active across P8 (memory_pii_leak), P9 (profile_injection), P10 (cross_user_profile_leak)
- ✓ Full backend suite: **743 passed / 9 skipped** (no skip new in Phase 34)
- ✓ Paired learning + documentation writeups for sub-phases 01–10

**Phase 34 known issues / deferred:**

- P11 rows (`token_budget_exhaustion`, `indirect_injection`) in `cases_memory.yaml` are inert at the runner level — kept as documented attack surfaces; runner assertions wait on a retrieval-grounding harness in Phase 35+
- Multi-model role assignment (separate summariser/extractor models) deferred to Phase 35 per locked decision #6
- Profile version history deferred to Phase 37 hardening; current shape overwrites `profile_text` on each extraction
- Encryption at rest for `profile_text` deferred to Phase 37
- Idle sweeper interval picked 5-min (open question in spec section 13); easy retune from `celery_app.py` if usage suggests otherwise

---
**Phase 35-01 outcome (Human-feedback collection):**

- ✓ Alembic `0023_add_copilot_feedback_tables` — `copilot_message_ratings` (FK → `copilot_messages.id`, value `up | down`, optional `comment`, unique `(message_id, user_id)`) + `copilot_session_ratings` (FK → `copilot_sessions.id`, value 1–5 CHECK, optional `comment`, unique `(session_id, user_id)`); partial index on message-ratings `value = 'down'` for the drill-down query
- ✓ ORM models `CopilotMessageRating` + `CopilotSessionRating` with `back_populates` wiring
- ✓ Pydantic schemas (`MessageRatingWrite`, `SessionRatingWrite`, `WeeklyFeedbackRow`, `BottomMessageRow`) — comment validator enforces "required for thumbs-down" + "required for session rating ≤2"
- ✓ Four router endpoints reusing `_require_flag_on` + `_require_admin_or_organizer`: `POST /api/v1/copilot/messages/{id}/rating`, `POST /api/v1/copilot/sessions/{id}/rating`, `GET /api/v1/copilot/admin/feedback/weekly`, `GET /api/v1/copilot/admin/feedback/bottom-messages`
- ✓ New package `app.copilot.feedback` with `weekly_rollup(db, weeks)` (ISO-week via Postgres `date_trunc('week', ...)`, Monday start, per locked decision (f)) + `bottom_messages(db, limit)` (partial-index drill-down; assistant + prior-user text already redacted at persist, regression assertion pinned)
- ✓ SSE `message_persisted` event emitted after persisting each assistant `copilot_messages` row; strictly additive to the Phase 30/32 SSE taxonomy (token/done/error/meta untouched)
- ✓ Frontend `useCopilotStream` captures `message_persisted` and stores assistant id on the rendered bubble; `CopilotDrawer.jsx` renders `data-message-id`, mounts `MessageRatingButtons` under each bubble, and intercepts the close action with `SessionRatingModal` when the session has ≥1 assistant turn
- ✓ `MessageRatingButtons.jsx` — icon-only thumbs, `aria-pressed` state, up persists on click, down opens inline comment box and persists only on submit (no half-state rows)
- ✓ `SessionRatingModal.jsx` — coercive (no skip), 1–5 `role=radiogroup`, comment textarea conditionally required when score ≤2, Cancel-close keeps the drawer open
- ✓ `AdminCopilotFeedbackPage.jsx` — weekly table + bottom-messages drill-down; route in `App.jsx`; nav entry in `AdminLayout.jsx` (visible to admin + organizer)
- ✓ 95% per-package coverage gate on `app.copilot.feedback` added to `.github/workflows/ci.yml` and pinned in `backend/tests/test_coverage_gates.py`
- ✓ Full backend suite: **799 passed / 11 skipped** (no skip new in 35-01)
- ✓ Frontend: **274 tests passed across 42 files**
- ✓ Paired learning + documentation writeups for sub-phases A–E in `docs/learning/35-01-human-feedback/` and `docs/documentation/35-01-human-feedback/`

**Phase 35-01 known issues / deferred:**

- No adversarial sweep on comment text (prompt injection via rating comments, PII smuggling) — per spec section 8, deferred to the 35-02+ multi-model eval sweep
- Multi-model comparison (paper contribution #2) deferred to sub-phases 35-02+
- No rate-limit on rating endpoints — unique constraints prevent row explosion (one row per `(message_id, user_id)`); rate-limit can land with Phase 37 if logs show spam
- Admin response-rate metric (% of assistant messages rated; % of closed sessions rated) not in the weekly view yet — easy add when paper analysis surfaces the need
- No `beforeunload` interception per locked decision (c); tab close / refresh proceeds silently (dark-pattern cost outweighs data win)
- Comment field encryption at rest deferred to Phase 37 hardening alongside `profile_text` encryption

---
*Last updated: 2026-05-23 — Phase 35 sub-phase 35-01 (human-feedback collection) shipped end-to-end. v1.4 milestone 6/9 phases complete (Phase 35 counted with 35-01 done; 35-02+ ahead). Next action is Phase 35-02+ (multi-model comparison — eval testset replay across 5–8 OpenRouter free models combining RAGAS + the human-feedback signal collected in 35-01).*
