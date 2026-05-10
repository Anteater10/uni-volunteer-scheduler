# OpenRouter as the Inference Gateway

## Summary

We use OpenRouter as the inference gateway for the AI Onboarding
Copilot. OpenRouter exposes an OpenAI-compatible Chat Completions API
surface that proxies requests to a curated catalog of provider models,
including a free-of-charge tier. This decision is motivated by three
project constraints: (1) zero direct inference spend for the SciTrek
deployment; (2) the Phase 35 evaluation requires drop-in model
substitution across heterogeneous providers; and (3) gateway-level
failover increases availability during provider outages.

## Configuration

| Setting | Value |
|---|---|
| Base URL | `https://openrouter.ai/api/v1` |
| SDK | `openai` Python SDK ≥ 1.40, with `base_url` override |
| Authentication | `OPENROUTER_API_KEY` (project secret) |
| Request timeout | `COPILOT_REQUEST_TIMEOUT_SECONDS` (default 60s) |
| Max completion tokens | `COPILOT_MAX_COMPLETION_TOKENS` (default 1024) |
| Primary model | `openai/gpt-oss-120b:free` |
| Fallback model | `meta-llama/llama-3.3-70b-instruct:free` |

Model identifiers are recorded per-row on `copilot_messages.model_id`
so that fallback events are observable in the research dataset.

## Failover policy

The client attempts the primary model first. The following exception
classes from the `openai` SDK trigger a transparent retry against the
fallback model:

- `APIConnectionError` — transport-layer failure
- `APITimeoutError` — request exceeded the configured timeout
- `RateLimitError` — HTTP 429 from the gateway or the upstream provider
- `APIStatusError` — any non-2xx status not covered above (5xx, 503, 502)

All other exceptions (authentication errors, invalid request
validation, internal exceptions) propagate immediately. If the
fallback also raises a retryable error, the most recent exception is
re-raised; the calling router is responsible for writing an error row
to `copilot_messages` with the exception class name in the `error`
column.

## Streaming and usage reporting

The client invokes `chat.completions.create` with `stream=True` and
`stream_options={"include_usage": True}`. The upstream emits an
incremental sequence of chat-completion chunks; the final chunk
contains a `usage` object with `prompt_tokens` and `completion_tokens`.
Both are recorded on the persisted assistant row. Without this option,
token-level cost analysis in Phase 35 would not be possible.

## Limitations

- Free-tier rate limits are rolling and not published; production
  bursts past the limit surface as HTTP 429 and are mapped to
  `RateLimitError`. Failover absorbs the first such event; sustained
  rate limiting will surface to the user as an `error` event.
- Free-tier model SKUs change over time; the model identifier is
  pinned at configuration and the SUMMARY document for Phase 30
  records the exact strings used during evaluation.
- OpenRouter adds approximately 50–100 ms of routing latency relative
  to a direct call to the upstream provider. This overhead is recorded
  per-request in `copilot_messages.latency_ms` and is therefore
  visible to the Phase 35 analysis.
- OpenRouter does not currently provide a structured signal for
  detecting which upstream provider answered a given request beyond
  the `model_id`. Per-provider availability statistics in the paper
  are derived externally from OpenRouter's status reports.

## Security posture

The OpenRouter API key is stored in `backend/.env` and read via
Pydantic settings. No prompts or completions are stored at OpenRouter
beyond the duration of the request when the `:free` SKUs are used (per
their data policy, accessed 2026-05-08). All telemetry is retained
in-app in `copilot_messages`.

## References

- OpenRouter, "Quickstart" —
  https://openrouter.ai/docs/quickstart (accessed 2026-05-08).
- OpenRouter, "Models" catalog —
  https://openrouter.ai/models (accessed 2026-05-08).
- OpenAI, Python SDK README, `base_url` configuration —
  https://github.com/openai/openai-python (accessed 2026-05-08).
- OpenAI, Chat Completions streaming reference —
  https://platform.openai.com/docs/api-reference/streaming (accessed 2026-05-08).
