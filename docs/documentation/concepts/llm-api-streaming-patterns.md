# LLM API Streaming Patterns — Reference

Operational reference for the OpenAI / OpenRouter chat-completion
streaming integration in this repo. Pairs with
[`docs/learning/concepts/llm-api-streaming-patterns.md`](../../learning/concepts/llm-api-streaming-patterns.md)
which has the lecture-length explanation.

## TL;DR

- Streaming chat completions ride on SSE (`text/event-stream`). Each
  event is one JSON object on a single `data:` line. Stream ends with
  `data: [DONE]`.
- Each event's `choices[0].delta.content` carries an **incremental**
  string. Concatenate to assemble.
- Pass `stream_options: {include_usage: true}` to receive
  `prompt_tokens` and `completion_tokens` in a terminal event.
- This repo wraps OpenAI's Python SDK against an OpenRouter `base_url`.
  Primary + fallback model selection retries on connection / timeout /
  429 / 5xx.
- Each turn's prompt is SHA-256-hashed and the hash, model id, token
  counts, and latency are stored on the `copilot_messages` row.

## Streaming envelope

### Wire format (server → client between OpenRouter and our backend)

```
data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","model":"openai/gpt-oss-120b:free","choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"}}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" there"}}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[],"usage":{"prompt_tokens":12,"completion_tokens":3,"total_tokens":15}}

data: [DONE]

```

### Event shape

Each `data:` line (except the terminal sentinel) is one JSON object:

```ts
type StreamChunk = {
  id: string;
  object: "chat.completion.chunk";
  model?: string;
  choices: Array<{
    index: number;
    delta: {
      role?: "assistant" | "tool";
      content?: string;          // incremental text — concatenate
      tool_calls?: Array<{...}>;
    };
    finish_reason?: "stop" | "length" | "content_filter" | "tool_calls";
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
};
```

Notes:

- `choices` may be `[]` on the usage-only event. Code must skip empty.
- `delta.content` may be missing on the very first event (role-only)
  and on `finish_reason` events. Skip on missing.
- `finish_reason` arrives on its own event, after the last content
  event. Useful for distinguishing `stop` (model done) from `length`
  (hit `max_tokens` and was truncated).

### Terminal sentinel

The literal six bytes `[DONE]` after `data: `. Not JSON. The SDK
recognizes this and closes the iterator; if you implement the client
yourself, branch on the raw line before `JSON.parse`.

## API surface

### Configuration

```python
# backend/app/config.py
copilot_enabled: bool = False
copilot_primary_model: str = "openai/gpt-oss-120b:free"
copilot_fallback_model: str = "meta-llama/llama-3.3-70b-instruct:free"
copilot_request_timeout_seconds: int = 60
copilot_max_completion_tokens: int = 1024
```

### Client construction

```python
# backend/app/copilot/llm.py
from openai import OpenAI

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

def _client() -> OpenAI:
    return OpenAI(
        base_url=_OPENROUTER_BASE_URL,
        api_key=settings.openrouter_api_key or "missing",
        timeout=settings.copilot_request_timeout_seconds,
    )
```

### Streaming call

```python
stream = client.chat.completions.create(
    model="openai/gpt-oss-120b:free",
    messages=[{"role": "system", "content": "..."},
              {"role": "user", "content": "..."}],
    stream=True,
    stream_options={"include_usage": True},
    max_tokens=1024,
)
for event in stream:
    usage = getattr(event, "usage", None)
    if usage is not None:
        prompt_tokens = usage.prompt_tokens or 0
        completion_tokens = usage.completion_tokens or 0
    choices = getattr(event, "choices", None) or []
    if not choices:
        continue
    chunk = getattr(choices[0].delta, "content", None)
    if chunk:
        # render chunk
        ...
```

### Retry envelope used in this repo

