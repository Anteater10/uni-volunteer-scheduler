# 34-05 — Wiring the summariser into the agent loop

> Sub-phase 34-05 of Phase 34 (memory + multi-turn). Module:
> `backend/app/copilot/agent/loop.py`.

## What changed

The Phase 33 agent loop was history-blind. `run_turn` rebuilt a
two-message preamble (`[system, user]`) on every call and shipped it
straight to `llm.chat()`. With Phase 34-04 we now have a working
summariser (`compress_if_needed`); 34-05 is the seam that calls it.

Two new keyword arguments land on `run_turn`:

```python
def run_turn(
    *,
    db,
    llm,
    scope,
    session_id,
    user_message: str,
    retrieval_context: str,
    model: str | None = None,
    context_window: int = CONTEXT_WINDOW_DEFAULT,
) -> Iterator[Any]:
```

`model` resolves the tokenizer; `context_window` is the budget
`compress_if_needed` measures against. Both default sensibly, so every
existing caller (router, tests, future scripts) continues to work
unchanged.

## The call site

Compression runs exactly once, at the top of `run_turn`, immediately
after the initial `[system, user]` preamble is assembled and before
the ReAct `while True:` loop begins:

```python
messages = compress_if_needed(
    messages,
    llm=llm,
    model=resolved_model,
    context_window=context_window,
)

while True:
    response = llm.chat(...)
    ...
```

This is the "once per turn" invariant. The loop's interior may append
tool-call/tool-result messages as the model dispatches tools, but we
deliberately do *not* re-run `compress_if_needed` inside the loop.
Section "Why once per turn" below explains why.

## Model resolution

When the caller omits `model`, `run_turn` calls `_default_model()`,
which tries to read `app.core.config.settings.copilot_primary_model`
and falls back to the literal string `"gpt-3.5-turbo"` if settings
can't be imported (e.g. in unit tests without an `.env`). The fallback
is safe because the summariser's tokenizer treats unknown model ids by
dropping to `cl100k_base` (see `docs/documentation/34-memory-multi-turn/04-summariser.md`).

```python
def _default_model() -> str:
    try:
        from app.core.config import settings
        return settings.copilot_primary_model or "gpt-3.5-turbo"
    except Exception:
        return "gpt-3.5-turbo"
```

This is intentionally permissive. We do not want a stray import-time
failure (missing env var in a CI image, mis-stubbed settings) to
crash an entire copilot turn — the worst case is a slightly
inaccurate token count.

## Cache-once-per-turn invariant

`compress_if_needed` is called exactly once per `run_turn`
invocation. The implications:

- The summariser LLM call (when compression triggers) costs one extra
  request per *turn*, never per *tool iteration*. A 6-tool-call turn
  pays the same compression overhead as a 1-tool-call turn.
- Tool results appended mid-turn can in principle push the message
  list back over the 70 % threshold (a fat `get_module_roster` blob,
  for example). We accept this. The next user turn will recompress.
  The alternative — re-running the summariser between tool calls —
  costs an LLM round-trip per tool dispatch and risks summarising
  half-finished reasoning.

The tool-call cap (`MAX_TOOL_CALLS_PER_TURN = 6`) bounds the worst-
case mid-turn growth. Six tool results is small relative to the 30 %
headroom the threshold leaves.

## Error-handling contract

`compress_if_needed` itself catches summariser LLM failures and
returns a sentinel synopsis (`"[summariser failed; older turns
dropped]"`) — see 34-04 docs. From `run_turn`'s perspective the
function is total: it always returns a list of messages. There is no
try/except in the loop because there's nothing to catch.

If for any reason `compress_if_needed` raises (a bug, not an LLM
error), the exception propagates up through `run_turn`. We do **not**
swallow it: an internal bug in the summariser pipeline should be
loud, not silently bypass compression and let the next `llm.chat()`
blow the window.

## Backward compatibility

Short conversations don't trigger compression. With the default
`CONTEXT_WINDOW_DEFAULT = 8192` and a typical two-message preamble
(~200 tokens), `_token_count` returns well under `0.7 * 8192 = 5734`
tokens, so `compress_if_needed` returns `messages` unchanged. The
LLM stub in `test_run_turn_no_compression_for_short_default_conversation`
asserts this: exactly one `llm.chat` call, messages reach the model
verbatim, no summariser invocation.

Every existing loop test (`test_loop.py`, `test_loop_memory.py`,
the tool-call regression tests) continues to pass without
modification.

## Tests

`backend/tests/copilot/agent/test_loop_memory.py` covers:

1. `run_turn` calls `compress_if_needed` with the `model` and
   `context_window` kwargs passed in.
2. When `model` is omitted, `run_turn` resolves a non-empty default
   and threads the default `CONTEXT_WINDOW_DEFAULT`.
3. With a tiny context window and a 6-turn synthetic history, the
   summariser LLM fires first (tools=None), then the main LLM
   receives `[*system, synopsis, *working_set]` — older turns are
   rolled into the synopsis and not present verbatim.
4. With defaults and a short conversation, no summariser call is
   made and the LLM sees `[system, user]` exactly.

Run via the standard docker pytest harness with `--no-cov`.
