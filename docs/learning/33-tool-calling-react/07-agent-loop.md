# Lecture 33-07: The Agent Loop — Where Static Surface Area Becomes a Conversation

## Where we are

We've spent six sub-phases building static parts: an audit log, a
schema filter, a scope object, a redactor, a registry, eight tools, and
one chokepoint called `invoke()`. None of it talks to an LLM. None of
it knows what a "turn" is. If a user sends a message right now, nothing
happens — there is no engine on top of the chassis.

33-07 is the engine. One file (`loop.py`), one generator (`run_turn`),
five event types (`events.py`), and three tests. That's the whole
sub-phase. It animates everything below it and gives 33-08 (the SSE
endpoint) and 33-09 (the React stream consumer) something concrete to
plug into.

## Why event types are typed

`events.py` could have been five `TypedDict`s. We used Pydantic models
with `Literal` `type` fields instead. Two reasons:

1. **Validation at the boundary.** The SSE encoder calls
   `model_dump_json()` and trusts the result. If the loop ever passes a
   bad shape — say, a `dict` where a `ToolResultEvent` was expected —
   Pydantic blows up loudly in the loop, not silently in the frontend.
2. **A literal discriminator means the frontend doesn't have to think.**
   `event.type === "tool_call"` is enough. No structural inference, no
   "does this dict have a `call_id`?" checks. The contract is the
   shape, and the shape is the contract.

## Walking through the happy path

The plan's first test scripts two LLM responses:

```
[
  {"tool_calls": [{"name": "list_modules", "args": {"week": "2026-W22"}}]},
  {"final_answer": "There are 3 modules running."},
]
```

The loop:

1. Builds messages: a system prompt that names the caller's role plus
   any retrieval context, then the user's question.
2. Calls `llm.chat(messages=..., tools=[...])`.
3. Sees `tool_calls`. Iterates. Looks up `list_modules` in the registry.
4. Calls `_begin(db, tool=..., scope=..., args=..., session_id=...)` —
   writes the audit row with `confirmation_status='not_required'`,
   returns the real `call_id`.
5. Yields `ToolCallEvent(call_id, tool="list_modules", args=...)`.
6. Calls `_complete(db, call_id=..., tool=..., scope=..., args=...)` —
   runs the handler, scrubs the result, stamps the audit row.
7. Yields `ToolResultEvent(call_id, result=..., redactions=0)`.
8. Appends `{"role": "tool", "name": "list_modules", "content": "<json>"}`
   to messages and loops.
9. Second LLM response is `{"final_answer": "..."}`. Yields
   `FinalAnswerEvent` and returns.

Three events, in order: `tool_call → tool_result → final_answer`. The
test asserts on the event type list and on the final text.

## Why we split `invoke()`

The plan had a sharp corner. `invoke()` already does
write-audit → maybe-pause → run → scrub → update-audit. From the
outside that's the right grain. From inside the loop it's
*one step too coarse* — because we want to emit `ToolCallEvent` carrying
the real `call_id`, and the real `call_id` only exists after the audit
row is written. The plan's workaround was to emit
`ToolCallEvent(call_id="tmp")` and then re-correlate later. We did not
ship that.

Instead, we split `invoke()` in `tools/base.py` into:

- `_begin(db, *, tool, scope, args, session_id) -> call_id`
- `_complete(db, *, call_id, tool, scope, args) -> {call_id, result, redactions}`

`invoke()` itself is now `call_id = _begin(...); if requires_confirmation: ... ; return _complete(...)`.
All the existing `invoke`-based tests still pass because the public
behavior is identical. The loop now uses the two halves directly and
the call_id flows from `_begin` through both `ToolCallEvent` and
`ToolResultEvent`. The test asserts `events[0].call_id == events[1].call_id`.

## The two hard caps

`MAX_TOOL_CALLS_PER_TURN = 6` and `MAX_MALFORMED_RETRIES = 2`. Both
are about budget — money for the first, latency for the second.

For the cap test we hand the stub LLM **ten** identical tool-call
responses. The loop runs the first six, yielding `tool_call` and
`tool_result` for each, then on the seventh iteration sees
`tool_calls_used >= 6`, yields `ErrorEvent("tool call cap reached")`,
and returns. The audit log keeps the six executed rows.

For the malformed test we hand it three `{"garbage": "x"}` responses.
The loop sees no `tool_calls` and no `final_answer`, so it increments
`malformed` and appends a corrective user message. After the third
malformed response, `malformed > 2`, and we yield
`ErrorEvent("LLM produced unparseable output")`. We never touch the DB
in that path, so the test passes `db=None`.

## Stub LLMs and free-models discipline

The loop takes the LLM as a parameter. It calls one method, `chat`, and
expects a dict back. That's it. Tests inject a `_StubLLM` with a
hand-written list of responses. No real API calls happen during the
test suite. This is non-negotiable: the project policy is "free models
only in tests," and the cheapest free model is the one you wrote
yourself.

This also means the loop is testable end-to-end without any LLM
dependency, which keeps CI fast and deterministic.

## What confirmation pauses look like

None of the eight read tools require confirmation, so the
confirmation-pause branch isn't exercised yet. The shape is there:
`_begin` returns a `call_id`, we yield `ToolCallEvent`, then —
because `tool.requires_confirmation` is true — we yield
`ConfirmationRequestEvent(call_id, tool, args, preview)` and **return**.
The audit row sits in `confirmation_status='pending'`. A later
`/confirm` endpoint will look up the row, either run `_complete` or
mark it denied, and emit the next batch of events on a fresh SSE
stream.

## The system prompt is grounded in scope

`_system_prompt(scope, retrieval_context)` interpolates `scope.role`
into the prompt. This is a defense-in-depth measure: the role filter
already prevents the LLM from *seeing* tools it isn't allowed to call,
but if the model still hallucinates a wrong tool name we want the
prompt itself to remind it whose scope it's in. The retrieval context
slot is where Phase 32's RAG output gets stitched in.

## Composition recap

`run_turn` composes:

- `registry.get_tools_for_role(scope.role)` — what's visible
- `tools.base._begin` and `_complete` — audit + redaction discipline
- `events.*` — the SSE wire shapes

Each piece was built and tested in isolation. The loop just orchestrates
them. That's why this sub-phase is *small*: every hard problem was
solved upstream.
