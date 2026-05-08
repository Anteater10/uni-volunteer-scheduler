# Phase 30 — Streaming Chat MVP (Plan)

> **Goal:** Ship a floating chat copilot inside the admin/organizer console
> that streams responses from a free-tier OpenRouter model, with all
> request/response telemetry logged from day one to seed the paper's data
> table. No RAG, no tools, no memory yet — just chat.

**Status:** planning → executing
**Started:** 2026-05-08
**Target:** 1 week
**Branch:** `feature/v1.4-phase-30-streaming-chat`

---

## Why now

The bottleneck for the paper is continued SciTrek deployment access, not
student status. Phase 30 ships a visible artifact the SciTrek team can use
and react to while you're still on campus. UX feedback from a real user is
worth more than a polished offline prototype.

---

## Scope (in)

### Backend

- `backend/app/copilot/__init__.py` — package marker.
- `backend/app/copilot/llm.py` — thin wrapper over OpenRouter using the
  `openai` Python SDK (`base_url=https://openrouter.ai/api/v1`). Single
  primary model + one fallback. Hardcoded role-aware system prompt.
- `backend/app/copilot/router.py` — FastAPI router mounted at
  `/api/v1/copilot`, exposing:
  - `POST /sessions` — create a new copilot session for the current user
  - `POST /sessions/{id}/messages` — send a user message; stream the
    assistant response back as Server-Sent Events
  - `GET /sessions/{id}` — fetch session + messages
  - `GET /sessions` — list current user's sessions
- Alembic migration `0042_copilot_sessions_and_messages`:
  - `copilot_sessions(id, user_id, created_at, model_id, system_prompt_hash)`
  - `copilot_messages(id, session_id, role, content, created_at,
     latency_ms, prompt_tokens, completion_tokens, prompt_hash,
     response_hash, model_id, error)`
- Structured request log row inserted on every model call. **This is the
  raw data table the paper draws from.** Treat it as a research artifact,
  not just a debug log.
- Admin feature flag `copilot_enabled` in `app_settings` (default `false`);
  router refuses 404 when disabled.

### Frontend

- `frontend/src/copilot/CopilotFab.jsx` — floating action button in the
  bottom-right of admin/organizer pages. Hidden when flag off.
- `frontend/src/copilot/CopilotDrawer.jsx` — slide-out chat panel.
- `frontend/src/copilot/useCopilotStream.js` — `EventSource` hook that
  consumes the SSE stream and updates message state.
- Drawer mounted in admin and organizer layouts only; never in public
  routes.

### Tests

- `backend/tests/test_copilot_router.py` — 100% coverage on the new router.
  - Flag-off → 404
  - Auth required (anon → 401)
  - Volunteer role rejected (only admin + organizer)
  - Session create + list + fetch
  - Message create logs telemetry row and streams
  - Error path: model timeout / quota → row written with `error` column
- `frontend/src/copilot/__tests__/CopilotDrawer.test.jsx` — render,
  open/close, message rendering, streaming token append.

### Documentation (parallel rule)

Every code block above produces both:

- `docs/learning/30-streaming-chat-mvp/{topic}.md` — tenured-professor
  lecture: build intuition first, then formalism, then code.
- `docs/documentation/30-streaming-chat-mvp/{topic}.md` — publication-style
  writeup: precise, citation-ready, no analogies.

Stubs for the four canonical topics (sse-streaming, openrouter-integration,
telemetry-schema, role-aware-system-prompts) are created at scaffold time
and filled in alongside the code.

---

## Scope (out — defer to later phases)

- **RAG / corpus / pgvector** → Phase 31.
- **Tools / ReAct / PII boundary** → Phase 33. The system prompt may
  describe a "tools coming soon" disclaimer but no tool calls are wired.
- **Multi-turn memory beyond session-local context** → Phase 34.
- **Model evaluation harness** → Phase 35.
- **Cost caps + circuit breakers** → Phase 37.
- Volunteer-facing UI.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| OpenRouter free-tier rate limits | Single fallback model; surface a `429` chip in the UI; structured error row in DB so we can later analyze rate-limit incidence. |
| SSE breakage behind reverse proxies | Test with `nginx`-style proxy locally; gracefully degrade to non-streaming POST if the EventSource closes prematurely. |
| Telemetry schema rot mid-milestone | Lock `copilot_messages` columns now via Alembic; future phases add columns with new migrations, never re-shape existing ones. The paper's data table needs schema stability. |
| Hallucinated answers about SciTrek | System prompt explicitly says "you do not yet have access to live SciTrek data; answer general questions only and recommend escalating to a human admin for specifics." This is a feature for Phase 30, fixed by RAG + tools later. |

---

## Definition of done

1. Migration applied; tables exist in dev + CI.
2. `POST /api/v1/copilot/sessions/{id}/messages` streams a real reply from
   OpenRouter end-to-end behind admin flag.
3. Every model call writes one row to `copilot_messages` with non-null
   latency + token counts.
4. CopilotFab visible only to admin + organizer roles, only when flag on.
5. Backend coverage on `app.copilot.*`: 100%.
6. Frontend tests for CopilotDrawer green.
7. Both `docs/learning/30-streaming-chat-mvp/` and
   `docs/documentation/30-streaming-chat-mvp/` have completed entries for
   each non-trivial code block.
8. Session journal entry exists for every working session.
9. SciTrek admin (or stand-in) sends one message and gets a real response
   in dev.

---

## Open decisions to lock at start of execution

- [ ] Primary model: OpenRouter free shortlist — pick one (e.g.
      `meta-llama/llama-3.1-8b-instruct:free` or
      `mistralai/mistral-7b-instruct:free`). Lock at first commit.
- [ ] Fallback model: pick one disjoint from primary.
- [ ] System prompt v0: 1 page, role-aware, tells the model it has no
      live data yet. Hash logged with every session row.
- [ ] Session retention: keep all messages forever for now (paper data).
      Revisit at Phase 38 deploy.