```python
# backend/app/copilot/llm.py
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
)

def stream_completion(*, messages, max_tokens=None):
    client = _client()
    last_exc = None
    for model_id in [settings.copilot_primary_model,
                     settings.copilot_fallback_model]:
        try:
            yield from _stream_one(client=client, model_id=model_id,
                                   messages=messages, max_tokens=max_tokens)
            return
        except _RETRYABLE as exc:
            last_exc = exc
            continue
    raise last_exc
```

Iterator contract: yields `(chunk_text, {})` for each token chunk, then a
terminal `("", meta_dict)` where `meta_dict` carries `model_id`,
`prompt_tokens`, `completion_tokens`, `latency_ms`, and `completion_text`.

## Usage in this codebase

| Concern | File | Detail |
|---|---|---|
| OpenAI SDK against OpenRouter | `backend/app/copilot/llm.py` | `base_url = "https://openrouter.ai/api/v1"` |
| Primary/fallback retry | `backend/app/copilot/llm.py` — `stream_completion` | Two-model list, retry on `_RETRYABLE` |
| Streaming + usage extraction | `backend/app/copilot/llm.py` — `_stream_one` | `stream=True`, `stream_options.include_usage=True` |
| Timeout | `backend/app/copilot/llm.py` | SDK whole-request timeout from settings (60s default) |
| Token chunking to browser | `backend/app/copilot/router.py` — `_sse_stream` | Each LLM chunk becomes one SSE `event: token` |
| Persistence | `backend/app/copilot/router.py` | Writes `CopilotMessage` row at stream end with all telemetry |
| System prompt versioning | `backend/app/copilot/prompts.py` | `SYSTEM_PROMPT_VERSION = "v0.1.0"` + `hash_prompt(...)` |
| Per-turn prompt hash | `backend/app/copilot/router.py` | `sha256(json.dumps(chat_messages, sort_keys=True))` |

### What lands in the database

Every turn produces one row in `copilot_messages` for the assistant turn,
with these telemetry fields populated:

| Column | Source | Use |
|---|---|---|
| `content` | concatenated `delta.content` | Conversation history |
| `model_id` | terminal meta from `_stream_one` | Which model actually answered (primary or fallback) |
| `prompt_tokens` | `usage.prompt_tokens` | Cost — input side |
| `completion_tokens` | `usage.completion_tokens` | Cost — output side |
| `latency_ms` | `time.monotonic` deltas in `_stream_one` | Performance dashboard |
| `prompt_hash` | sha256 of sorted-key JSON of message list | Eval reproducibility |
| `response_hash` | sha256 of full completion text | Eval reproducibility |
| `error` | exception class name if stream failed | Error rate dashboard |

The session row records `model_id` (intended primary), `system_prompt_hash`,
and `system_prompt_version`. The per-message `model_id` records what
actually answered, which can differ when fallback kicks in.

### What does NOT land in the database

