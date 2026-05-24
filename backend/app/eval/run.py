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
from .replay import replay_one

logger = logging.getLogger(__name__)


def _load_testset(path: str) -> list[dict[str, Any]]:
    if path in {"", "ignored", "default"}:
        raw = (files("app.eval") / "testset.yaml").read_text()
    else:
        raw = Path(path).read_text()
    return (yaml.safe_load(raw) or {}).get("questions", []) or []


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
) -> None:
    set_model_for_replay(model_id, monkeypatch=None)
    logger.info("eval_model_started model=%s n_questions=%s use_agent_loop=%s",
                model_id, len(questions), use_agent_loop)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                replay_one,
                model_id=model_id,
                question=q,
                out_dir=out_dir,
                monkeypatch=None,
                use_agent_loop=use_agent_loop,
            )
            for q in questions
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
        "--use-agent-loop",
        action="store_true",
        default=False,
        help="Drive replays through app.copilot.agent.loop.run_turn instead "
             "of the bare complete() path. Requires DB / scope wiring — "
             "still a work-in-progress (see SUMMARY).",
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
        )
    logger.info("eval_run_finished out_dir=%s", out_dir)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
