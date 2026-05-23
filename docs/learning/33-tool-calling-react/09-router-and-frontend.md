# Lecture — wiring the agent loop into HTTP and React

> Sub-phase 33-09. Companion to the publication writeup
> `docs/documentation/33-tool-calling-react/09-router-and-frontend.md`.

We've built the agent loop (33-07) and the confirmation store (33-08).
Now we need humans to actually be able to drive it. That means two
endpoints and two frontend pieces.

## Why a separate confirm endpoint

You might be tempted to do everything over a single long-lived SSE
connection: send the confirmation as a message-in-flight on the existing
stream. Don't. Two reasons:

1. **HTTP/2 + reverse proxies often cut idle SSE streams** after 60s.
   The user might wait minutes before deciding. Holding the stream open
   to wait for a human decision wastes a connection and risks silent
   timeouts on infrastructure you don't own.
2. **The audit row is the source of truth.** If the browser tab crashes
   between "user clicked confirm" and "server saw it", we want a clean
   POST that idempotently resolves the parked call. SSE makes that
   harder.

So `/confirm/{call_id}` is a plain old POST. The endpoint:

- Looks up the parked entry (404 if missing).
- Checks the TTL (410 if expired).
- Runs the handler (admin/organizer scope) and stamps the audit row.

## Why the TTL check moved

The original `execute_after_confirmation` only checked existence. The
TTL only fired in `resolve`. But our endpoint never calls `resolve` on
the approve path — it goes straight to `execute_after_confirmation`. So
an expired pending entry would still get executed. We moved the TTL
check into `execute_after_confirmation` so there is one place that owns
the "may this run?" decision.

This is the kind of bug that survives for a long time because both
paths feel correct in isolation. Lesson: when two functions share a
precondition, push the check down into the one that actually performs
the side effect.

## Why feature-flag the chat endpoint

The Phase 32 chat endpoint streams `token` / `done` events. The agent
loop emits `tool_call` / `tool_result` / `confirmation_request` /
`final_answer`. These are not the same wire format. If we shipped the
new events unconditionally, every existing Phase 30 / 32 test would
break — and any external integration would too.

The flag `copilot_agent_loop_enabled` defaults off. With it off,
nothing changes. With it on, the endpoint runs `run_turn` instead of
`llm.stream_completion`. Tests opt in per-test via monkeypatch; prod
opts in via env when the structured-LLM adapter is ready.

## The `_get_agent_llm` indirection

`run_turn` expects a duck-typed LLM with a `.chat(messages, tools)`
method returning either `{"tool_calls": [...]}` or `{"final_answer":
"..."}`. The real OpenRouter client doesn't speak that protocol — it
streams plain text. Wiring the real adapter is a different sub-phase.

So we leave a hook: `_get_agent_llm()` raises `NotImplementedError` by
default. Tests do `monkeypatch.setattr(router, "_get_agent_llm", lambda:
stub)`. This is the same indirection pattern we used for the embedding
provider in Phase 31 — when a dependency isn't ready, expose a function
that returns it so tests can swap in a fake without touching imports.

## Frontend dispatch

`useCopilotStream` already had `onDone` / `onError`. We added four new
callbacks: `onToolCall`, `onToolResult`, `onConfirmationRequest`,
`onFinalAnswer`. The drawer wires them into local state:

- `toolCalls` — `{ [call_id]: { tool, status } }` for the indicator.
- `pendingConfirmations` — `{ [call_id]: { tool, args, preview } }`.
- `confirmInFlight` — `{ [call_id]: true }` while a decision is posting.

On approve / reject, the drawer calls `copilotApi.confirmCall(callId,
approved)`. Success removes the card; failure surfaces a red error line.

## Why we stopped pushing an empty assistant bubble on done

On a confirmation-paused turn there is no `final_answer` yet — the
stream ended because the loop paused. The previous `onDone` handler
pushed an empty assistant bubble in that case, which looked like the
copilot said nothing. The fix: only push a bubble when `text` is
non-empty. The card itself is the "what's happening" affordance.

## Testing the SSE plumbing

Two test layers:

1. **Backend integration** — TestClient + a scripted `_StubLLM` that
   returns canned `tool_calls` / `final_answer` dicts. Assert event
   names appear in order on the wire, including the terminal `done`.
2. **Frontend integration** — `global.fetch` mocked, the response body
   is a `ReadableStream` containing the SSE wire format. Vitest +
   Testing Library assert the indicator renders, the card renders, and
   clicking Confirm posts to `/confirm/{call_id}` with `approved: true`.

Both layers are hermetic. No live LLM, no live network.

## Recap

- Confirm endpoint = plain POST, idempotent on the audit row.
- Chat endpoint = feature-flagged. Old behaviour by default, new event
  stream when opted in.
- TTL check lives in the function that actually runs the handler.
- Frontend dispatches on `event.type` via callbacks and posts the
  decision back over a separate HTTP request.
