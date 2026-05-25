"""Phase 35-02 — CLI entrypoint for ``python -m app.eval.score``.

The replay step (``python -m app.eval.run``) produces per-question JSON
traces under ``--out-dir``. This command is the *second half*: it scores
those traces (RAGAS + tool-use), optionally joins human ratings, optionally
runs the adversarial sweep, and emits the paper deliverables
(``results.csv`` + ``traces.json`` + ``report.md``).

This file orchestrates existing library functions ONLY — no new metric
logic, no new report formats:

* :func:`app.eval.metrics.score_all_traces` — mutates each trace JSON
  in-place, attaching ``ragas`` (only when a ``judge`` is supplied) and
  ``tool_use_grade`` (always — ``grade_trace`` is offline).
* :func:`app.eval.metrics.ragas._default_judge` — the real RAGAS judge
  (hits OpenRouter; needs ``OPENROUTER_API_KEY`` + ``ragas`` installed).
* :func:`app.eval.metrics.human.per_model_rollup` — per-model human-rating
  rollup (needs a DB session).
* :func:`app.eval.adversarial.run_adversarial` — per-model adversarial JSON
  (heavy: real network + DB seeding).
* :mod:`app.eval.reports` — ``write_results_csv`` / ``write_traces_json`` /
  ``render_markdown``.

Usage:
    # Fast: tool-use grading + CSV + report, NO RAGAS network cost.
    python -m app.eval.score --out-dir backend/eval-results/RUN --testset default --no-ragas

    # Full: real RAGAS judge (OpenRouter). See module note on env vars.
    OPENROUTER_API_KEY=sk-... \\
    python -m app.eval.score --out-dir backend/eval-results/RUN --testset default

The real RAGAS judge (``ragas._default_judge``) reads ``OPENAI_API_KEY``
and ``OPENAI_BASE_URL``; it falls back to ``OPENROUTER_API_KEY`` for the key
and defaults the base URL to ``https://openrouter.ai/api/v1`` if unset.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .metrics import score_all_traces
from .metrics.ragas import _default_judge
from .models import CANDIDATE_MODELS
from .reports import render_markdown, write_results_csv, write_traces_json
from .run import _load_testset, _resolve_models

logger = logging.getLogger(__name__)


def _collect_traces(out_dir: Path) -> list[dict[str, Any]]:
    """Load every per-question trace under ``out_dir`` (rglob ``q-*.json``).

    Adversarial output lives under ``out_dir/adversarial`` and is named per
    model (``<slug>.json``), so it is never picked up by the ``q-*`` glob.
    Unreadable files are skipped so a half-written trace can't abort scoring.
    """
    traces: list[dict[str, Any]] = []
    for trace_path in sorted(Path(out_dir).rglob("q-*.json")):
        try:
            traces.append(json.loads(trace_path.read_text()))
        except (json.JSONDecodeError, OSError):
            logger.warning("score_skip_unreadable_trace path=%s", trace_path)
            continue
    return traces


def _load_adversarial(adv_dir: Path) -> list[dict[str, Any]]:
    """Load the per-model adversarial JSON files written by run_adversarial."""
    out: list[dict[str, Any]] = []
    if not adv_dir.exists():
        return out
    for adv_path in sorted(adv_dir.glob("*.json")):
        try:
            out.append(json.loads(adv_path.read_text()))
        except (json.JSONDecodeError, OSError):
            logger.warning("score_skip_unreadable_adversarial path=%s", adv_path)
            continue
    return out


def _compute_human() -> list[dict[str, Any]]:
    """Open a real DB session and roll up human ratings per model.

    Imported lazily so the default (no ``--with-human``) path never touches
    the database or imports SQLAlchemy session machinery.
    """
    from app.database import SessionLocal

    from .metrics.human import per_model_rollup

    db = SessionLocal()
    try:
        return per_model_rollup(db)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval.score")
    parser.add_argument(
        "--out-dir", required=True,
        help="Directory of replay traces (the --out-dir you passed to "
             "python -m app.eval.run). Deliverables are written here.",
    )
    parser.add_argument(
        "--testset", required=True,
        help="Path to testset.yaml, or 'default' for the in-package testset. "
             "Must match the testset used for the replay.",
    )
    parser.add_argument(
        "--no-ragas",
        dest="ragas",
        action="store_false",
        default=True,
        help="Skip RAGAS scoring (no OpenRouter network). Tool-use grading "
             "still runs (it is offline). Produces CSV + report without "
             "paying the RAGAS network cost.",
    )
    parser.add_argument(
        "--with-human",
        action="store_true",
        default=False,
        help="Join human ratings from the 35-01 feedback tables (opens a DB "
             "session). Default off: a fresh local run has no ratings yet.",
    )
    parser.add_argument(
        "--adversarial",
        action="store_true",
        default=False,
        help="Also run the adversarial sweep (HEAVY: real network + DB "
             "seeding) and fold its per-model results into the report. "
             "Default off.",
    )
    parser.add_argument(
        "--models", default="all",
        help="Comma-separated model IDs, or 'all'. Only used by the "
             "--adversarial path.",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    questions = _load_testset(args.testset)

    judge = _default_judge if args.ragas else None
    logger.info(
        "score_started out_dir=%s ragas=%s with_human=%s adversarial=%s",
        out_dir, bool(args.ragas), args.with_human, args.adversarial,
    )

    # 1. RAGAS (optional) + tool-use (always) — mutates traces in place.
    score_all_traces(out_dir=out_dir, questions=questions, judge=judge)

    # 2. Adversarial sweep (optional, heavy).
    adversarial: list[dict[str, Any]] = []
    if args.adversarial:
        from .adversarial import run_adversarial

        adv_dir = out_dir / "adversarial"
        models = _resolve_models(args.models)
        run_adversarial(models=models, out_dir=adv_dir)
        adversarial = _load_adversarial(adv_dir)

    # 3. Human-rating rollup (optional, needs DB).
    human: list[dict[str, Any]] = []
    if args.with_human:
        human = _compute_human()

    # 4. Collect scored traces and emit deliverables.
    traces = _collect_traces(out_dir)
    csv_path = out_dir / "results.csv"
    traces_path = out_dir / "traces.json"
    report_path = out_dir / "report.md"
    write_results_csv(traces=traces, out_path=csv_path)
    write_traces_json(traces=traces, out_path=traces_path)
    render_markdown(
        traces=traces,
        adversarial=adversarial,
        human=human,
        out_path=report_path,
    )

    n_models = len({t.get("model") for t in traces if t.get("model")})
    logger.info(
        "score_finished n_traces=%s n_models=%s csv=%s traces=%s report=%s",
        len(traces), n_models, csv_path, traces_path, report_path,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
