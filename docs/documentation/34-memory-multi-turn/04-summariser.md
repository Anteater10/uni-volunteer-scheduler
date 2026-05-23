# 34-04 — Within-session summariser

> Sub-phase 34-04 of Phase 34 (memory + multi-turn). Module:
> `backend/app/copilot/memory/summariser.py`.

## What it does

The agent loop builds a list of chat messages every turn — system
prompt, prior user/assistant exchanges, any tool calls and tool
results, and the new user message. As that list grows, two failure
modes appear:

1. **Token-window overflow.** OpenRouter free models have small
   context windows (8k–32k). A long volunteer-scheduling session can
   blow past that.
2. **Cost growth.** Even when the window fits, every turn re-sends the
   entire history. Cost grows quadratically over a session.

`compress_if_needed(...)` is called before every `llm.chat()`. If the
estimated token count exceeds `threshold * context_window` (default
70 %), it rolls older turns into a single synthetic system message
(`"## Conversation so far\n<synopsis>"`) and keeps the last N
user/assistant pairs (default 2) verbatim. The result is a shorter
message list that still gives the model the recent working context
plus a one-paragraph recap of what came before.

## Public surface

```python
compress_if_needed(
    messages,
    *,
    llm,
    model,
    context_window,
    threshold=0.7,
    working_set_pairs=2,
) -> list[dict]
```

- `messages` — the OpenAI-shaped chat history (`role`, `content`,
  optional `tool_calls`, optional `name`).
- `llm` — any object with a `.chat(messages, tools=None) -> dict`
  method. The dict's `final_answer` (or `content`) field is read as
  the synopsis text.
- `model` — model id, used only to pick the tokenizer.
- `context_window` — passed by the caller because OpenRouter doesn't
  expose this uniformly.
- `threshold` / `working_set_pairs` — knobs, surfaced for tests and
  future tuning.

Returns either the original `messages` unchanged (under threshold, or
nothing to roll up) or a new list shaped
`[*leading_system_msgs, synthetic_synopsis, *working_set]`.

## Algorithm

1. Estimate token count via `_token_count(messages, model=model)`.
   This uses `tiktoken.encoding_for_model(model)` when available, and
   falls back to `cl100k_base` otherwise — see "Why cl100k_base"
   below.
2. If `used < threshold * context_window`, return `messages` as-is.
3. Split into leading system messages and the "body".
4. Walk the body backwards, counting `user` messages. After
   `working_set_pairs` user turns, the cut index marks where the
   working set begins.
5. If `older` (everything before the cut) is empty, return `messages`
   unchanged — the working set already covers the whole conversation.
6. Build a single-user-turn prompt via `_build_compression_prompt` and
   call `llm.chat(...)`. If the LLM call raises, the synopsis becomes
   the sentinel `"[summariser failed; older turns dropped]"` so the
   loop keeps going instead of crashing the user's request.
7. Return `system_msgs + [synthetic_synopsis] + working_set`.

## Why we recompute every turn instead of persisting

A persistent rolling summary (e.g. a `summary_so_far` column on the
session) saves one LLM call per long turn but introduces drift: every
update is a lossy re-compression of the previous summary plus new
turns, and after enough rounds the synopsis becomes a game of
telephone. Recomputing from the raw message list every time keeps the
synopsis grounded in the actual conversation. The cost is one extra
LLM call per turn *only when over threshold*, which is rare — most
sessions never trip the 70 % bar.

## Why 70 % and 2 pairs as v1 knobs

- **70 % threshold.** Empirically, leaving 30 % of the window free
  gives the model enough room for its own response plus a few tool
  call/result round-trips before the next compression check. Lower
  thresholds compress too aggressively; higher thresholds let the
  window blow up mid-tool-call.
- **2 pairs working set.** Volunteers ask short, contextual follow-up
  questions ("what about next week?"). Keeping the last two
  exchanges verbatim preserves enough referent for the model to
  resolve those pronouns without bloating the prompt.

Both numbers are surfaced as keyword arguments so we can A/B them
later without changing call sites.

## Why we fall back to `cl100k_base`

OpenRouter routes many free / non-OpenAI models (Mistral, Llama-3,
Qwen, etc.) which do *not* ship a tokenizer registered with
`tiktoken.encoding_for_model`. Without a fallback, `_token_count`
would raise on every non-GPT model. `cl100k_base` is the encoding
used by GPT-3.5 / GPT-4 family models and has become the de-facto
standard tokenizer for OpenAI-compatible chat surfaces. Token counts
under it are an approximation — close enough to make the 70 %
compression decision, not exact enough to bill the user.

## Tests

`backend/tests/copilot/memory/test_summariser.py` covers:

- `_token_count` returns 0 for empty input and positive ints for
  string content + tool calls.
- `compress_if_needed` is a no-op under threshold (no LLM call made).
- Over threshold, the last two `user`/`assistant` pairs survive
  verbatim.
- Older `tool_call` and `tool_result` entries are rolled into the
  synopsis prompt (verified by asserting the tool name appears in
  the prompt sent to the stub LLM, and no `tool` role remains in
  the returned list).
- The synopsis is exactly one synthetic system message sitting
  between the leading system prompt and the working set.

All eight tests run inside the docker test container per CLAUDE.md
conventions, with `--no-cov` (the project-wide coverage gate stays
intact via Phase 32-08 per-package thresholds).