- Per-chunk delta timing (only end-to-end `latency_ms`)
- Raw SSE bytes (only the final concatenated text)
- Provider-internal request IDs (would be useful for cross-referencing
  OpenRouter's dashboard; not stored today)

## Operational concerns

### Proxy buffering

The same nginx / Cloudflare / ALB buffering rules from
`docs/documentation/concepts/server-sent-events.md` apply to the
browser-facing SSE response. They also apply to the OpenRouter ↔ backend
hop if you have a proxy in between (you usually don't — the OpenAI SDK
talks straight to OpenRouter over TLS).

Symptom: tokens arrive in big batches separated by long pauses. Fix is
`X-Accel-Buffering: no` and `Cache-Control: no-cache, no-transform` on
the SSE response from FastAPI.

### Reconnect storms

Each browser-side stream is initiated by a user clicking Send, so
reconnect-on-drop isn't automatic in this app's design — the user
either retries or starts a new turn. If automatic reconnect is added
later, the `Last-Event-ID` header would need a corresponding `id:`
field in the SSE events and a way for the server to resume mid-stream
from the LLM provider. OpenAI doesn't support resume; the only way is
to replay the conversation history and start over.

### Cost tracking

Per-message: `prompt_tokens * input_price + completion_tokens *
output_price`. Price table is per-model and changes over time; pin
historical prices by snapshotting them with the model ID at the time
of the call (not done today — a known gap for Phase 35).

Per-session: sum across the session's messages.

Per-user / per-role: join `copilot_sessions` to `users` and aggregate.

Per-day: time-bucket on `created_at`.

### Rate limits

OpenRouter passes through per-model rate limits. The free tier of
`openai/gpt-oss-120b:free` and `meta-llama/llama-3.3-70b-instruct:free`
has aggressive per-minute caps. In production with paid models this is
less of an issue but still must be planned for.

Today the retry envelope catches `RateLimitError` and falls back to the
secondary model, which has its own (independent) rate limit. If both
are rate-limited the request fails and a row with `error =
"RateLimitError"` is persisted.

### Timeouts

The SDK's `timeout` is the whole-request timeout — from request issue
through stream close. Setting too low truncates legitimate long
responses; setting too high lets stuck calls hold workers. Current
value (60s) is sufficient for a 1024-token completion at typical model
throughput.

There's no per-chunk timeout today. A "model emits the first 50 tokens
then stalls for 5 minutes" failure mode would consume a worker until the
60s whole-request timeout fires. If this becomes an issue, instrument
the iterator with a `time.monotonic` deadline reset on each chunk.

### Prompt safety

The system prompt
[`backend/app/copilot/prompts.py`](../../../backend/app/copilot/prompts.py)
is explicit that the model has no live data access. This is the primary
mitigation for prompt-injection-driven data exfiltration: there's no
data to exfiltrate. When live data tools are added in a later phase, the
threat model needs to be re-evaluated — see `docs/copilot-journal/` for
the architecture discussion.

### Cancellation

The browser side uses `AbortController` to cancel the `fetch`. When the
TCP connection closes, FastAPI's `StreamingResponse` generator gets a
`GeneratorExit` or similar on its next `yield`; the OpenAI SDK's
underlying HTTP connection then notices its consumer is gone and closes.

The completion tokens consumed up to the cancellation point are still
billed by OpenRouter — cancellation reduces future spend, not past
spend.

## Glossary

- **chat.completion.chunk** — `object` value on streaming events,
  distinguishing them from the non-streaming `chat.completion`.
- **completion tokens** — Tokens in the model's generated reply. Billed at
  the output price.
- **delta** — The incremental field of a streaming event. Contains the
  new bytes since the last event, not the cumulative response.
- **finish_reason** — `"stop"` (model ended naturally), `"length"`
  (hit `max_tokens`), `"content_filter"` (provider safety), `"tool_calls"`
  (model wants to invoke a tool).
- **`include_usage`** — Option in `stream_options` that adds a terminal
  event with `usage: {prompt_tokens, completion_tokens, total_tokens}`.
- **`max_tokens`** — Cap on completion length. Output truncates with
  `finish_reason: "length"` when hit.
- **OpenRouter** — Provider-of-providers. Exposes the OpenAI Chat
  Completions API surface and routes the request to one of many
  underlying providers (OpenAI, Anthropic, Meta, Google, etc.) keyed by
  the `model` parameter.
- **primary / fallback model** — Two-model retry pattern: try primary,
  fall back to secondary on `_RETRYABLE` exceptions, error if both fail.
- **prompt caching** — OpenAI feature where a long static prompt prefix
  (>1024 tokens) is cached server-side and not re-billed at full price
  on subsequent calls with the same prefix.
- **prompt hash** — `sha256(json.dumps(messages, sort_keys=True))`,
  stored with each assistant message for eval reproducibility.
- **prompt tokens** — Tokens in the input message list. Billed at the
  input price.
- **`stream_options`** — OpenAI chat completion parameter holding
  stream-specific options. `{include_usage: true}` is the only widely
  useful field today.
- **TTFB (time-to-first-byte)** — Time from request issue to the first
  delta event. Primary perceived-latency metric for streaming chat.
- **whole-request timeout** — Timeout that covers the entire request
  including the stream. Different from a per-chunk no-progress timeout.
