"""Phase 35-02-D: RAGAS adapter unit tests. No real network — the judge
LLM is stubbed via a fake ``score_one`` callable injected into the adapter.

The single ``_default_judge`` integration test is skip-guarded twice: it
needs ``ragas`` installed (not in CI — ``requirements-eval.txt`` only) AND a
real ``OPENROUTER_API_KEY`` (it hits OpenRouter's free tier). CI skips it
cleanly; Andy runs it for real locally.
"""
from __future__ import annotations

import os

import pytest


def test_score_trace_empty_answer_returns_null_metrics():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "",
        "prompt": "hi",
        "retrieved_context": [{"doc_id": "d1", "snippet": "x"}],
    }
    question = {"gold": "irrelevant"}
    out = score_trace(trace, question, judge=lambda *_a, **_kw: {
        "faithfulness": 1.0, "answer_relevancy": 1.0, "context_precision": 1.0,
    })
    assert out == {
        "faithfulness": None, "answer_relevancy": None,
        "context_precision": None,
    }


def test_score_trace_no_context_skips_context_precision():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "answer text",
        "prompt": "hi",
        "retrieved_context": [],
    }
    question = {"gold": "answer text"}

    def _judge(**kwargs):
        return {
            "faithfulness": 0.9, "answer_relevancy": 0.9,
            "context_precision": 0.5,
        }

    out = score_trace(trace, question, judge=_judge)
    assert out["faithfulness"] == 0.9
    assert out["answer_relevancy"] == 0.9
    assert out["context_precision"] is None


def test_score_trace_judge_error_records_null(monkeypatch):
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "text",
        "prompt": "hi",
        "retrieved_context": [{"doc_id": "d", "snippet": "s"}],
    }
    question = {"gold": "text"}

    def _judge(**_kw):
        raise RuntimeError("judge unreachable")

    out = score_trace(trace, question, judge=_judge)
    assert out == {
        "faithfulness": None, "answer_relevancy": None,
        "context_precision": None,
    }


def test_score_trace_passes_values_through_on_happy_path():
    from app.eval.metrics.ragas import score_trace

    trace = {
        "final_answer": "the answer",
        "prompt": "the question",
        "retrieved_context": [{"doc_id": "d", "snippet": "the answer"}],
    }
    question = {"gold": "the answer"}
    out = score_trace(trace, question, judge=lambda **_: {
        "faithfulness": 0.81, "answer_relevancy": 0.79, "context_precision": 0.74,
    })
    assert out == {
        "faithfulness": 0.81, "answer_relevancy": 0.79, "context_precision": 0.74,
    }


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="needs OPENROUTER_API_KEY — _default_judge hits OpenRouter",
)
def test_default_judge_returns_three_floats_against_openrouter():
    """Real RAGAS path. Skipped in CI (no ragas, no key). When Andy runs it
    locally with ``pip install -r backend/requirements-eval.txt`` and a real
    key, it must return the three metric keys as floats-or-None."""
    pytest.importorskip("ragas")
    from app.eval.metrics.ragas import _default_judge

    out = _default_judge(
        question="What is the SciTrek volunteer scheduler?",
        answer="It is an app for scheduling UCSB SciTrek volunteers.",
        gold="An app for scheduling UCSB SciTrek volunteers.",
        context=["SciTrek is a UCSB program that schedules student volunteers."],
    )
    assert set(out) == {"faithfulness", "answer_relevancy", "context_precision"}
    for k, v in out.items():
        assert v is None or isinstance(v, float), f"{k}={v!r}"


