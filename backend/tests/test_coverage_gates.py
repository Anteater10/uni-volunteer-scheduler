"""Phase 32-08 — regression test that pins the per-package coverage gates.

Tripwire: if a future PR silently lowers --cov-fail-under for any of the three
Phase 32 namespaces (`app.copilot`, `app.copilot.retrieval`, `app.corpus`) below
95, or flips `branch = True` off in `.coveragerc`, this test fails loudly in CI
instead of allowing the gate to degrade unnoticed.

Metadata-only — no DB, no fixtures, runs in well under a second.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest
import yaml

def _discover_paths() -> tuple[Path, Path, Path]:
    """Locate ci.yml, .coveragerc, and the tests dir robustly.

    On a dev checkout `parents[2]` is the repo root. In the docker test image
    only `backend/` is mounted at `/app`, so we fall back to common layouts.
    """
    here = Path(__file__).resolve()
    tests_dir = here.parent  # backend/tests
    backend_dir = tests_dir.parent  # backend
    coveragerc = backend_dir / ".coveragerc"

    candidates = [
        backend_dir.parent / ".github" / "workflows" / "ci.yml",  # dev checkout
        Path("/repo/.github/workflows/ci.yml"),  # docker mount convention
        Path("/workspace/.github/workflows/ci.yml"),
    ]
    ci_yaml = next((p for p in candidates if p.exists()), candidates[0])
    return ci_yaml, coveragerc, tests_dir


CI_YAML, COVERAGERC, TESTS_DIR = _discover_paths()

MIN_THRESHOLD = 95
WHOLE_APP_FLOOR = 90.5
PACKAGES = (
    "app.copilot",
    "app.copilot.retrieval",
    "app.copilot.feedback",
    "app.corpus",
)


def _iter_run_commands(ci_doc: dict) -> list[str]:
    """Flatten every `run:` block across every job/step in the workflow."""
    commands: list[str] = []
    for job in (ci_doc.get("jobs") or {}).values():
        for step in job.get("steps", []) or []:
            run = step.get("run")
            if isinstance(run, str):
                commands.append(run)
    return commands


@pytest.fixture(scope="module")
def ci_workflow() -> dict:
    if not CI_YAML.exists():
        pytest.skip(
            f"ci.yml not reachable at {CI_YAML} — the docker test image only "
            "mounts backend/. CI runs the full repo checkout and exercises "
            "these assertions there."
        )
    return yaml.safe_load(CI_YAML.read_text())


@pytest.fixture(scope="module")
def ci_run_blob(ci_workflow: dict) -> str:
    return "\n".join(_iter_run_commands(ci_workflow))


@pytest.mark.parametrize("package", PACKAGES)
def test_per_package_cov_gate_present(ci_run_blob: str, package: str) -> None:
    """Each of the three namespaces has its own --cov-fail-under invocation."""
    # Match the package as a standalone token (not a prefix of another).
    # E.g. `--cov=app.copilot` must not be satisfied by `--cov=app.copilot.retrieval`.
    pattern = re.compile(
        rf"--cov={re.escape(package)}(?![.\w])"
    )
    assert pattern.search(ci_run_blob), (
        f"Expected a `--cov={package}` invocation in ci.yml run: blocks. "
        f"Phase 32-08 requires per-package gates, not blended coverage."
    )


@pytest.mark.parametrize("package", PACKAGES)
def test_per_package_threshold_at_least_95(ci_run_blob: str, package: str) -> None:
    """The --cov-fail-under that follows each --cov=<pkg> must be >= 95.

    We extract the *entire* pytest invocation containing the package flag and
    assert its --cov-fail-under value is at the floor or higher.
    """
    pkg_re = re.compile(rf"--cov={re.escape(package)}(?![.\w])")
    # Inspect each line — a step's `run:` may span multiple lines.
    matched_threshold = None
    for line in ci_run_blob.splitlines():
        if not pkg_re.search(line):
            continue
        m = re.search(r"--cov-fail-under=(\d+(?:\.\d+)?)", line)
        assert m, (
            f"Line invoking --cov={package} is missing --cov-fail-under: {line!r}"
        )
        threshold = float(m.group(1))
        assert threshold >= MIN_THRESHOLD, (
            f"--cov-fail-under for {package} dropped to {threshold}; "
            f"Phase 32-08 requires >= {MIN_THRESHOLD}."
        )
        matched_threshold = threshold
    assert matched_threshold is not None, (
        f"No --cov={package} invocation found to inspect for --cov-fail-under."
    )


@pytest.mark.parametrize("package", PACKAGES)
def test_per_package_gate_is_not_rounded(ci_run_blob: str, package: str) -> None:
    """Roadmap #168: pytest-cov decides pass/fail at the report precision,
    which defaults to 0 decimals — so 94.59% rounded to 95 and passed while
    the log printed FAIL. Every gate line must carry --cov-precision=2."""
    pkg_re = re.compile(rf"--cov={re.escape(package)}(?![.\w])")
    lines = [l for l in ci_run_blob.splitlines() if pkg_re.search(l)]
    assert lines, f"No --cov={package} invocation found."
    for line in lines:
        assert "--cov-precision=2" in line, (
            f"--cov={package} gate is missing --cov-precision=2, so its "
            f"threshold is checked after rounding: {line!r}"
        )


def test_whole_app_floor_only_rises() -> None:
    """The pytest.ini floor is a ratchet (Phase S #168): measured 89.94% on
    2026-09-21, floor 89.5; raised to 90.5 at 90.61%. Raise WHOLE_APP_FLOOR when
    you raise the ini."""
    ini = (TESTS_DIR.parent / "pytest.ini").read_text()
    addopts = next(l for l in ini.splitlines() if l.startswith("addopts"))
    m = re.search(r"--cov-fail-under=(\d+(?:\.\d+)?)", addopts)
    assert m, "pytest.ini addopts lost its --cov-fail-under"
    assert float(m.group(1)) >= WHOLE_APP_FLOOR
    assert "--cov-precision=2" in addopts


def test_coveragerc_has_branch_coverage_on() -> None:
    """branch = True is what makes the JSON gate distinguish line vs branch."""
    assert COVERAGERC.exists(), f".coveragerc missing at {COVERAGERC}"
    parser = configparser.ConfigParser()
    parser.read(COVERAGERC)
    assert parser.has_section("run"), ".coveragerc missing [run] section"
    branch = parser.get("run", "branch", fallback="").strip()
    assert branch.lower() == "true", (
        f".coveragerc [run] branch must be True (got {branch!r}); "
        "Phase 31-followup + Phase 32-08 require branch coverage."
    )


@pytest.mark.parametrize(
    "glob_pattern",
    [
        "test_copilot_*.py",
        "test_retrieval_*.py",
        "test_corpus_*.py",
        "copilot/feedback/test_*.py",
    ],
)
def test_namespace_has_test_files(glob_pattern: str) -> None:
    """Each namespace must have at least one test file backing the gate."""
    matches = sorted(TESTS_DIR.glob(glob_pattern))
    assert matches, (
        f"No test files matching {glob_pattern} in {TESTS_DIR}; "
        "coverage gate would be vacuous."
    )
