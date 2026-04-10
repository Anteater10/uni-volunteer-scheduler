"""Celery task for async CSV import processing.

Runs stage-1 LLM extraction then stage-2 deterministic validation.
Stores preview in csv_imports.result_payload.
"""
import statistics
from app.celery_app import celery
from app.database import SessionLocal
from app.models import CsvImportStatus
from app.config import settings
from app.services.csv_validator import validate_import
from app.services.import_schemas import ExtractedEvent
from app.services import corpus_logger, import_service


def _estimate_cost(row_count: int, model: str) -> float:
    """Estimate LLM cost for extraction.

    Rough estimate: ~500 input tokens per row + ~200 output tokens per row.
    gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output (as of 2025).
    """
    input_tokens = row_count * 500 + 2000  # rows + system prompt
    output_tokens = row_count * 200
    if "gpt-4o-mini" in model:
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    else:
        # Conservative estimate for unknown models
        cost = (input_tokens + output_tokens) * 0.01 / 1_000
    return round(cost, 4)


def _stage1_extract_stub(raw_csv: str) -> list[dict]:
    """STUB: Placeholder for stage-1 LLM extraction.

    Returns empty list. Real implementation in plan 05-07 (BLOCKED on CSV sample).
    In tests, this is monkey-patched to return test data.
    """
    # TODO(phase5-07): Replace with real instructor + OpenAI structured output call
    return []


def _stage1_extract(raw_csv: str, model: str) -> list[dict]:
    """Stage-1 LLM extraction entry point.

    Delegates to stub for now. Real implementation replaces _stage1_extract_stub.
    """
    return _stage1_extract_stub(raw_csv)


@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
)
def process_csv_import(self, import_id: str) -> None:
    """Process a CSV import: stage-1 extraction + stage-2 validation.

    Status transitions: pending -> processing -> ready | failed
    """
    db = SessionLocal()
    try:
        imp = import_service.get_import(db, import_id)
        raw_csv_bytes = imp.result_payload.get("raw_csv", "").encode("utf-8") if imp.result_payload else b""

        # Transition to processing
        import_service.update_import_status(db, import_id, CsvImportStatus.processing)

        # Estimate cost
        row_count = raw_csv_bytes.decode("utf-8", errors="replace").count("\n")
        estimated_cost = _estimate_cost(row_count, settings.openai_model)
        if estimated_cost > settings.import_cost_ceiling:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=f"Estimated cost ${estimated_cost:.2f} exceeds ceiling ${settings.import_cost_ceiling:.2f}"
            )
            return

        # Stage 1: LLM extraction (stub)
        raw_csv = raw_csv_bytes.decode("utf-8", errors="replace")
        extracted_dicts = _stage1_extract(raw_csv, settings.openai_model)

        if not extracted_dicts:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.ready,
                result_payload={"rows": [], "summary": {"to_create": 0, "to_review": 0, "conflicts": 0, "total": 0}}
            )
            return

        # Parse into ExtractedEvent objects
        extracted_events = [ExtractedEvent(**d) for d in extracted_dicts]

        # Stage 2: Deterministic validation
        preview = validate_import(extracted_events, db)

        # Store preview
        import_service.update_import_status(
            db, import_id, CsvImportStatus.ready,
            result_payload=preview.model_dump()
        )

        # Corpus logging
        confidences = [e.confidence for e in extracted_events]
        corpus_logger.log_import(
            raw_csv_bytes=raw_csv_bytes,
            normalized_json=extracted_dicts,
            model=settings.openai_model,
            confidence_distribution={
                "min": min(confidences) if confidences else 0,
                "max": max(confidences) if confidences else 0,
                "mean": statistics.mean(confidences) if confidences else 0,
                "below_threshold": sum(1 for c in confidences if c < 0.85),
            },
        )

    except Exception as e:
        try:
            import_service.update_import_status(
                db, import_id, CsvImportStatus.failed,
                error_message=str(e)
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
