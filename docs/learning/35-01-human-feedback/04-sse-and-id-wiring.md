# Learning — wiring a persisted-row id through a streaming UI

## The puzzle

The copilot streams tokens with Server-Sent Events. A single turn looks
like this on the wire:

```
event: meta
data: {"citations": [...], "retrieval_latency_ms": 12, ...}

event: token
data: "Hel"

event: token
data: "lo!"

event: done
data: {"message_id": "9b0a0d6e-..."}
```

The frontend assembles the tokens into a string and, once `done` arrives,
pushes a new `{ role: "assistant", content }` object into a React
`messages` array. The drawer re-renders, the bubble appears, and the
user reads the answer.

That worked for Phase 30. The trouble starts when we want to **rate** the
answer. A thumb-up button on the bubble has to send `POST
/api/v1/copilot/messages/{id}/rating`. Which `{id}`?

The `done` payload had it — but by the time `done` arrives we are about
to close the stream, run `onDone`, and stuff a plain `{ role, content }`
into state. The id is on the floor.

You could rebuild it from state ("the last assistant bubble"), but that
is brittle: it breaks the moment a turn races with a confirmation card
or a tool result. A robust UI stamps the id onto the DOM at the moment
the bubble is rendered, and lets the rating button read it off the
ancestor.

## Three places that need to know the id

1. **The DB** — already knows. The `copilot_messages.id` UUID is
   generated when the row is inserted.
2. **The stream** — sees the id at `_sse_format("done", ...)`. By that
   point we have already committed the row.
3. **The bubble** — wants the id at render time. Currently has nothing.

The fix is to make (2) tell (3) explicitly. We could repurpose `done`,
but `done` is the *terminal* event — using it for "here is the id"
conflates "stream is over" with "row is in the DB". Better to add a
separate event that announces persistence:

```
event: message_persisted
data: {"id": "<uuid>", "role": "assistant"}
```

This event has one job: hand the id to the frontend. It always fires
right after the row is committed. It fires even on the error path
(because we still persist a partial assistant row with `error` stamped,
and the frontend still wants to attach an id so the user can rate a
bad turn). And it fires *before* `done` — so by the time the stream
closes, the hook already has the id buffered.

## Why a new event, not a new field on `done`?

Two reasons.

**Backwards compat with non-terminating turns.** Some agent-loop turns
end on a `confirmation_request` — they pause waiting for the user. We
still persist the assistant text-so-far. A new event lets us emit the
id at *whatever* boundary we like; cramming it into `done` couples it
to a single termination shape.

**Semantic clarity for older clients.** SSE is a "subscribe to a stream
of named events" protocol. The Phase 30 invariant says the `done`
payload is exactly `{"message_id"}`. Old browsers / older deployed
frontends *do not* parse unknown fields out of `done`. They *do*
silently ignore unknown event names. Adding a new event is strictly
additive; adding a new key risks contract drift if any third-party
consumer ever appears.

The test `test_existing_event_shapes_unchanged` codifies that promise.

## How the frontend captures the id

In `useCopilotStream`, the SSE parser is already a `switch` over
`ev.event`. We add a sixth case:

```js
} else if (ev.event === "message_persisted") {
  const body = JSON.parse(ev.data);
  persistedId = body.id;
  persistedRole = body.role || "assistant";
}
```

At end-of-stream we reconcile: `resolvedId = persistedId || messageId`.
The fallback to `messageId` (from `done`) is for the very narrow window
of "old backend, new frontend" — the two ids refer to the same row, so
using either is safe.

Then `onDone` receives `{ id, role, ... }`. The drawer's `onDone`
pushes that `id` into the React state alongside `content` and
`citations`. The `MessageBubble` accepts it as a prop and conditionally
applies `data-message-id={id}` — but only when `role === "assistant"`.

## Why no stamp on user bubbles

A user bubble has a `copilot_messages` row too — but it is the user
*as rater*, not the user as ratee. There is no row for the user to
rate themselves, and treating user messages as rate-able would let a
user thumbs-down their own prompt, which is nonsense.

Stamping the id only on assistant bubbles enforces that ergonomically:
the future rating component can do `el.closest("[data-message-id]")`
and only ever find assistant turns.

## The order of the events matters

The new event is emitted **before** `done`. If we had put it after,
clients that close the stream on `done` (legitimate behaviour — `done`
is the documented "you can stop reading now" signal) would never see
it.

The backend test `test_message_persisted_precedes_done` asserts this
ordering at the wire layer. The error path has the same invariant:
`message_persisted` precedes `error`. The drawer's bubble is pushed
inside `onError` for the error path, so the id has to be already
buffered when that callback fires — otherwise the bubble would render
without a `data-message-id` and the rating UI would be wedged on a
bad-turn bubble, which is exactly the case where we *most* want to
capture a downvote.

## What I'd do differently next time

If I were redesigning the SSE protocol from scratch I'd probably emit
`message_persisted` *first* (right after the row insert, before the
first token of the *next* turn even arrives), and let `done` carry no
payload at all. That separates "the row exists" from "the stream is
over". But the existing protocol is shipped and the strictly-additive
constraint is real — refactoring `done`'s shape would break Phase 30
tests for marginal aesthetic gain.

## Reference

- Backend: `backend/app/copilot/router.py`, search for
  `message_persisted`. Both `_sse_stream` and `_agent_sse_stream` emit
  it from the same position.
- Frontend hook: `frontend/src/copilot/useCopilotStream.js`, the
  `case "message_persisted":` branch and the end-of-stream
  reconciliation.
- Frontend drawer: `frontend/src/copilot/CopilotDrawer.jsx`,
  `MessageBubble`'s conditional `data-message-id` stamp.
- Tests: `backend/tests/copilot/api/test_message_persisted_sse.py`,
  `frontend/src/copilot/__tests__/useCopilotStream.test.jsx`, and the
  three new tests at the bottom of `CopilotDrawer.test.jsx`.
