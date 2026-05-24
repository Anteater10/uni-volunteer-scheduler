# Phase 34 — Memory + multi-turn context — SUMMARY

**Status:** Shipped
**Date completed:** 2026-05-23
**Branch:** `feature/v1.4-phase-34-memory-multi-turn`
**Milestone:** v1.4 (AI Onboarding Copilot)
**Plan:** `docs/superpowers/plans/2026-05-23-phase-34-memory-multi-turn.md`
**Spec:** `docs/superpowers/specs/2026-05-23-phase-34-memory-multi-turn-design.md`

## Goal

Extend the Phase 33 copilot from history-blind agent calls to a
session-aware assistant. Three new layers:

1. **Within-session summarisation** — when the working-set transcript
   crosses a token threshold, fold older turns into a rolling summary
   and keep recent turns verbatim so the LLM sees a coherent window.
2. **End-of-session profile extraction** — when a session closes
   (explicit `POST /sessions/{id}/close` or idle-sweeper timeout),
   Celery extracts a free-form profile blob from the transcript,
   re-applies the PII redactor with `declared=False`, and writes
   `copilot_user_profiles`.
3. **Session-start profile injection** — load the user's profile blob
   at session start and concatenate it into the system prompt behind
   an advisory header so the model treats it as untrusted context.

User control: view + clear via a "Copilot memory" card on
`/profile`. No manual edit.

## What shipped

- **New table `copilot_user_profiles`** — one row per user, free-form
  `profile_text` plus `updated_at`. Alembic `0022`.
- **Three new columns on `copilot_sessions`** — `closed_at`,
  `last_message_at`, `profile_extracted_at`. Same migration.
- **`app.copilot.memory.summariser.compress_if_needed`** — tiktoken
  token count with safe encoding fallback, threshold-driven; rolls
  older turns + tool-call results into a structured summary; no-ops
  below threshold.
- **`app.copilot.memory.extractor`** — `build_prompt(transcript, prior_blob)`
  + `run(...)` that calls the LLM, redacts with `declared=False`, and
  drops HIGH-severity outputs instead of writing them.
- **`app.copilot.memory.profile_block.load_profile_block(db, user_id)`** —
  per-user-scoped loader that returns the advisory-wrapped string
  (`"## What you know about this user"` … `"Use this context when it
  helps; ignore it when irrelevant."`) — structural framing the
  adversarial suite asserts against.
- **Celery task `app.tasks.extract_profile.extract_profile_facts`** —
  wraps the extractor with retry/failure handling, idempotent on
  `profile_extracted_at`.
- **Celery beat job `sweep_idle_sessions`** — 5-minute cadence; closes
  sessions inactive >30 min and enqueues extraction.
- **Router additions** — `GET /api/v1/copilot/profile`,
  `DELETE /api/v1/copilot/profile` (idempotent),
  `POST /api/v1/copilot/sessions/{id}/close` (enqueues extractor).
  Message append bumps `last_message_at`.
- **Loop integration** — `run_turn` calls `compress_if_needed` before
  each `llm.chat()` and concatenates the profile block into the
  system prompt at session start (sub-phase 34-05 + 34-07).
- **Frontend `CopilotMemorySettings`** — loading / empty / populated /
  forget-confirm states; wired into `ProfilePage` below the profile
  card.
- **Functional integration tests F1–F5** — happy-path multi-turn
  scenarios covering summariser firing, session close → extract,
  profile-block injection, clear-and-reopen, idle-sweeper close.
- **Memory adversarial suite** — `cases_memory.yaml` with 10 cases
  across 5 categories (P8 `memory_pii_leak`, P9 `profile_injection`,
  P10 `cross_user_profile_leak`, P11 `token_budget_exhaustion`,
  P11 `indirect_injection`). 8 active cases assert end-to-end; the
  two P11 rows are documented surfaces with runner assertions deferred
  (see Known follow-ups).

## Definition of Done

- [x] **Migration `0022`** applies cleanly up + down.
- [x] **Profile API** — GET + DELETE (idempotent) green.
- [x] **Session close + idle sweeper** — endpoint enqueues extractor;
      beat sweep closes idle sessions; `last_message_at` bumped on
      every append.
- [x] **Summariser** — threshold + no-op path; tiktoken count with
      fallback; working-set + tool-call rollup tests green.
- [x] **Loop integration** — `compress_if_needed` called before each
      `llm.chat()`; profile block concatenated into system prompt.
- [x] **Extractor + Celery task** — `build_prompt` + `run`; HIGH-severity
      drop honoured; idempotent on `profile_extracted_at`.
- [x] **Profile injection** — `load_profile_block` wraps blob with
      advisory header/footer; per-user `WHERE user_id = …` scope.
