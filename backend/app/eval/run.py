"""Phase 35-02-C — CLI entrypoint for ``python -m app.eval.run``.

Usage:
    python -m app.eval.run --models all --testset default
    python -m app.eval.run --models meta-llama/llama-3.3-70b-instruct:free \\
                           --testset backend/app/eval/testset.yaml

Per-model parallelism: ``ThreadPoolExecutor(max_workers=4)``. Models are
executed sequentially (one model at a time) because OpenRouter's free-tier
rate limit is per-model AND IP-wide, and running 8 models concurrently
risks the IP cap (spec §5).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .models import (
    CANDIDATE_MODELS,
    assert_free_tier,
    set_model_for_replay,
)
from .replay import _model_slug, replay_grounded, replay_one

logger = logging.getLogger(__name__)

# A trace with one of these outcomes is a real result and is skipped on
# resume. Anything else (notably ``hard_failure`` from a rate-limit 429)
# is re-attempted so a chunked, day-by-day free-tier run can make progress.
_DONE_OUTCOMES = frozenset({"ok", "empty_response"})


def _make_session():
    """Open a DB session for the grounded path.

    Lazy import so the bare/offline path (and its unit tests) never need a
    configured database. Monkeypatched in CLI tests. The grounded run must
    execute where ``SessionLocal`` can reach the ingested corpus — i.e.
    inside the docker network (``docker exec ... python -m app.eval.run``).
    """
    from app.database import SessionLocal

    return SessionLocal()


def _load_testset(path: str) -> list[dict[str, Any]]:
    if path in {"", "ignored", "default"}:
        raw = (files("app.eval") / "testset.yaml").read_text()
    else:
        raw = Path(path).read_text()
    return (yaml.safe_load(raw) or {}).get("questions", []) or []


def _already_done(out_dir: Path, model_id: str, question_id: str) -> bool:
    """True if a successful trace for this (model, question) already exists.

    Lets a free-tier run resume: re-running the same command with the same
    ``--out-dir`` skips questions that already succeeded and re-attempts the
    ones a 429 turned into ``hard_failure``.
    """
    trace_path = Path(out_dir) / _model_slug(model_id) / f"q-{question_id}.json"
    if not trace_path.exists():
        return False
    try:
        data = json.loads(trace_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return data.get("outcome") in _DONE_OUTCOMES


def _resolve_models(arg: str) -> list[str]:
    if arg == "all":
        return list(CANDIDATE_MODELS)
    return [m.strip() for m in arg.split(",") if m.strip()]


def _run_model(
    *,
    model_id: str,
    questions: list[dict[str, Any]],
    out_dir: Path,
    max_workers: int,
    use_agent_loop: bool = False,
    grounded: bool = False,
    resume: bool = True,
) -> None:
    set_model_for_replay(model_id, monkeypatch=None)
    pending = questions
    if resume:
        pending = [
            q for q in questions
            if not _already_done(out_dir, model_id, q["id"])
        ]
        skipped = len(questions) - len(pending)
        if skipped:
            logger.info("eval_model_resume model=%s skipped_done=%s remaining=%s",
                        model_id, skipped, len(pending))
    logger.info("eval_model_started model=%s n_questions=%s grounded=%s "
                "use_agent_loop=%s",
                model_id, len(pending), grounded, use_agent_loop)
    if not pending:
        logger.info("eval_model_finished model=%s (nothing to do)", model_id)
        return

    def _grounded_task(q):
        # One session per question — SQLAlchemy sessions are not thread-safe,
        # so the ThreadPoolExecutor workers must not share one.
        db = _make_session()
        try:
            return replay_grounded(
                model_id=model_id, question=q, db=db, out_dir=out_dir,
                monkeypatch=None,
            )
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        if grounded:
            futures = [pool.submit(_grounded_task, q) for q in pending]
        else:
            futures = [
                pool.submit(
                    replay_one,
                    model_id=model_id,
                    question=q,
                    out_dir=out_dir,
                    monkeypatch=None,
                    use_agent_loop=use_agent_loop,
                )
                for q in pending
            ]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("eval_replay_uncaught model=%s err=%s",
                                 model_id, exc)
    logger.info("eval_model_finished model=%s", model_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval.run")
    parser.add_argument("--models", required=True,
                        help="Comma-separated model IDs, or 'all'.")
    parser.add_argument("--testset", required=True,
                        help="Path to testset.yaml, or 'default' for the "
                             "in-package testset.")
    parser.add_argument(
        "--out-dir", default=None,
        help="Output directory. Defaults to "
             "backend/eval-results/{timestamp}/.",
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Re-run every question even if a successful trace already "
             "exists. Default is to resume: skip questions that already "
             "succeeded and re-attempt 429-failed ones. Use a fixed "
             "--out-dir across days to chunk a free-tier run.",
    )
    parser.add_argument(
        "--use-agent-loop",
        action="store_true",
        default=False,
        help="Drive replays through app.copilot.agent.loop.run_turn instead "
             "of the bare complete() path. Requires a structured "
             "tool-calling LLM adapter that is NOT yet built (Phase 35-04).",
    )
    parser.add_argument(
        "--grounded",
        action="store_true",
        default=False,
        help="Drive replays through the deployed retrieval-grounded path "
             "(Phase 32 retrieve -> <retrieved_context> -> complete). "
             "Populates retrieved_context so RAGAS faithfulness / "
             "context_precision are valid. Needs a DB reaching the ingested "
             "corpus — run inside the docker network.",
    )
    args = parser.parse_args(argv)

    # Free-tier guard for the candidate set (spec §2.7 / §13).
    assert_free_tier()
    models = _resolve_models(args.models)
    for mid in models:
        if not mid.endswith(":free"):
            raise ValueError(
                f"refusing to run with non-:free model: {mid!r}"
            )

    questions = _load_testset(args.testset)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        ts = os.environ.get(
            "EVAL_RUN_TIMESTAMP",
            _dt.datetime.now(_dt.timezone.utc)
                .strftime("%Y-%m-%dT%H-%M-%SZ"),
        )
        out_dir = Path("backend") / "eval-results" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Models run sequentially; questions parallelise within a model.
    for model_id in models:
        _run_model(
            model_id=model_id,
            questions=questions,
            out_dir=out_dir,
            max_workers=args.max_workers,
            use_agent_loop=args.use_agent_loop,
            grounded=args.grounded,
            resume=args.resume,
        )
    logger.info("eval_run_finished out_dir=%s", out_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
