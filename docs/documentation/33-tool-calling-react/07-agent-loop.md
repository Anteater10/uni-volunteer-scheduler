# Sub-phase 33-07: The Agent Loop

## Purpose

Sub-phases 33-01 through 33-06 stood up the static surface area: an
audit log, a JSON-Schema filter, a role/scope object, a PII redactor, a
tool registry, eight read tools, and the `invoke()` chokepoint that
composes write/run/scrub/update into a single dispatch step. None of
that is animated. A request still needs something to **drive** it —
something that talks to the LLM, decides when to call a tool, when to
stop, and what to emit to the client. That driver is the agent loop in
`backend/app/copilot/agent/loop.py`, and 33-07 is where it lands.

## What the loop is

`run_turn()` is a Python generator. Each call to it represents one
turn of a copilot conversation. Each `yield` it produces is one SSE
event the React frontend consumes. Five event shapes are possible, all
defined as Pydantic models in `app/copilot/agent/events.py`:

- `ToolCallEvent` — "I am about to call `tool` with `args`, the audit
  row is `call_id`."
- `ToolResultEvent` — "Here is the (already redacted) result for
  `call_id`, with `redactions` count for observability."
- `ConfirmationRequestEvent` — "The tool requires human approval; the
  turn has paused. Hit `/confirm` to resume."
- `FinalAnswerEvent` — "I'm done, here's the text."
- `ErrorEvent` — "I'm aborting this turn; here's why."

Each model carries a `Literal` `type` discriminator. The frontend can
dispatch on `event.type` without parsing the rest of the payload. The
backend SSE endpoint (33-08) will encode each model with
`model_dump_json()` and write `data: ...\n\n`. Round-trip serialization
is covered by `tests/copilot/agent/test_events.py`.

## Control flow

A turn proceeds like this:

1. Build the message list: a system prompt grounded in the caller's
   role plus any retrieval context, followed by the user turn.
2. Call `llm.chat(messages=..., tools=[t.json_schema for t in tools])`
   where `tools` is filtered by `registry.get_tools_for_role(scope.role)`.
3. If the response carries `final_answer`, yield `FinalAnswerEvent` and
   return. The turn is over.
4. If the response is neither `final_answer` nor `tool_calls`, increment
   a malformed counter, append a corrective user message, and loop.
5. If the response carries `tool_calls`, iterate. For each one:
   - Enforce the per-turn cap.
   - Look up the tool by name (unknown tool → `ErrorEvent`, return).
   - Write the audit row via `_begin()` to learn the real `call_id`.
   - Yield `ToolCallEvent(call_id=...)`.
   - If the tool requires confirmation, yield
     `ConfirmationRequestEvent` and return — the turn is paused.
   - Otherwise run the tool via `_complete()`, yield `ToolResultEvent`,
     append the JSON-stringified result to `messages` as a `tool` turn,
     and continue the outer loop.

## Hard caps and why

Two caps protect the system from cost and reliability failure modes.

**`MAX_TOOL_CALLS_PER_TURN = 6`** bounds the worst case where the LLM
chains tool calls. Six is generous for the read surface in 33-06 — most
real turns finish in one or two — but small enough that a runaway loop
costs cents, not dollars. When the cap is hit, the loop yields an
`ErrorEvent` with `"cap"` in the message and returns. The audit log
already has rows for every call that fired before the cap, so the trail
is intact.

**`MAX_MALFORMED_RETRIES = 2`** bounds garbage responses from the LLM.
We give it two chances to emit either `tool_calls` or `final_answer`
with a polite corrective message in between, then we abort with
`ErrorEvent("LLM produced unparseable output")`. Two retries is enough
to catch a transient parsing hiccup but cheap enough that a broken
prompt fails fast.

## The `_begin` / `_complete` split

The plan originally had the loop call `invoke()` and yield a
placeholder `call_id` in `ToolCallEvent` before knowing the real one.
We refactored instead: `tools/base.py` now exposes `_begin()` (write
audit row, return `call_id`) and `_complete()` (run handler, scrub
result, stamp audit row). `invoke()` composes both for the existing
non-loop callers. The loop calls `_begin()` first, emits
`ToolCallEvent` with the real `call_id`, then either pauses for
confirmation or runs `_complete()` and emits `ToolResultEvent`. The
call_id therefore matches across both events — a frontend can use it as
a stable correlation key.

## Stub-LLM testing pattern

The loop never imports an LLM client. It takes one as a constructor
argument with a single `chat(messages, tools) -> dict` method. Tests
inject a `_StubLLM` with a scripted list of responses. This is a
strict free-models discipline: no real API calls, no network, no
billing surprises, deterministic asserts. The three tests in
`test_loop.py` cover (1) the happy path with a tool call followed by a
final answer, (2) the cap-enforcement path where ten scripted tool
calls produce a single `ErrorEvent` after the sixth, and (3) the
malformed-retry path where three garbage responses produce an
`ErrorEvent` containing `"unparseable"`.

## How the loop composes with the rest of 33

- `registry` decides which tools are visible to this caller's role.
- `_begin` / `_complete` (the split halves of `invoke`) carry the audit
  + redaction discipline through every call.
- `events.py` defines the wire shapes.
- 33-08 will wrap `run_turn` in a FastAPI SSE endpoint.
- 33-09 will add the React `EventSource` consumer.

The loop itself stays small and policy-only. All security is upstream
(role filter, schema validation) or downstream (redactor, audit log).
That separation is what 33-01 through 33-06 paid for.
