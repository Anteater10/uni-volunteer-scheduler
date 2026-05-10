# OpenRouter and the `openai` SDK

## Why this matters

We are building a copilot that needs to call a large language model.
There are five or so credible providers (OpenAI, Anthropic, Google,
Mistral, Meta-via-Together, etc.) and each has its own API surface,
authentication scheme, and pricing. If we hardwire the project to one
of them we get three nasty consequences:

1. **Phase 35 becomes a rewrite.** That phase is the multi-model
   evaluation that anchors the paper. If the call site only knows how
   to talk to one vendor, we either rewrite it or write a weaker paper.
2. **A vendor outage takes the app down.** When Anthropic's API
   degraded for two hours last quarter, every product wired directly
   to it was unusable.
3. **A free-tier model swap requires a code change.** SciTrek has zero
   inference budget. We need free models, and the free-model SKU
   churns. Hardcoding it locks us into whichever model was free the day
   we shipped.

OpenRouter solves all three. It is a reverse proxy in front of ~100
models from many vendors, and it speaks the *same* OpenAI Chat
Completions API that the `openai` Python SDK already targets.

## The intuition

The OpenAI Chat Completions API became the lingua franca of LLM
inference. It is the format every shop checks they're compatible with
because too many client libraries hardcode it. OpenRouter took
advantage of that gravity: their API endpoint *is* the OpenAI endpoint,
just at a different host. The `model` parameter — a string like
`"openai/gpt-oss-120b:free"` or `"meta-llama/llama-3.3-70b-instruct:free"`
— picks which upstream provider to route to. From the client's
perspective, there is one API. From the operator's perspective, there
are 100 backends.

The `openai` Python SDK is built around an `OpenAI(api_key, base_url)`
class. The whole SDK is just a typed HTTP client; nothing assumes
"openai.com" except the default `base_url`. If you point `base_url` at
OpenRouter, every method on the SDK still works.

## The mechanism

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
    timeout=settings.copilot_request_timeout_seconds,
)

stream = client.chat.completions.create(
    model="openai/gpt-oss-120b:free",
    messages=[{"role": "user", "content": "hi"}],
    stream=True,
    stream_options={"include_usage": True},
)
for event in stream:
    chunk = event.choices[0].delta.content
    if chunk:
        ... # forward to SSE
```

`stream_options={"include_usage": True}` tells OpenRouter to emit a
final chunk that contains `prompt_tokens` and `completion_tokens`. This
is critical — without it, we cannot do cost analysis in Phase 35.

## The mechanism, in our codebase

`backend/app/copilot/llm.py` is small on purpose. It exposes one main
function:

```python
def stream_completion(*, messages, max_tokens=None) -> Iterator[tuple[str, dict]]:
    ...
```

Each non-final yield is `(chunk_text, {})`. The terminal yield is
`("", {"model_id": ..., "prompt_tokens": ..., "completion_tokens": ...,
"latency_ms": ..., "completion_text": ...})`.

The function tries the primary model first. If it raises a *retryable*
exception — `APIConnectionError`, `APITimeoutError`, `RateLimitError`,
or any `APIStatusError` (the SDK wrapper around 4xx/5xx) — we
transparently retry against the fallback model. Any other exception
(auth error, validation error, our own bug) is re-raised immediately.

The candidate list is currently two models, locked at config time:

```python
def _candidates() -> list[str]:
    return [
        settings.copilot_primary_model,    # openai/gpt-oss-120b:free
        settings.copilot_fallback_model,   # meta-llama/llama-3.3-70b-instruct:free
    ]
```

Two design choices buried in this function are worth flagging:

1. **No silent vendor swap on validation errors.** If the prompt is too
   long for the primary, retrying on the fallback would mask the bug
   that produced an over-long prompt. We re-raise so the structured
   error log catches it.
2. **One client, many candidates.** The same `OpenAI()` instance is
   reused across attempts. The host is OpenRouter regardless; only the
   `model` parameter changes.

## Why we chose OpenRouter over direct vendor APIs

- **Free-tier inference for the prod copilot** — non-negotiable for the
  SciTrek budget. OpenRouter aggregates free SKUs.
- **One swap to compare models in Phase 35** — research-critical.
  Changing `model="openai/gpt-oss-120b:free"` to
  `model="anthropic/claude-haiku-4-5"` is a one-line diff, not a
  client-library swap.
- **Resilience.** When one upstream goes down, OpenRouter often stays
  up because the others don't. Even if we never use it for routing
  smarts, it is a load-bearing piece of our uptime story.

The cost is one extra hop of latency (typically 50–100ms) and a fuzzy
SLA. Both are acceptable for an internal admin copilot.

## What to read next

- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart) — five-minute setup.
- [OpenRouter Models](https://openrouter.ai/models) — current free-tier SKUs.
- [OpenAI Python SDK README](https://github.com/openai/openai-python) — `base_url` is in the constructor section.
- [Anthropic streaming reference](https://docs.anthropic.com/en/api/messages-streaming) — useful when Phase 35 wants direct comparison.
