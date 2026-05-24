"""Phase 35-02-E — model-parameterised adversarial re-run.

Reads ``backend/tests/copilot/adversarial/cases.yaml`` and
``cases_memory.yaml``. For each model, sets
``COPILOT_PRIMARY_MODEL=COPILOT_FALLBACK_MODEL=<model>`` via
``app.eval.models.set_model_for_replay`` and re-runs every case, then
writes one JSON file per model to ``out_dir``.

NOT invoked in CI (real network, expensive). The existing
``backend/tests/copilot/adversarial/test_adversarial.py`` is untouched
and continues to run as the single-model CI gate (plan §35-02-E
plan-vs-reality preamble #2 point 2).

The case-iteration bodies live in the pytest module as
``run_tool_case`` / ``run_memory_case`` helpers (Phase 35-02-E
refactor). ``_run_one_case`` here dispatches on the ``source`` tag
that ``_load_cases()`` attaches to every case (``"cases.yaml"`` ->
tool/agent-loop path, ``"cases_memory.yaml"`` -> memory path), runs
the helper, and translates assertion / boundary failures into a
structured ``outcome`` field. The real implementation requires DB
state (``db_session`` + ``seed_full_world`` + admin users) that the
offline harness does not set up on its own; it therefore raises
``NotImplementedError`` until invoked from a context that wires the
DB fixtures up manually. The CI-safe path monkeypatches
``_run_one_case`` to a stub and exercises only the wrapper shape.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from .models import set_model_for_replay
from .replay import _model_slug

logger = logging.getLogger(__name__)


_CASES_DIR = Path(__file__).resolve().parents[2] / (
    "tests/copilot/adversarial"
)


def _load_cases() -> list[dict[str, Any]]:
    """Load every case YAML in the adversarial test directory.

    Each case is tagged with a ``source`` field (``"cases.yaml"`` or
    ``"cases_memory.yaml"``) so ``_run_one_case`` can dispatch to the
    correct harness without re-inspecting the file structure.
    """
    cases: list[dict[str, Any]] = []
    for name in ("cases.yaml", "cases_memory.yaml"):
        p = _CASES_DIR / name
        if not p.exists():
            continue
        loaded = yaml.safe_load(p.read_text()) or []
        for c in loaded:
            tagged = dict(c)
            tagged.setdefault("source", name)
            cases.append(tagged)
    return cases


def _run_one_case(model_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Real case runner — dispatches on ``case['source']`` to either
    ``run_tool_case`` (cases.yaml / agent loop) or ``run_memory_case``
    (cases_memory.yaml / memory-shaped harness).

    Requires DB state (``db_session`` + ``seed_full_world`` + admin
    users) that the offline harness does not set up. Callers that
    want to drive this against a real OpenRouter session must build a
    SQLAlchemy session, seed the full-world fixture, create the admin
    user(s), and invoke the helpers from
    ``backend/tests/copilot/adversarial/test_adversarial.py`` directly.

    Left as ``NotImplementedError`` here so CI never accidentally
    invokes it; the wrapper tests monkeypatch this function with a
    stub (see ``test_adversarial_wrapper.py``).
    """
    raise NotImplementedError(
        "Real adversarial case runner — requires DB session, "
        "seed_full_world, and admin user fixtures. Drive "
        "run_tool_case / run_memory_case from "
        "backend/tests/copilot/adversarial/test_adversarial.py "
        "directly, or monkeypatch this function from the offline "
        "harness driver script. See backend/app/eval/adversarial.py "
        "docstring for the rationale."
    )


def run_adversarial(
    *, models: list[str], out_dir: Path,
) -> None:
    """Iterate models x cases and write one JSON file per model.

    Free-tier guard: every model id must end in ``":free"``. The
    helper raises ``ValueError`` on any other suffix to keep us from
    accidentally billing OpenRouter for an adversarial sweep.
    """
    for mid in models:
        if not mid.endswith(":free"):
            raise ValueError(
                f"refusing to run non-:free model: {mid!r} "
                "(every adversarial sweep must stay on the OpenRouter "
                "free tier; see plan §35-02 preamble)"
            )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_cases()

    for model_id in models:
        set_model_for_replay(model_id, monkeypatch=None)
        per_case: list[dict[str, Any]] = []
        for case in cases:
            try:
                result = _run_one_case(model_id, case)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "id": case.get("id"),
                    "category": case.get("category"),
                    "outcome": "error",
                    "error_class": exc.__class__.__name__,
                    "error": str(exc),
                }
            per_case.append(result)
            logger.info(
                "eval_adversarial_case model=%s case_id=%s "
                "category=%s outcome=%s",
                model_id,
                result.get("id"),
                result.get("category"),
                result.get("outcome"),
            )

        cats: dict[str, dict[str, int]] = {}
        for r in per_case:
            cat = r.get("category") or "unknown"
            slot = cats.setdefault(
                cat, {"n": 0, "pass": 0, "fail": 0, "error": 0}
            )
            slot["n"] += 1
            outcome = r.get("outcome", "error")
            slot[outcome] = slot.get(outcome, 0) + 1

        out_path = out_dir / f"{_model_slug(model_id)}.json"
        out_path.write_text(
            json.dumps(
                {
                    "model": model_id,
                    "cases": per_case,
                    "categories": cats,
                },
                indent=2,
                default=str,
            )
        )


__all__ = ["run_adversarial"]
