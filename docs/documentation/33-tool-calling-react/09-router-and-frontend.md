# Phase 33-09 — Router wiring and frontend confirmation card

This sub-phase exposes the agent loop over HTTP and wires the React drawer
to render the new event types. Concretely, three things land:

1. `POST /api/v1/copilot/confirm/{call_id}` — the human-decision endpoint
   that completes a parked write tool call.
2. The existing chat endpoint (`POST /api/v1/copilot/sessions/{id}/messages`)
   learns to stream agent-loop events instead of raw token chunks, behind a
   feature flag.
3. The React drawer renders a `ConfirmationCard` for each parked call and a
   `ToolCallIndicator` for each in-flight read, and posts the operator's
   decision back to the confirm endpoint.

## The confirm endpoint

`ConfirmBody` is a single-field Pydantic model: `approved: bool`. The
handler:

- 404s when the copilot feature flag is off (invisible surface invariant).
- 403s for participant accounts.
- On `approved=False`, drops the in-process pending entry and flips the
  audit row to `rejected` via `update_status`. If the audit row is missing,
  returns 404.
- On `approved=True`, calls `execute_after_confirmation` under the caller's
  role and `id`. The function looks up the parked tool call, runs the
  handler, scrubs the output through the boundary redactor, and updates
  the audit row to `executed`. The redacted result is returned verbatim.
- Maps `ConfirmationExpired` -> HTTP 410 and also stamps the audit row as
  `expired` so the lineage is preserved.
- Maps `ConfirmationNotFound` -> HTTP 404.

The TTL check itself moved into `execute_after_confirmation` so the
endpoint no longer needs to call `resolve` first — there is now exactly
one path that decides whether a parked call may run, and it always
enforces the 5-minute window.

## Wiring the agent loop into the chat endpoint

The Phase 30 / 32 chat endpoint streams `meta`, `token`, `done`, and
`error` events. Sub-phase 33-09 adds the ability to stream the new agent
event types (`tool_call`, `tool_result`, `confirmation_request`,
`final_answer`). Because the wire format differs significantly — token
chunks vs. structured discriminated events — the new path is gated on
`settings.copilot_agent_loop_enabled` and defaults off. With the flag off
the endpoint behaves exactly as Phase 32 left it; with the flag on the
endpoint:

1. Runs retrieval (so citation chips still arrive via the `meta` event).
2. Builds the scope from `current_user.role` and `current_user.id`.
3. Calls `run_turn` and serialises each yielded Pydantic event as an SSE
   block: the event name is `event.type`, the payload is
   `event.model_dump_json()`.
4. Appends a terminal `done` event after `final_answer` so existing
   clients (and tests) see a clean turn boundary, and persists the
   assistant message body for `GET /sessions/{id}` replay.

A small indirection function — `_get_agent_llm()` — returns the
structured LLM adapter the loop expects (an object with a `.chat(...)`
method returning `{"tool_calls": ...}` / `{"final_answer": ...}`). The
default implementation raises `NotImplementedError` because the
production tool-calling adapter ships in a later sub-phase; tests
monkeypatch this hook to inject a scripted stub.

## ConfirmationCard

The card is intentionally boring: an amber-bordered block with the tool
name, a pretty-printed JSON args dump, the model-supplied human-readable
preview, and Confirm / Reject buttons. The drawer owns the network call;
the card just exposes `onApprove` / `onReject` callbacks and a `disabled`
prop that is flipped while a decision is in flight (prevents
double-clicks).

## ToolCallIndicator

A one-line inline indicator: a small spinning loader and the text
"calling list_modules…" while the tool runs, then "ran list_modules" once
the matching `tool_result` arrives. It uses `role="status"` so screen
readers announce changes. The drawer keys indicators by `call_id` so
parallel calls render distinctly.

## SSE event flow end-to-end

```
browser   --POST /messages---------->   FastAPI
browser   <--event: meta (citations)--
browser   <--event: tool_call--------
browser   <--event: tool_result-----   (read-only path)
browser   <--event: final_answer----
browser   <--event: done------------

browser   <--event: confirmation_request-- (write path, stream pauses)
browser   --POST /confirm/{call_id}-->   FastAPI
                                         executes handler, redacts,
                                         updates audit row
browser   <-- {"result": ..., "redactions": n}
```

The drawer dispatches on `event.type` via the `useCopilotStream` hook's
new callbacks: `onToolCall`, `onToolResult`, `onConfirmationRequest`,
`onFinalAnswer`. Existing callbacks (`onDone`, `onError`) are unchanged.

## Error mapping

- 404 `confirmation not found` — no parked entry and no audit row.
- 410 `confirmation expired` — TTL elapsed; audit row stamped `expired`.
- 403 — participant accounts.
- 404 (entire route) — copilot flag off.

## Feature gating

`copilot_agent_loop_enabled` defaults to `False`. Production deployments
keep the Phase 32 behaviour until the structured-LLM adapter ships. Tests
flip the flag per-test via `monkeypatch.setattr(settings, ...)`.