- [x] **Frontend** — `CopilotMemorySettings` loading / empty /
      populated / forget / cancel paths covered; wired into
      `ProfilePage`.
- [x] **Functional F1–F5** — all green.
- [x] **Adversarial 8/8 active cases** pass; P8 + P10 at 100% pass
      bar; P9 at ≥80% pass bar (structurally 100%).
- [x] **Two-folder rule** — paired `docs/learning/34-memory-multi-turn/`
      and `docs/documentation/34-memory-multi-turn/` writeups for
      sub-phases 01–10.

## Test counts

Full backend suite (`pytest -q --no-cov` on this branch, 2026-05-23):

| Surface | Count |
|---|---|
| Full backend suite — passed | **743** |
| Full backend suite — skipped | **9** |

The 9 skips are pre-existing (CI-only coverage-gate checks that
require `.github/workflows/ci.yml` to be mounted, and three
`tests/test_eval_script_smoke.py` rows that require the optional
`requirements-eval.txt` install or `docs/` mount). No skip is new
in Phase 34.

Adversarial:

| Category | Cases | Active | Pass | Bar |
|---|---|---|---|---|
| P8 `memory_pii_leak` | 3 | 3 | 3 | 100% |
| P9 `profile_injection` | 3 | 3 | 3 | ≥80% (structural 100%) |
| P10 `cross_user_profile_leak` | 2 | 2 | 2 | 100% |
| P11 `token_budget_exhaustion` | 1 | 0 | n/a | deferred |
| P11 `indirect_injection` | 1 | 0 | n/a | deferred |
| **TOTAL active** | **8** | **8** | **8** | — |

Source: full-suite run `743 passed, 9 skipped, 41 warnings in 75.62s`
on this branch tip (post sub-phase 34-10, commit `0c7127c` —
`docs(34-10): adversarial suite — documentation + learning`).

## Per-sub-phase summary

| Sub-phase | Title | Key commits | One-liner |
|---|---|---|---|
| 34-01 | Schema (table + session columns + ORM) | `3a15a57`, `341c4de`, `52dfd6c` | Alembic `0022` + `CopilotUserProfile` + 3 session columns. |
| 34-02 | Profile API (GET / DELETE) | `7ed3ee7`, `378070d`, `3c69861`, `6217638` | `CopilotProfileRead` schema + GET + idempotent DELETE. |
| 34-03 | Session close endpoint + idle sweeper | `730aeca`, `40bee99`, `7625864`, `411105c` | Close endpoint enqueues extractor; `last_message_at` bump; 5-min beat sweep. |
| 34-04 | Summariser (`compress_if_needed`) | `5806642`, `cc61a70`, `03d9cdc`, `2bee28d` | tiktoken count + threshold + no-op path + tool-call rollup. |
| 34-05 | Wire summariser into agent loop | `0243bd8`, `c493e96` | `run_turn` calls `compress_if_needed` before each `llm.chat()`. |
| 34-06 | Extractor + Celery task | `5ed2878`, `52b8132`, `1ade1d4`, `dc4556d` | `build_prompt` + `run` + Celery wrapper with HIGH-severity drop. |
| 34-07 | Profile retrieval at session start | `3ae1de7`, `199f43d`, `7ebc18c` | `load_profile_block` + system-prompt injection. |
| 34-08 | Frontend settings section | `325bf63`, `c8e594f`, `84d819e` | `CopilotMemorySettings` + `ProfilePage` wire-in. |
| 34-09 | Functional integration tests (F1–F5) | `2a86206`, `fcc0467` | Five happy-path multi-turn scenarios. |
| 34-10 | Adversarial suite (memory categories) | `5093fe8`, `54c6141`, `0c7127c` | `cases_memory.yaml` + 3 runner functions for P8/P9/P10. |
| 34-11 | Closeout | (this commit + ROADMAP/STATE commit) | SUMMARY + ROADMAP + STATE refresh. |

## Files added / changed

**New backend:**
- `backend/alembic/versions/0022_add_copilot_user_profiles_and_session_columns.py`
- `backend/app/copilot/memory/{__init__,summariser,extractor,profile_block}.py`
- `backend/app/tasks/extract_profile.py`
- `backend/tests/copilot/memory/` (unit tests)
- `backend/tests/copilot/api/test_profile_endpoints.py`,
  `test_session_close_endpoint.py`, `test_profile_schema.py`
- `backend/tests/copilot/tasks/test_sweep_idle_sessions.py`
- `backend/tests/copilot/agent/test_loop_memory.py`,
  `test_functional_memory.py`
- `backend/tests/copilot/adversarial/cases_memory.yaml` +
  appended runner cases in `test_adversarial.py`

