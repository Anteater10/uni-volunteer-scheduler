"""Phase 35-02-B — model registry.

Locks the 8 OpenRouter free-tier candidate models we evaluate, the Phase 33
baseline (current production primary), and the ``set_model_for_replay``
helper that pins BOTH ``copilot_primary_model`` and ``copilot_fallback_model``
to the same value for the duration of one replay.

Why pin both? ``app.copilot.llm._candidates()`` returns
``[primary, fallback]`` and silently swaps on any retryable error. If we
only set primary, a 429 on a small model would produce results from the
70B fallback and contaminate the per-model row. See spec §13(b).

Free-tier invariant: every ID ends in ``:free``. ``assert_free_tier()`` is
the startup guard imported by ``app.eval.run``.
"""
from __future__ import annotations

from typing import Any

from app.config import settings


# 3 flagship + 2 mid + 3 small. Provider mix: Meta×2, Nous, DeepSeek,
# Qwen, Google, OpenAI, NVIDIA. Verified `:free` on 2026-05-23 (spec §2.1).
CANDIDATE_MODELS: tuple[str, ...] = (
    # flagship
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-v4-flash:free",
    # mid
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "google/gemma-4-31b-it:free",
    # small
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "meta-llama/llama-3.2-3b-instruct:free",
)

# Phase 33 baseline — current production primary. Spec §13(e): commit one
# frozen run of the adversarial suite against this model as the 9th
# comparison point so the paper can show "what the current primary scores."
BASELINE_MODEL: str = "openai/gpt-oss-120b:free"

# RAGAS judge — pinned across the entire comparison so scoring is identical
# across models. Spec §6.1.
RAGAS_JUDGE_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"

# Context window pinned for every replay (spec §2.1) so flagship models do
# not get a context-size advantage in RAGAS.
PINNED_CONTEXT_TOKENS: int = 131_072


def assert_free_tier() -> None:
    """Startup guard — every model the harness can route to must be :free."""
    for mid in CANDIDATE_MODELS:
        assert mid.endswith(":free"), (
            f"model in registry does not end in :free: {mid!r}"
        )
    assert BASELINE_MODEL.endswith(":free"), (
        f"baseline is not :free: {BASELINE_MODEL!r}"
    )
    assert RAGAS_JUDGE_MODEL.endswith(":free"), (
        f"RAGAS judge is not :free: {RAGAS_JUDGE_MODEL!r}"
    )


def set_model_for_replay(
    model_id: str, *, monkeypatch: Any | None = None
) -> None:
    """Pin both primary and fallback for the duration of one replay.

    Pass ``monkeypatch`` from a pytest fixture for test-scoped overrides;
    pass ``None`` for the CLI path (mutates ``settings`` directly).
    """
    if not model_id.endswith(":free"):
        raise ValueError(
            f"refusing to pin model that does not end in :free: {model_id!r}"
        )
    if monkeypatch is not None:
        monkeypatch.setattr(settings, "copilot_primary_model", model_id)
        monkeypatch.setattr(settings, "copilot_fallback_model", model_id)
    else:
        settings.copilot_primary_model = model_id
        settings.copilot_fallback_model = model_id


__all__ = [
    "CANDIDATE_MODELS",
    "BASELINE_MODEL",
    "RAGAS_JUDGE_MODEL",
    "PINNED_CONTEXT_TOKENS",
    "assert_free_tier",
    "set_model_for_replay",
]
