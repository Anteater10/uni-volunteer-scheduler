# OpenRouter as the Inference Gateway

> _Stub — to be filled in alongside `app/copilot/llm.py`._

## Summary

We use OpenRouter as the inference gateway for the AI Onboarding Copilot.
OpenRouter exposes an OpenAI-compatible Chat Completions API surface that
proxies requests to a curated catalog of provider models, including a
free-of-charge tier. This decision is motivated by two project
constraints: (1) zero direct inference spend for the SciTrek deployment,
and (2) the Phase 35 evaluation requires drop-in model substitution
across heterogeneous providers.

## Configuration

- Base URL: `https://openrouter.ai/api/v1`
- SDK: `openai` Python SDK with `base_url` override.
- Authentication: `OPENROUTER_API_KEY` (project secret).
- Primary and fallback model IDs: locked at execution start; recorded in
  Phase 30 SUMMARY.

## Limitations

- Free-tier rate limits are rolling; production traffic past the limit
  surfaces as `429`. We treat this as a recoverable error and surface a
  user-visible chip.
- Free-tier models change SKU over time; we pin the model ID and revisit
  on schedule.

## References

- OpenRouter documentation — to be cited at fill-in.