**Modified backend:**
- `backend/app/models.py` — `CopilotUserProfile` + 3 columns on `CopilotSession`.
- `backend/app/copilot/router.py` — GET/DELETE `/profile`, POST `/sessions/{id}/close`, `last_message_at` bump.
- `backend/app/copilot/schemas.py` — `CopilotProfileRead`.
- `backend/app/copilot/prompts.py` — accept + concatenate profile block.
- `backend/app/copilot/agent/loop.py` — `compress_if_needed` call + profile block in system prompt.
- `backend/app/celery_app.py` — `sweep_idle_sessions` schedule + include `app.tasks.extract_profile`.

**New frontend:**
- `frontend/src/copilot/CopilotMemorySettings.jsx`
- `frontend/src/copilot/__tests__/CopilotMemorySettings.test.jsx`

**Modified frontend:**
- `frontend/src/pages/ProfilePage.jsx` — render `<CopilotMemorySettings />`.
- `frontend/src/copilot/api.js` — profile fetch + delete client.

**Docs (two-folder rule):**
- `docs/documentation/34-memory-multi-turn/01..10-*.md`
- `docs/learning/34-memory-multi-turn/01..10-*.md`

## Locked decisions (from spec section 2)

| # | Decision | Choice |
|---|---|---|
| 1 | Memory scope | Within-session + cross-session profile (no conversation recall) |
| 2 | Extraction timing | End-of-session, async via Celery |
| 3 | Within-session summarisation | Rolling summary + recent N turns verbatim |
| 4 | Profile shape | Free-form text blob (no structured slots) |
| 5 | User control | View + clear, no manual edit |
| 6 | Model assignment | One model (`COPILOT_LLM_MODEL`) for all roles — summariser, extractor, chat |
| 7 | Profile injection timing | Session-start only; mid-session profile changes apply to the next session |

## Known follow-ups

- **P11 adversarial rows are inert at the runner level.** Both
  `token_budget_exhaustion` and `indirect_injection` are kept in
  `cases_memory.yaml` so the attack surfaces stay documented, but
  neither has a runner assertion yet. Wiring them needs a longer-
  running harness that drives `run_turn` with padded history and a
  retrieval payload — that work overlaps with retrieval-grounding
  scheduled for Phase 35+.
- **Multi-model assignment is deferred to Phase 35.** This phase
  ships one-model-for-all (summariser, extractor, chat) per locked
  decision #6. Phase 35's multi-model eval harness is the right
  surface to compare separate models per role.
- **Idle sweeper interval is 5 min.** Spec section 13 left this as
  an open implementation question; we picked 5-min for tighter
  user feel. Easy to retune from `celery_app.py` if real-world
  usage suggests 1-min or 10-min is better.
- **No "extracting profile…" UI state.** Background work is
  intentionally invisible. If admins ask for visibility later, the
  signal already lives in `copilot_sessions.profile_extracted_at`.
- **Profile version history.** Deferred to Phase 37 hardening; the
  current shape overwrites `profile_text` on each extraction. The
  audit trail is implicit in Celery logs only.
- **Encryption at rest for `profile_text`.** Deferred to Phase 37.

## Out of scope (per spec section 12)

- Cross-session conversation recall (vector search) — not planned.
- Per-role profile (separate organizer vs admin blob) — YAGNI.
- Manual profile editing — locked decision #5.
- Admin views of other users' profiles — defer to Phase 38 if SciTrek requests.

## Handoff to Phase 35

Phase 35 (multi-model evaluation harness) inherits:

- The **memory subsystem boundaries** — when Phase 35 swaps models
  per request, the summariser + extractor must keep using the
  request-scoped model selection, not a hard-coded constant. The
  `COPILOT_LLM_MODEL` setting is the only knob today; the eval
  harness will need a per-request override.
- The **adversarial YAML schema** — Phase 35 extends `cases.yaml`
  and `cases_memory.yaml` with multi-model replays; do not
  rewrite the schema.
- The **`copilot_user_profiles` table** — Phase 35's human-feedback
  collection (sub-phase 35-01) lives in sibling tables
  (`copilot_message_ratings`, `copilot_session_ratings`); don't
  fold ratings into the profile blob.
- The **`profile_extracted_at` idempotency flag** — preserve the
  semantics; the eval harness shouldn't double-extract.

Phase 35 should NOT touch:

- The Phase 33 tool surface or three-layer boundary.
- The `_PENDING` confirmation contract (Phase 37 swap).
- The Phase 30 SSE token taxonomy (additive frames only).
- The advisory header/footer wrapping `load_profile_block` — the
  adversarial suite asserts on the exact strings.
