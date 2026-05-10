# Phase 30 — Streaming Chat MVP — SUMMARY

**Status:** ✅ Shipped
**Date completed:** 2026-05-08
**Branch:** `feature/v1.4-phase-30-streaming-chat`
**Milestone:** v1.4 (AI Onboarding Copilot)

## What shipped

A flag-gated `/api/v1/copilot` API + matching admin/organizer UI that
streams an LLM chat over SSE and persists every model invocation to a
research-grade telemetry table.

### Backend

- Alembic revision `0018_copilot_sessions_and_messages` — two new
  tables (`copilot_sessions`, `copilot_messages`), one enum
  (`copilot_message_role`), one composite index, FK cascade. Validated
  upgrade → downgrade → upgrade round-trip.
- ORM classes `CopilotSession`, `CopilotMessage`,
  `CopilotMessageRole` in `backend/app/models.py`.
- New settings in `backend/app/config.py`: `copilot_enabled`,
  `copilot_primary_model`, `copilot_fallback_model`,
  `copilot_request_timeout_seconds`, `copilot_max_completion_tokens`.
- New package `backend/app/copilot/`:
  - `prompts.py` — base prompt + admin/organizer tails,
    `SYSTEM_PROMPT_VERSION = "v0.1.0"`, `hash_prompt()` SHA-256.
  - `llm.py` — OpenRouter via the `openai` SDK, primary→fallback
    retry on `APIConnectionError | APITimeoutError | RateLimitError | APIStatusError`,
    streaming via `stream_options={"include_usage": True}`.
  - `schemas.py` — pydantic v2 read/create models.
  - `router.py` — `POST /sessions`, `GET /sessions`,
    `GET /sessions/{id}`, `POST /sessions/{id}/messages` (SSE).
    Flag-off → 404. Volunteer role → 403. Per-session ownership
    enforcement.
- Wired into `backend/app/main.py` under `/api/v1`.

### Frontend

- New module `frontend/src/copilot/`:
  - `api.js` — REST client for sessions endpoints.
  - `useCopilotStream.js` — fetch + ReadableStream + SSE parser
    hook, with `parseSseChunk` exported for testing.
  - `CopilotFab.jsx` — flag-gated floating action button,
    admin/organizer only.
  - `CopilotDrawer.jsx` — chat drawer with lazy session creation,
    auto-scrolling messages, streaming partial bubble, and error
    surfaces.
- Mounted in `frontend/src/components/Layout.jsx` as a global
  bottom-right FAB.
- New env: `VITE_COPILOT_ENABLED` mirrors the backend flag so the
  surface stays invisible end-to-end when off.

### Tests

- Backend: 29 tests in `backend/tests/test_copilot_router.py` covering
  flag-off 404, auth-required, volunteer 403, session CRUD for admin +
  organizer, ownership isolation, SSE streaming with assertion on
  event types and message-id round-trip, mid-stream error path, llm
  primary/fallback/both-fail behavior, `max_tokens` passthrough,
  empty-choice handling, prompt versioning + hashing.
  **100% coverage on `app.copilot.*`.**
- Frontend: 16 tests in `frontend/src/copilot/__tests__/CopilotDrawer.test.jsx`
  covering parseSseChunk, FAB visibility (role/auth/flag), session
  bootstrap success + failure, happy-path streaming,
  mid-stream error, close handler. All 222 frontend tests still
  green.

### Documentation (two-folder rule)

- `docs/learning/30-streaming-chat-mvp/` — 4 lectures (sse-streaming,
  openrouter-integration, telemetry-schema, role-aware-system-prompts)
  with intuition-first explanations.
- `docs/documentation/30-streaming-chat-mvp/` — 4 publication-style
  writeups with the same topic split, citation-ready.

## Locked decisions (unchanged from PLAN)

| Decision | Value | Reason |
|---|---|---|
| Primary model | `openai/gpt-oss-120b:free` | OpenRouter free tier, capable enough for general Q&A |
| Fallback model | `meta-llama/llama-3.3-70b-instruct:free` | Different vendor for failover diversity |
| Stream protocol | SSE (POST endpoint via fetch + ReadableStream) | Unidirectional within a turn; proxy-friendly; trivial to debug |
| Session retention | Forever | Sessions are research data |
| Migration ID | `0018_copilot_sessions_and_messages` | Sequential after `0017` |
| Telemetry columns | All paper-relevant fields recorded from day 1 | No backfill at Phase 35 |
| Volunteer access | 403 (not 404) — feature exists, role lacks it | Distinct from flag-off, matches OWASP guidance |

## End-to-end smoke (2026-05-08)

Live test against real OpenRouter, executed twice:

- **Curl path:** session created, stream POST returned 30 `token`
  events + terminal `done`. Row in `copilot_messages` —
  `latency_ms=2807`, `prompt_tokens=366`, `completion_tokens=48`,
  `model_id=openai/gpt-oss-120b:free`, `error=NULL`.
- **Browser path:** Andy logged in as admin, opened the FAB, sent
  "In one sentence, what is the SciTrek copilot for?". Streaming
  bubble visible word-by-word, terminal cursor cleared on `done`,
  text matched assistant row. Row recorded —
  `latency_ms=3738`, `prompt_tokens=366`, `completion_tokens=46`.

Both runs confirm the streaming, telemetry, role-gating, and flag-gating
work together against the production database schema.

## Definition of Done

- [x] Migration applied to `uni_volunteer` and round-trip-tested
- [x] Router 404s when flag off, 403s for volunteer
- [x] Streaming endpoint emits SSE; assistant row persisted
- [x] Telemetry columns populated end-to-end (latency, tokens,
      model_id, hashes)
- [x] Frontend FAB hidden when flag off, role wrong, or unauthed
- [x] Backend tests 100% on `app.copilot.*`
- [x] Frontend tests cover FAB visibility + streaming + error path
- [x] Real OpenRouter smoke test green via curl AND via browser
- [x] Two-folder docs filled in (learning + documentation)

## Known limitations / deferred work

- No client-side resumption on dropped connections (regenerate UI
  affordance instead). Revisit at Phase 35 if the latency CDF
  motivates it.
- No `tool_calls` table — tools land in Phase 33.
- No prompt-editor admin page; prompts edited via git + version bump.
- No nginx-style buffering hints in the response — single-uvicorn
  deployment for now. Add `X-Accel-Buffering: no` when reverse-proxy
  lands.
- API key in `backend/.env` is a personal OpenRouter key; rotate
  before any public deploy.

## Files changed (commit chain)

- `7ce17b0` — step 1: migration + models + config
- `ba12032` — step 2: copilot package + router + 29 tests (100% coverage)
- `22ea7ce` — Phase 30 lecture + publication writeups (8 files)
- `420f6b8` — frontend: FAB + drawer + streaming hook + 16 tests

Five commits ahead of `main`.

## Handoff to Phase 31

Phase 31 ("conversation history + session list UI") inherits:

- A working session abstraction. Listing endpoint already exists
  (`GET /sessions`), needs a UI surface and a "switch session" affordance.
- `prompt_hash` + `system_prompt_version` already on every session row;
  no schema work needed for prompt versioning.
- A drawer component to extend rather than replace.

Phase 31 should NOT touch:

- The SSE wire format (locked for the milestone).
- The telemetry column set (extensions only via additive migrations).
- The 100% coverage gate on `app.copilot.*`.
