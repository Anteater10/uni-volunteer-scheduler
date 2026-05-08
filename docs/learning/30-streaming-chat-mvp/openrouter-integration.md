# OpenRouter and the `openai` SDK

> _Stub — to be filled in alongside `app/copilot/llm.py`._

## Why this matters

Hardcoding ourselves to a single vendor (OpenAI, Anthropic, Google) makes
the eventual multi-model evaluation in Phase 35 painful. OpenRouter is a
reverse proxy: one API key and one base URL gives us routed access to
~100 models from many vendors, including a curated free tier. For a
research project that *must* compare models, this is the path of least
friction.

## The intuition (to expand)

- The OpenAI Chat Completions API became a de-facto interface. Other
  vendors implemented it.
- OpenRouter speaks that interface and proxies to the right vendor based
  on the `model` parameter.
- The `openai` Python SDK accepts a `base_url`. Point it at OpenRouter
  and it just works — no fork, no patching.

## The mechanism (to expand)

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
)
```

- Free-tier models advertised with the `:free` suffix.
- Streaming via `stream=True`; iterate `client.chat.completions.create(...)`.

## Why we chose it here (to expand)

- Free-tier inference for the prod copilot — non-negotiable for SciTrek
  budget.
- One swap to compare models in Phase 35 — research-critical.

## What to read next

- OpenRouter docs — "Quickstart" and "Models" pages.
- OpenAI Python SDK README — `base_url` configuration.
