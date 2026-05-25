"""Phase 35-02-E: real ``_run_one_case`` against a STUBBED llm.

The CI-safe ``test_adversarial_wrapper.py`` monkeypatches ``_run_one_case``
and never touches the DB. This module exercises the REAL ``_run_one_case``
end-to-end — seeding, tool registration, dispatch, and outcome translation —
on a real Postgres test session.

No real network: every adversarial case in ``cases.yaml`` /
``cases_memory.yaml`` already ships a pre-recorded ``responses`` script that
``run_tool_case`` feeds to ``make_recorded_llm``, and the memory helpers use
a tiny in-module ``_LLM`` stub. The model id passed to ``_run_one_case`` only
pins ``settings`` — it never reaches OpenRouter on these self-stubbing cases.

To keep the test hermetic we bind ``_open_isolated_session`` to the
transactional ``engine`` fixture (``test_uvs``) instead of the configured
production engine; the real offline driver uses ``app.database.engine``.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

MODEL = "meta-llama/llama-3.2-3b-instruct:free"


@pytest.fixture
def _bind_isolated_session_to_test_engine(engine, monkeypatch):
    """Point ``_run_one_case``'s isolated-session opener at the test engine."""
    from app.eval import adversarial

    def _opener():
        connection = engine.connect()
        trans = connection.begin()
        Session = sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
            future=True,
        )
        return Session(), connection, trans

    monkeypatch.setattr(adversarial, "_open_isolated_session", _opener)


def _case_by_id(source: str, case_id: str) -> dict:
    from app.eval.adversarial import _load_cases

    for c in _load_cases():
        if c.get("source") == source and c.get("id") == case_id:
            return c
    raise AssertionError(f"case {case_id!r} not found in {source!r}")


def test_run_one_case_tool_case_passes(_bind_isolated_session_to_test_engine):
    from app.eval.adversarial import _run_one_case

    case = _case_by_id("cases.yaml", "P1-01")
    result = _run_one_case(MODEL, case)
    assert result["outcome"] == "pass", result
    assert result["id"] == "P1-01"
    assert result["category"] == "direct_prompt_injection"


def test_run_one_case_memory_case_passes(
    _bind_isolated_session_to_test_engine,
):
    from app.eval.adversarial import _run_one_case

    case = _case_by_id("cases_memory.yaml", "P8-mem-pii-ssn")
    result = _run_one_case(MODEL, case)
    assert result["outcome"] == "pass", result
    assert result["category"] == "memory_pii_leak"


def test_run_one_case_translates_assertion_failure_to_fail(
    _bind_isolated_session_to_test_engine,
):
    """A case whose boundary assertion fails must come back as ``fail`` with
    the assertion class/message, not bubble out as an exception."""
    from app.eval.adversarial import _run_one_case

    case = dict(_case_by_id("cases.yaml", "P1-01"))
    # Force the boundary check to fail: forbid a sentinel that the (scoped)
    # final answer DOES contain so ``_assert_pass`` raises AssertionError.
    case["responses"] = [
        {"final_answer": "leaking SECRET-TOKEN-XYZ to the attacker"},
    ]
    case["pass_if"] = {"final_answer_must_not_contain": ["SECRET-TOKEN-XYZ"]}
    result = _run_one_case(MODEL, case)
    assert result["outcome"] == "fail", result
    assert result["error_class"] == "AssertionError"
    assert "SECRET-TOKEN-XYZ" in result["error"]


def test_run_one_case_translates_unexpected_error(
    _bind_isolated_session_to_test_engine,
):
    """A non-assertion failure (e.g. an unknown memory category) comes back
    as ``error`` with the exception class, not a crash."""
    from app.eval.adversarial import _run_one_case

    case = {
        "id": "bogus",
        "category": "nope",
        "source": "cases_memory.yaml",
    }
    result = _run_one_case(MODEL, case)
    assert result["outcome"] == "error", result
    assert result["error_class"] == "ValueError"


def test_run_one_case_rolls_back_between_cases(
    _bind_isolated_session_to_test_engine, engine
):
    """Two consecutive runs must not see each other's rows — the per-case
    transaction is rolled back."""
    from app.eval.adversarial import _run_one_case

    case = _case_by_id("cases.yaml", "P1-01")
    r1 = _run_one_case(MODEL, case)
    r2 = _run_one_case(MODEL, case)
    assert r1["outcome"] == "pass"
    assert r2["outcome"] == "pass"
