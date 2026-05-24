# 35-01-D — SSE `message_persisted` and frontend id wiring

## Why this exists

Phase 35-01 ships per-message thumbs-up / thumbs-down ratings (35-01-B Task 5).
A rating row is keyed by the assistant message's UUID — the primary key of
the `copilot_messages` table. For the UI to send `POST
/api/v1/copilot/messages/{id}/rating`, every rendered assistant bubble must
know its persisted id.

Before this sub-phase the streaming endpoint emitted the id only on the
terminal `event: done` (or `event: error`) marker. The drawer's onDone
callback received `{ messageId, text, citations }`, but the assistant bubble
itself — pushed into the `messages` array inside `onDone` — was never
stamped with the id. There was no DOM hook a future rating component could
target without rebuilding state.

Sub-phase 35-01-D closes that gap with a strictly-additive change to the
SSE protocol and a small thread of plumbing on the frontend.

## Protocol change — backend

The `POST /sessions/{id}/messages` stream now emits a new event
immediately after the assistant `copilot_messages` row is persisted and
**before** the terminal `done` (or `error`) marker:

```
event: message_persisted
data: {"id": "<uuid>", "role": "assistant"}
```

- `id` is the primary key of the new `copilot_messages` row (a string
  UUID — what `MessageRatingCreate` expects).
- `role` is always the literal string `"assistant"`. It is included for
  forward-compatibility with future events that might announce
  persistence of other kinds of rows (e.g. tool-result rows, system
  rewrites).

The event is emitted from both streaming paths in
`backend/app/copilot/router.py`:

- `_sse_stream` (the Phase 30 baseline path) — emitted right after
  `db.refresh(assistant_msg)`, before the `done`/`error` write.
- `_agent_sse_stream` (the Phase 33 agent-loop path) — same position,
  immediately after the assistant row is committed.

The change is strictly additive:

- `token` / `done` / `error` payload shapes are byte-for-byte unchanged
  (covered by `test_existing_event_shapes_unchanged`).
- Old clients that ignore unknown event names see no behaviour change.

## Frontend wiring

### `useCopilotStream`

The hook now has a `case "message_persisted"` branch that captures
`persistedId` and `persistedRole` from the event payload. At stream end:

- `send()` returns `{ id, role, messageId, text, error, citations }`.
- `onDone` and `onError` receive the same shape (with `latencies` for
  `onDone`).
- `messageId` is preserved as a legacy alias for the same value (so the
  Phase 33 tests that read `messageId` keep passing).
- If the backend does not emit `message_persisted` (e.g. an older deploy
  is in front of a newer frontend), the hook falls back to
  `done.message_id` so the bubble still gets stamped — see
  `useCopilotStream.test.jsx` for the regression fixture.
- A malformed `message_persisted` payload is silently dropped; the
  stream continues as if the event had not arrived.

### `CopilotDrawer`

`onDone` now pushes `{ id, role, content, citations }` into the
`messages` array. `MessageBubble` accepts an optional `messageId` prop
and applies `data-message-id="<uuid>"` to the bubble's outer `<div>`
when the message is an assistant turn. User bubbles never receive the
attribute — there is no `copilot_messages` row for user turns to rate
in this design (the user is the rater).

### Test fixtures

- `backend/tests/copilot/api/test_message_persisted_sse.py` — six tests
  covering shape, ordering (`message_persisted` precedes
  `done`/`error`), id correlation with the persisted DB row, and the
  strictly-additive invariant.
- `frontend/src/copilot/__tests__/useCopilotStream.test.jsx` — five
  tests covering capture, callback shape, error-path id, the
  backwards-compat fallback to `done.message_id`, and graceful
  handling of malformed payloads.
- `frontend/src/copilot/__tests__/CopilotDrawer.test.jsx` — three new
  tests (data-message-id stamp on assistant bubble, no stamp on user
  bubble, legacy fallback) bringing the file to 25 passing tests.

## What this unblocks

Sub-phase 35-01-E (thumbs-up / thumbs-down UI) can now mount a rating
component anywhere inside the drawer and target the right
`copilot_messages` row by reading `data-message-id` off the closest
ancestor — no extra state plumbing required.

## Reference

- `backend/app/copilot/router.py` — `_sse_stream` and
  `_agent_sse_stream` (search for `message_persisted`).
- `frontend/src/copilot/useCopilotStream.js` — `case
  "message_persisted":` branch and the `resolvedId` reconciliation at
  stream end.
- `frontend/src/copilot/CopilotDrawer.jsx` — `MessageBubble`
  `data-message-id` stamping.