def _install_fake_ragas_stack(monkeypatch, *, df):
    """Inject fake ``ragas`` / ``datasets`` / ``langchain_*`` modules into
    ``sys.modules`` so ``_default_judge`` runs end-to-end offline.

    Lets us cover the real import-and-call path (Dataset build, evaluate call,
    dataframe extraction) without ragas installed or any network. ``df`` is the
    pandas DataFrame the fake ``evaluate(...).to_pandas()`` returns.
    """
    import sys
    import types

    captured: dict = {}

    class _MetricObj:
        def __init__(self, name):
            self.name = name

    faithfulness = _MetricObj("faithfulness")
    answer_relevancy = _MetricObj("answer_relevancy")
    context_precision = _MetricObj("context_precision")

    class _Result:
        def to_pandas(self):
            return df

    def _evaluate(ds, *, metrics, llm, embeddings, run_config):
        captured["ds"] = ds
        captured["metrics"] = metrics
        captured["llm"] = llm
        captured["embeddings"] = embeddings
        return _Result()

    class _Dataset:
        def __init__(self, rows):
            self.rows = rows

        @classmethod
        def from_list(cls, rows):
            captured["rows"] = rows
            return cls(rows)

    datasets_mod = types.ModuleType("datasets")
    datasets_mod.Dataset = _Dataset

    langchain_openai_mod = types.ModuleType("langchain_openai")
    langchain_openai_mod.ChatOpenAI = lambda **kw: ("chat", kw)

    langchain_hf_mod = types.ModuleType("langchain_huggingface")
    langchain_hf_mod.HuggingFaceEmbeddings = lambda **kw: ("emb", kw)

    ragas_mod = types.ModuleType("ragas")
    ragas_mod.evaluate = _evaluate

    ragas_embeddings_mod = types.ModuleType("ragas.embeddings")
    ragas_embeddings_mod.LangchainEmbeddingsWrapper = lambda e: ("wrap-emb", e)

    ragas_llms_mod = types.ModuleType("ragas.llms")
    ragas_llms_mod.LangchainLLMWrapper = lambda llm: ("wrap-llm", llm)

    ragas_metrics_mod = types.ModuleType("ragas.metrics")
    ragas_metrics_mod.faithfulness = faithfulness
    ragas_metrics_mod.answer_relevancy = answer_relevancy
    ragas_metrics_mod.context_precision = context_precision

    ragas_run_config_mod = types.ModuleType("ragas.run_config")
    ragas_run_config_mod.RunConfig = lambda **kw: ("run-config", kw)

    for name, mod in {
        "datasets": datasets_mod,
        "langchain_openai": langchain_openai_mod,
        "langchain_huggingface": langchain_hf_mod,
        "ragas": ragas_mod,
        "ragas.embeddings": ragas_embeddings_mod,
        "ragas.llms": ragas_llms_mod,
        "ragas.metrics": ragas_metrics_mod,
        "ragas.run_config": ragas_run_config_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    return captured


class _FakeCol:
    def __init__(self, value):
        self._value = value

    @property
    def iloc(self):
        return [self._value]


class _FakeDF:
    """Minimal stand-in for a one-row pandas DataFrame — pandas isn't in the
    CI image (eval-only dep), so we model just what ``_pick`` touches:
    ``in df.columns`` and ``df[col].iloc[0]``."""

    def __init__(self, row: dict):
        self._row = row

    @property
    def columns(self):
        return list(self._row.keys())

    def __getitem__(self, key):
        return _FakeCol(self._row[key])


def test_default_judge_extracts_floats_with_fake_ragas(monkeypatch):
    """Cover the full ``_default_judge`` body offline via fake modules."""
    df = _FakeDF(
        {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.7}
    )
    captured = _install_fake_ragas_stack(monkeypatch, df=df)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.eval.metrics.ragas import _default_judge

    out = _default_judge(
        question="q", answer="a", gold="g", context=["c1", "c2"],
    )
    assert out == {
        "faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.7,
    }
    # Env wiring: OPENROUTER_API_KEY forwarded to OPENAI_API_KEY + base URL set.
    assert os.environ["OPENAI_API_KEY"] == "sk-or-fake"
    assert os.environ["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1"
    # Single-row dataset built with the expected columns.
    assert captured["rows"] == [
        {"question": "q", "answer": "a", "contexts": ["c1", "c2"],
         "ground_truth": "g"},
    ]


def test_default_judge_drops_nan_and_missing_columns(monkeypatch):
    """``_pick`` returns None for NaN cells and absent columns."""
    # faithfulness NaN -> None; context_precision column absent -> None.
    df = _FakeDF({"faithfulness": float("nan"), "answer_relevancy": 0.5})
    _install_fake_ragas_stack(monkeypatch, df=df)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")

    from app.eval.metrics.ragas import _default_judge

    out = _default_judge(question="q", answer="a", gold="g", context=[])
    assert out["faithfulness"] is None
    assert out["answer_relevancy"] == 0.5
    assert out["context_precision"] is None
