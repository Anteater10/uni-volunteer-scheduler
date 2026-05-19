# LLM API Streaming Patterns

A lecture on integrating with chat-completion APIs in production: OpenAI's
streaming protocol (and OpenRouter's compatible surface), primary/fallback
model selection, timeouts, prompt versioning + hashing, token accounting,
and the robustness rules that keep the bill predictable and the parser
honest.

## Why this matters for interviews

LLM features are no longer "AI specialist" turf — every backend role that
touches user-facing product is expected to know how to wire one up. The
interview signals are practical: can you (a) avoid burning the customer
with a 60-second blocking call, (b) handle the wire format without
silently dropping the last few tokens, (c) reason about cost and
reproducibility, and (d) survive when the model provider has a bad
afternoon. None of these require ML knowledge; they're systems-engineering
problems in disguise.

## The design choice

There are two surfaces you can hit on every major chat API:

- **Non-streaming**: one request, you wait, you get a `choices[0].message.content`
  with the full response.
- **Streaming**: one request with `stream: true`, you get a sequence of
  delta chunks over an HTTP response body until the server flushes a final
  `[DONE]` marker (OpenAI/OpenRouter wire format) or closes the connection.

### Why streaming improves perceived latency

For a 300-token reply at ~30 tok/s, the non-streaming call takes ~10 seconds
of dead time. Users staring at a spinner judge that interaction as
unresponsive. With streaming, the user sees the first token in ~200ms and
reads at roughly the same speed the model writes — "perceived latency"
drops by an order of magnitude even though total latency is identical.

Streaming also gives you:

- A cancellation point. The user can abort after they've seen enough,
  saving completion tokens.
- An early-stop opportunity. The server can match a regex against the
  partial stream and cut the connection if the model wanders into a
  jailbreak or PII leak.
- Back-pressure. If your downstream (e.g., SSE to the browser) buffers,
  the LLM client naturally pauses too because the OpenAI SDK iterator
  pulls one chunk at a time.

### Pros and cons

| | Streaming | Non-streaming |
|---|---|---|
| Perceived latency | low (TTFB ~200ms) | high (entire reply) |
| Total wall time | same | same |
| Server FD usage | one open conn per active call | freed immediately |
| Parser complexity | partial-JSON, chunk boundaries | none |
| Error handling | failure mid-stream possible | one place to fail |
| Cancellation | clean | wasted tokens |
| Cost telemetry | needs `include_usage` | always present |

Pick streaming for user-facing chat. Pick non-streaming for batch jobs,
classification, structured extraction where you parse the whole response
at once.

## How it works under the hood

### The OpenAI / OpenRouter wire format

A streaming chat completion is an HTTP/1.1 response with media type
`text/event-stream` (yes, it's literally SSE). Each event has one
`data:` line carrying a JSON object:

```
data: {"id":"chatcmpl-abc","choices":[{"index":0,"delta":{"role":"assistant"}}]}

data: {"id":"chatcmpl-abc","choices":[{"index":0,"delta":{"content":"Hi"}}]}

data: {"id":"chatcmpl-abc","choices":[{"index":0,"delta":{"content":" there"}}]}

data: {"id":"chatcmpl-abc","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: {"id":"chatcmpl-abc","choices":[],"usage":{"prompt_tokens":12,"completion_tokens":3,"total_tokens":15}}

data: [DONE]

```

The notable bits:

- Each `data:` is a full JSON object on one line. Newlines inside the JSON
  would break SSE framing, so the provider promises to emit single-line JSON.
  Don't pretty-print.
- The `delta.content` is the **incremental** text, not the cumulative.
  Concatenate to get the full response.
- The final `[DONE]` literal is not JSON — it's a sentinel. If you naively
  `JSON.parse(line.slice(5))` you'll crash on the last event.
- Usage (`prompt_tokens` / `completion_tokens` / `total_tokens`) only
  arrives if you pass `stream_options: { include_usage: true }`. Older
  endpoints sometimes attach it to the last delta event; newer ones emit
  it as its own dedicated event with an empty `choices` array. **Handle
  both shapes.**

### How chunk boundaries don't align with token boundaries

A common confusion: "the model emitted 30 tokens, so I should see 30 SSE
events." Not true. The provider batches tokens into chunks for efficiency.
You might see one chunk per token, or one chunk per 5 tokens, or weird
patterns based on whether the model is hitting a sampling-heavy region.
Your code must not assume a one-to-one mapping. Just concatenate
`delta.content` into a buffer and render the buffer.

There's a worse failure mode: chunk **byte** boundaries also don't align
with **JSON** boundaries. A single TCP read might land you with:

```
data: {"id":"chatcmpl-abc","cho
```

— the JSON is incomplete. You must buffer until you see `\n\n` (the SSE
event separator) and only then attempt `JSON.parse`. SDKs handle this for
you; if you implement the client yourself, this is the bug.

### How the OpenAI SDK abstracts it

The Python SDK gives you a synchronous iterator that handles all of this:

```python
stream = client.chat.completions.create(
    model="...",
    messages=[...],
    stream=True,
    stream_options={"include_usage": True},
)
for event in stream:
    choices = event.choices
    if choices:
        chunk = choices[0].delta.content
        if chunk:
            yield chunk
    if event.usage:
        yield_usage(event.usage)
```

The SDK does the chunked-encoding decode, the SSE parse, the JSON parse,
and gives you typed objects. You give up some control (you can't easily
inspect the raw bytes for debugging) in exchange for not writing the
parser. For a production system, use the SDK; for an interview question
"implement the client", be ready to discuss the parser.

### OpenRouter compatibility

OpenRouter exposes an OpenAI-compatible surface at
`https://openrouter.ai/api/v1`. Point the OpenAI SDK's `base_url` at it
and pass `model: "<provider>/<model-id>"` (e.g., `openai/gpt-4o-mini`,
`meta-llama/llama-3.3-70b-instruct`). OpenRouter routes to the underlying
provider, normalizes the response shape, and returns it as if you'd hit
OpenAI directly. This is the pattern this codebase uses.

The advantage: one client, many models, normalized billing, automatic
provider failover at OpenRouter's layer. The cost: an extra hop of
latency (small) and the occasional shape difference where OpenRouter
emits something the SDK didn't expect.

## How this codebase uses it

The integration is split into two files. The router
[`backend/app/copilot/router.py`](../../../backend/app/copilot/router.py)
handles HTTP, persistence, and the SSE envelope to the browser. The LLM
client [`backend/app/copilot/llm.py`](../../../backend/app/copilot/llm.py)
handles streaming, model selection, and usage extraction.

### Client setup — point OpenAI SDK at OpenRouter

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

The `timeout` is the **per-request** timeout (currently 60 seconds, see
`backend/app/config.py`). A single LLM call that hangs longer than this
raises `APITimeoutError` which is handled by the fallback logic.

### Primary → fallback model retry

```python
# backend/app/copilot/llm.py
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
)

def _candidates() -> list[str]:
    return [
        settings.copilot_primary_model,    # "openai/gpt-oss-120b:free"
        settings.copilot_fallback_model,   # "meta-llama/llama-3.3-70b-instruct:free"
    ]

def stream_completion(*, messages, max_tokens=None):
    client = _client()
    last_exc = None
    for model_id in _candidates():
        try:
            yield from _stream_one(
                client=client, model_id=model_id,
                messages=messages, max_tokens=max_tokens,
            )
            return
        except _RETRYABLE as exc:
            logger.warning("copilot_model_retryable_failure model=%s err=%s",
                           model_id, exc.__class__.__name__)
            last_exc = exc
            continue
    raise last_exc
```

Key design choices encoded here:

- **Retry list is finite and explicit.** Two models, no infinite loop.
  If both fail, the original exception bubbles up to the router which
  writes an error row.
- **Only specific exceptions are retried.** Auth failures, validation
  errors, and 400s are NOT retried — they're caller bugs, retrying just
  costs money and delays the error.
- **`yield from` preserves the streaming contract.** The router sees the
  retry as transparent; from its perspective it's still pulling
  `(chunk, meta)` tuples until the stream completes.

### Streaming the response with usage

```python
# backend/app/copilot/llm.py
def _stream_one(*, client, model_id, messages, max_tokens):
    started = time.monotonic()
    kwargs = {
        "model": model_id,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    completion_text: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0

    stream = client.chat.completions.create(**kwargs)
    for event in stream:
        usage = getattr(event, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        choices = getattr(event, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            continue
        chunk = getattr(delta, "content", None)
        if chunk:
            completion_text.append(chunk)
            yield chunk, {}

    latency_ms = int((time.monotonic() - started) * 1000)
    yield "", {
        "model_id": model_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "completion_text": "".join(completion_text),
    }
```

Defensive coding worth pointing out:

- `getattr(event, "usage", None)` — older SDK versions don't have `usage`
  at all on the iterator items. `getattr` with a default is safer than
  attribute access.
- `choices = getattr(event, "choices", None) or []` — the usage-only event
  has `choices: []`. Skipping the empty list avoids an `IndexError` on
  `choices[0]`.
- The terminal yield distinguishes itself by sending an empty token and
  a populated meta dict. The router uses `if meta:` vs `elif chunk:` to
  branch.

### Prompt versioning + hashing

LLM responses are non-deterministic and the prompt matters as much as the
model. To make Phase 35 evals reproducible, every session row stores:

```python
# backend/app/copilot/prompts.py
SYSTEM_PROMPT_VERSION = "v0.1.0"

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```

And every turn's user message records a hash of the **full conversation
history** sent to the model:

```python
# backend/app/copilot/router.py
prompt_blob = json.dumps(chat_messages, sort_keys=True)
prompt_hash = hashlib.sha256(prompt_blob.encode("utf-8")).hexdigest()
```

`sort_keys=True` is critical: dict iteration order is implementation
detail, so the hash would be unstable across Python versions without it.

### Token accounting

`prompt_tokens` and `completion_tokens` flow from OpenRouter's usage event
into the `copilot_messages` row alongside `latency_ms` and `model_id`.
That row plus the dollar-per-million-tokens for the resolved model gives
you per-message cost. Sum over a user, a day, a model variant, etc., for
your spend dashboard.

## Common pitfalls

### Forgetting `stream_options: { include_usage: true }`

Without it, you get streamed deltas but no token counts at the end. Your
cost dashboard now shows zero spend even though the bill is real. The
OpenAI SDK doesn't warn you. Diagnose by logging the last event's shape;
if `usage` is `None`, you forgot the option.

### Crashing on `[DONE]` if you wrote the parser yourself

```js
// WRONG — this throws on the [DONE] line
const data = JSON.parse(line.slice(5));
```

```js
// RIGHT
const raw = line.slice(5).trim();
if (raw === "[DONE]") { finalize(); continue; }
const data = JSON.parse(raw);
```

The SDK handles this. If you bypass the SDK to save a dependency, you
will hit this bug. Don't.

### Partial JSON chunks

A TCP read can give you `data: {"choices":[{"delta":{"con`. If you
`JSON.parse` immediately you crash. Correct pattern: buffer until you've
seen `\n\n`, then parse the data line. The Python SDK and the OpenAI
JS SDK both buffer for you.

### Tokens that contain newlines

`delta.content` is JSON-string-encoded in the wire format, so a literal
`\n` in the model output arrives as `\\n` in the JSON. After
`JSON.parse`, you're holding a real `\n` in the JS string. If you forward
this to the browser over SSE without re-JSON-encoding it,
you've put a literal `\n` in your `data:` line — which the browser will
interpret as the start of a new line, breaking parsing.

This codebase avoids the problem by `json.dumps`-ing each token before
putting it in the SSE `data:` field:

```python
yield _sse_format("token", json.dumps(chunk))
```

### Retrying non-retryable errors

If the model rejects your prompt for safety reasons (HTTP 400 with a
specific error code), retrying with a different model rarely helps —
it'll usually reject too, and you've doubled the latency for nothing.
This codebase's `_RETRYABLE` tuple excludes generic `APIError` for
exactly this reason.

### Streaming without timeouts

A model that gets stuck mid-response can hold your worker for hours. The
OpenAI SDK's `timeout` parameter is the **whole-request** timeout — the
clock starts at the request and stops when the stream closes. Set it
generously (60s here) but always set it.

For a stricter "no progress in N seconds" timeout, you have to instrument
the iterator yourself: every time you receive a chunk, reset a wall-clock
deadline; if no chunk arrives by the deadline, raise and close the
stream. Worth doing for long-running streams; this codebase doesn't yet.

### Sending the system prompt on every turn instead of caching it

For long system prompts (multi-page rule sets), you pay for
`prompt_tokens` on every single turn. OpenAI's prompt caching kicks in
automatically if the prefix exceeds 1024 tokens; below that, you're
paying full freight. Be conscious of the cost model when designing
prompts.

### Not pinning model IDs

`openai/gpt-4o-mini` resolves to "whatever OpenAI calls the mini model
today." When they ship `gpt-4o-mini-2026-01-01`, your responses shift
under you. Pin to the dated variant in production so your evals stay
comparable. This codebase uses `openai/gpt-oss-120b:free` and
`meta-llama/llama-3.3-70b-instruct:free` which are themselves moving
targets — fine for a beta, worth pinning before the eval phase ships.

## Interview Q&A

**Q (mid):** Walk me through the OpenAI streaming chat completion wire
format.
**A:** HTTP/1.1 response, `Content-Type: text/event-stream`. Each event
is a `data: <json>` line followed by a blank line. JSON shape is
`{id, choices: [{index, delta: {content, role?, tool_calls?},
finish_reason}], usage?}`. `delta.content` is the incremental text —
you concatenate it to assemble the reply. The stream ends with a
sentinel `data: [DONE]\n\n`. To get token counts, pass
`stream_options: {include_usage: true}` and the server emits a
final event with empty `choices` and a populated `usage` object.

**Q (mid):** Why use streaming for an LLM chat UI?
**A:** Perceived latency. The user sees the first token in ~200ms
instead of waiting ~10 seconds for the full response. Streaming also
enables cancellation (user closes the tab, you stop generating and
stop paying), early stopping on safety regex, and natural back-pressure
to a downstream consumer.

**Q (mid):** How do you handle a model that times out mid-stream?
**A:** Use the SDK's `timeout` parameter (whole-request timeout) plus
a retry policy that catches specific exceptions —
`APIConnectionError`, `APITimeoutError`, `RateLimitError`,
`APIStatusError` — and re-tries against a fallback model. Critically,
don't blanket-retry on `APIError`: that catches 4xx user errors where
retrying just doubles the cost. This repo's `llm.py` uses exactly this
pattern: a `_RETRYABLE` tuple and a `for model_id in _candidates()`
loop with `yield from` to preserve the streaming contract.

**Q (mid):** How do you track LLM spend?
**A:** Pass `stream_options: {include_usage: true}` so the server emits
a final event with `prompt_tokens` and `completion_tokens`. Persist
both, plus `model_id` and `latency_ms`, to a row keyed by
session/turn. Join against a price table at query time so model price
changes don't corrupt historical numbers. This repo stores those four
fields on `copilot_messages` per turn.

**Q (senior):** How would you make LLM responses reproducible for an
eval harness?
**A:** Three sources of non-determinism to pin down. (1) Model
version — use dated variants (`gpt-4o-mini-2026-01-01`), not floating
aliases. (2) Sampling — set `temperature: 0` and a fixed `seed`
(supported on some models). (3) Inputs — hash the full message array
(`sha256(json.dumps(messages, sort_keys=True))`) and store the hash on
the eval row so any drift in your prompt construction is detectable.
This repo stores `system_prompt_hash` on the session and `prompt_hash`
on each turn for exactly this reason. Note: even with all three pinned,
many providers don't guarantee determinism — flag this in your eval
report.

**Q (senior):** Design a streaming chat API for 100k concurrent users
backed by an LLM provider with strict per-minute rate limits.
**A:** Three layers. (1) **Browser → app**: SSE. One open response per
active turn, fronted by an HTTP/2 LB so each TLS connection multiplexes
many streams. (2) **App → provider**: a queue + worker pool with global
rate limiter, so 100k users can be waiting but only N hit OpenRouter at
once. Worker pulls a job, opens a stream, fans tokens out to the
waiting browser stream via a pub/sub bus (Redis Streams). (3)
**Resilience**: primary/fallback model selection, per-model rate
limiters tracked by your code (not just by the provider's 429s),
circuit breaker that pauses requests to a degraded provider for 30
seconds. Add prompt caching at the app layer for repeated system
prompts to cut prompt-token spend. Cost telemetry on every turn,
realtime dashboards by model and user cohort.

**Q (senior):** How do you handle prompt injection in a streaming chat
app?
**A:** Defense in depth. (1) Treat user-supplied text as data, not
instructions — wrap it in clear delimiters in the prompt, and tell the
model in the system prompt that anything inside those delimiters is
untrusted. (2) Use the OpenAI Moderation API or a small classifier on
the user message **before** the call. (3) Stream-time pattern matching:
if the model starts emitting something that looks like a leaked system
prompt or a tool call to a privileged action, cut the stream. (4)
Capability boundaries: don't give the model a tool that can do
irreversible damage (delete data, send email, transfer funds) without
human confirmation. This codebase mitigates the worst case by giving
the model no live data access at all — see the system prompt in
`backend/app/copilot/prompts.py` which is explicit about that.

**Q (senior):** Your streaming endpoint sometimes drops the last few
tokens. How do you debug?
**A:** Three suspects to rule out in order. (1) **Parser**: are you
`JSON.parse`-ing a complete event, or attempting parse on a partial
buffer? Log the raw bytes before parse. Most likely your SSE buffer
loop discards the un-terminated tail when the connection closes
without a final `\n\n`. Fix by treating "stream end" as an implicit
event terminator. (2) **Proxy buffering**: nginx/Cloudflare may close
the connection before flushing the last buffered chunk. Set
`X-Accel-Buffering: no` and `Cache-Control: no-transform`. (3)
**Provider behaviour**: some providers emit the final tokens
in the same chunk as the `finish_reason`. If you're iterating with
`if delta.content: ...` and skipping events with no content, you might
also be skipping the event that carries the last newline. Inspect the
full event, not just `delta.content`.

## Further reading

- OpenAI: [Streaming chat completions](https://platform.openai.com/docs/api-reference/streaming)
- OpenAI: [`stream_options: include_usage`](https://platform.openai.com/docs/api-reference/chat/create#chat-create-stream_options)
- OpenAI Python SDK: [streaming guide](https://github.com/openai/openai-python#streaming-responses)
- OpenRouter: [OpenAI-compatible API](https://openrouter.ai/docs/quick-start)
- Anthropic: [Streaming messages](https://docs.anthropic.com/en/api/messages-streaming) — same idea, different envelope (different event names like `content_block_delta`)
- "[Token caching](https://platform.openai.com/docs/guides/prompt-caching)" — OpenAI's automatic caching for repeated prompt prefixes
