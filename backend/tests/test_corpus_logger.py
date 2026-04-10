"""Unit tests for corpus logger."""
import json
from unittest.mock import patch

from app.services.corpus_logger import log_import, compute_csv_hash


def test_compute_csv_hash():
    data = b"col1,col2\nval1,val2"
    h = compute_csv_hash(data)
    assert len(h) == 64  # SHA-256 hex digest
    assert h == compute_csv_hash(data)  # deterministic


def test_log_import_appends_jsonl(tmp_path):
    corpus_file = tmp_path / "csv_imports.jsonl"
    with patch("app.services.corpus_logger.CORPUS_FILE", corpus_file):
        with patch("app.services.corpus_logger.CORPUS_DIR", tmp_path):
            log_import(
                raw_csv_bytes=b"date,module\n2026-01-01,orientation",
                normalized_json=[{"module_slug": "orientation"}],
                model="gpt-4o-mini",
                confidence_distribution={"min": 0.9, "max": 0.99, "mean": 0.95},
            )
    assert corpus_file.exists()
    lines = corpus_file.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["model"] == "gpt-4o-mini"
    assert "raw_csv_hash" in entry
    assert "normalized_json" in entry
    assert entry["normalized_json"] == [{"module_slug": "orientation"}]


def test_log_import_appends_multiple(tmp_path):
    corpus_file = tmp_path / "csv_imports.jsonl"
    with patch("app.services.corpus_logger.CORPUS_FILE", corpus_file):
        with patch("app.services.corpus_logger.CORPUS_DIR", tmp_path):
            for i in range(3):
                log_import(
                    raw_csv_bytes=f"row{i}".encode(),
                    normalized_json=[],
                    model="gpt-4o-mini",
                    confidence_distribution={},
                )
    lines = corpus_file.read_text().strip().split("\n")
    assert len(lines) == 3
