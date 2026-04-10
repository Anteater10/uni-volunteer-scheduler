"""Corpus logger for CSV import pipeline.

Appends raw->normalized pairs to a JSONL file for future eval.
Files are gitignored; raw CSVs contain event data only (no PII).
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CORPUS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "corpus"
CORPUS_FILE = CORPUS_DIR / "csv_imports.jsonl"


def _ensure_dir() -> None:
    """Ensure the corpus directory exists."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)


def compute_csv_hash(raw_csv_bytes: bytes) -> str:
    """SHA-256 hash of raw CSV bytes."""
    return hashlib.sha256(raw_csv_bytes).hexdigest()


def log_import(
    raw_csv_bytes: bytes,
    normalized_json: list[dict[str, Any]],
    model: str,
    confidence_distribution: dict[str, Any],
) -> None:
    """Append a raw->normalized import pair to the corpus JSONL file.

    Args:
        raw_csv_bytes: Original CSV file bytes (verbatim).
        normalized_json: Stage-1 LLM output as list of dicts.
        model: LLM model used (e.g., "gpt-4o-mini").
        confidence_distribution: Stats like {min, max, mean, median, below_threshold}.
    """
    _ensure_dir()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_csv_hash": compute_csv_hash(raw_csv_bytes),
        "raw_csv_bytes": raw_csv_bytes.decode("utf-8", errors="replace"),
        "normalized_json": normalized_json,
        "model": model,
        "confidence_distribution": confidence_distribution,
    }

    with open(CORPUS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
