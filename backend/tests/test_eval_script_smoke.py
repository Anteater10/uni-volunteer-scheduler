"""Plan 32-07 smoke tests for the offline RAGAS harness.

These tests live in ``backend/tests/`` so CI picks them up, but they
*never* run the LLM judge — that requires an OpenRouter key, a live
corpus DB, and minutes of wall time. They only assert the *shape* of
the committed artifacts so we catch drift in the column header or the
testset structure that the paper imports verbatim.

The three guard rails:

1. ``test_eval_script_imports_cleanly`` — the harness module is
   importable when ``ragas`` is installed. If ``ragas`` is missing
   (the default CI state, since it is in ``requirements-eval.txt``
   not ``requirements.txt``), the test ``skip``\\s with a clear reason.

2. ``test_testset_artifact_exists`` — the 30-question frozen testset
   parses as JSON and each entry carries the two RAGAS-mandatory
   fields (``question`` + ``ground_truth``).

3. ``test_csv_artifact_columns`` — *if* the CSV exists, its header is
   exactly the locked four-column shape the paper LaTeX expects. The
   CSV may not yet exist (Andy runs the harness offline) so this test
   skips when the file is absent rather than failing.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


# Repo root = backend/ parent — but the docker test container only mounts
# `backend/` at `/app`, so the repo-root sibling dirs (`docs/`, `scripts/`)
# are absent inside the container. We therefore look in two places:
# 1. The real repo root (when running from host: `pytest backend/tests/...`).
# 2. ``/repo`` (an opt-in bind mount the harness developer can pass).
# When neither is present we ``skip`` rather than fail — these artifacts
# are validated at PR review on the host, not in the request-path CI image.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_CANDIDATE_REPO_ROOTS = [
    _BACKEND_ROOT.parent,  # host run
    Path("/repo"),  # opt-in bind mount
]


def _resolve_artifact(rel: str) -> Path | None:
    for root in _CANDIDATE_REPO_ROOTS:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


_TESTSET_REL = "docs/documentation/32-rag-retrieval/eval/testset.json"
_CSV_REL = "docs/documentation/32-rag-retrieval/rerank-lift.csv"
_SCRIPT_REL = "scripts/eval_rerank_lift.py"

_LOCKED_HEADER = ["metric", "rerank_off", "rerank_on", "lift"]


def test_eval_script_imports_cleanly() -> None:
    """Script imports under the eval-deps virtualenv; skip otherwise."""
    pytest.importorskip(
        "ragas",
        reason="ragas not installed; install backend/requirements-eval.txt to run harness",
    )
    pytest.importorskip("matplotlib")
    pytest.importorskip("datasets")

    # Load the script as a module without executing main(). The module
    # is in scripts/ which is not on sys.path by default, so we use
    # importlib.util.spec_from_file_location to load by path.
    script_path = _resolve_artifact(_SCRIPT_REL)
    if script_path is None:
        pytest.skip(
            f"scripts/ not mounted into test container; "
            f"validated on host. Looked under: {_CANDIDATE_REPO_ROOTS!r}"
        )
    spec = importlib.util.spec_from_file_location(
        "eval_rerank_lift", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:
        pytest.skip(f"backend stack not importable from this venv: {exc}")

    # Surface the public entry points the docs / future plans depend on.
    assert hasattr(module, "main"), "harness must expose a main() entry"
    assert hasattr(module, "run"), "harness must expose run(rerank_on, repeats)"


def test_testset_artifact_exists() -> None:
    """30-question frozen testset is present and well-formed."""
    testset_path = _resolve_artifact(_TESTSET_REL)
    if testset_path is None:
        pytest.skip(
            f"docs/ not mounted into test container; "
            f"validated on host. Looked under: {_CANDIDATE_REPO_ROOTS!r}"
        )
    with testset_path.open() as fh:
        data = json.load(fh)
    # Filter out the leading metadata header object (carries `_section`).
    data = [x for x in data if isinstance(x, dict) and not x.get("_section")]
    assert isinstance(data, list), "testset must be a JSON array"
    # Plan says >= 20 items (allows partial human-action state); the
    # final committed artifact carries 30.
    assert len(data) >= 20, f"expected >= 20 questions, got {len(data)}"
    for i, item in enumerate(data):
        assert isinstance(item, dict), f"item {i} not an object"
        assert "question" in item, f"item {i} missing 'question'"
        assert "ground_truth" in item, f"item {i} missing 'ground_truth'"


def test_csv_artifact_columns() -> None:
    """If the CSV is committed, its header matches the paper-locked shape."""
    csv_path = _resolve_artifact(_CSV_REL)
    if csv_path is None:
        pytest.skip(
            "rerank-lift.csv not reachable (docs/ not mounted or not yet generated)"
        )
    with csv_path.open() as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
    assert header == _LOCKED_HEADER, (
        f"CSV header drift: expected {_LOCKED_HEADER!r}, got {header!r}. "
        "The paper LaTeX imports these column names verbatim — do not "
        "rename without coordinating with the writeup."
    )
