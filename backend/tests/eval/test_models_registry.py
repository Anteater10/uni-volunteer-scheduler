"""Phase 35-02-B: model registry invariants.

Asserts every model ID in the registry ends in `:free`, the count matches
the spec (8 candidates + 1 baseline = 9), and the `set_model_for_replay`
helper writes both primary AND fallback env-backed settings.
"""
from __future__ import annotations

import pytest

from app.config import settings


def test_all_candidate_models_are_free():
    from app.eval.models import CANDIDATE_MODELS, BASELINE_MODEL

    assert len(CANDIDATE_MODELS) == 8
    for mid in CANDIDATE_MODELS:
        assert mid.endswith(":free"), f"{mid!r} is not a :free model"
    assert BASELINE_MODEL.endswith(":free")


def test_baseline_matches_phase_33_primary():
    """Spec §13(e) — baseline is the current production primary."""
    from app.eval.models import BASELINE_MODEL

    assert BASELINE_MODEL == "openai/gpt-oss-120b:free"


def test_set_model_for_replay_pins_both_primary_and_fallback(monkeypatch):
    """Critical: see Plan-vs-reality preamble #2 point (4)."""
    from app.eval.models import set_model_for_replay

    set_model_for_replay(
        "meta-llama/llama-3.3-70b-instruct:free", monkeypatch=monkeypatch
    )
    assert settings.copilot_primary_model == (
        "meta-llama/llama-3.3-70b-instruct:free"
    )
    assert settings.copilot_fallback_model == (
        "meta-llama/llama-3.3-70b-instruct:free"
    )


def test_set_model_for_replay_rejects_paid_model(monkeypatch):
    from app.eval.models import set_model_for_replay

    with pytest.raises(ValueError, match=":free"):
        set_model_for_replay("openai/gpt-4o", monkeypatch=monkeypatch)


def test_assert_free_tier_startup_check_passes():
    from app.eval.models import assert_free_tier

    assert_free_tier()  # must not raise


def test_assert_free_tier_rejects_paid_intruder(monkeypatch):
    """If someone adds a non-:free entry, the startup assertion fires."""
    from app.eval import models as eval_models

    monkeypatch.setattr(
        eval_models,
        "CANDIDATE_MODELS",
        eval_models.CANDIDATE_MODELS + ("openai/gpt-4o",),
    )
    with pytest.raises(AssertionError, match=":free"):
        eval_models.assert_free_tier()


def test_testset_does_not_reference_non_free_models():
    """No question's required_tools or notes can route to a paid model.

    Defends against a future contributor adding a 'gpt-4o' reference that
    bypasses the harness's :free pin. Already covered by the testset schema
    test for notes — this test extends to required_tools entries.
    """
    from importlib.resources import files
    import yaml

    raw = (files("app.eval") / "testset.yaml").read_text()
    questions = (yaml.safe_load(raw) or {}).get("questions", [])
    for q in questions:
        rt = q.get("required_tools") or []
        for entry in rt:
            for v in (entry.get("args") or {}).values():
                if isinstance(v, str) and "/" in v and ":" in v:
                    assert v.endswith(":free"), (
                        f"{q['id']} arg references non-:free model id {v!r}"
                    )
