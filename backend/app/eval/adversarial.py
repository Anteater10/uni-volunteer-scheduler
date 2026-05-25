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
refactor), and the world-seeding logic lives in
``tests/copilot/adversarial/seed.py``. ``_run_one_case`` here
dispatches on the ``source`` tag that ``_load_cases()`` attaches to
every case (``"cases.yaml"`` -> tool/agent-loop path,
``"cases_memory.yaml"`` -> memory path). It replicates the pytest
fixture setup programmatically — opens an isolated SQLAlchemy session
(same join-external-transaction pattern as the ``db_session``
fixture), registers every production tool, seeds the full-world
fixture / creates the admin user(s), runs the helper, and translates
pass / assertion-failure / error into a structured ``outcome`` field.
Each case rolls its transaction back so it never contaminates the
next. The CI-safe wrapper test monkeypatches ``_run_one_case`` to a
stub and exercises only the wrapper shape; a separate test drives the
real ``_run_one_case`` against a stubbed LLM (no real network).
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


def _open_isolated_session():
    """Open a SQLAlchemy session bound to its own outer transaction.

    Mirrors ``backend/conftest.py::db_session`` (join-external-transaction +
    create_savepoint) so router/tool code that calls ``db.commit()`` does not
    escape the rollback. Returns ``(session, connection, trans)`` — the caller
    rolls back ``trans`` and closes ``connection`` to discard the case's writes
    so cases never contaminate each other.
    """
    from sqlalchemy.orm import sessionmaker

    from app.database import engine

    connection = engine.connect()
    trans = connection.begin()
    Session = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
        future=True,
    )
    return Session(), connection, trans


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

    Replicates the pytest fixture setup programmatically: opens an isolated
    SQLAlchemy session (same join-external-transaction pattern as the
    ``db_session`` fixture), registers every production tool, seeds the
    full-world fixture, creates the admin user(s), runs the helper, and
    translates pass -> ``{"outcome": "pass"}`` / assertion failure ->
    ``{"outcome": "fail", ...}``. The transaction is always rolled back so
    one case never contaminates the next.

    The shared bodies live in the pytest module
    (``run_tool_case`` / ``run_memory_case``) and the seeding logic lives in
    ``tests/copilot/adversarial/seed.py`` — both imported here so the offline
    path and the CI path exercise identical code.
    """
    # Imports are local so importing this module never drags the test tree in
    # (it only matters when the offline driver actually runs a case).
    from tests.copilot.adversarial import seed as _seed
    from tests.copilot.adversarial.test_adversarial import (
        _assert_pass,
        run_memory_case,
        run_tool_case,
    )

    source = case.get("source", "cases.yaml")
    session, connection, trans = _open_isolated_session()
    base = {"id": case.get("id"), "category": case.get("category")}
    try:
        _seed.register_all_tools()
        if source == "cases_memory.yaml":
            admin_user = _seed.make_admin_user(session)
            other_admin_user = _seed.make_admin_user(session)
            session.flush()
            run_memory_case(
                case,
                session,
                admin_user,
                other_admin_user=other_admin_user,
            )
        else:
            world = _seed.seed_full_world(session)
            session.flush()
            events, sentinels, case_r = run_tool_case(case, session, world)
            _assert_pass(events, case_r, sentinels)
    except AssertionError as exc:
        return {
            **base,
            "outcome": "fail",
            "error_class": exc.__class__.__name__,
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "outcome": "error",
            "error_class": exc.__class__.__name__,
            "error": str(exc),
        }
    else:
        return {**base, "outcome": "pass"}
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()
        from app.copilot.agent import confirmation
        from app.copilot.agent.tools import registry

        registry._reset_for_tests()
        confirmation._reset_for_tests()


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
