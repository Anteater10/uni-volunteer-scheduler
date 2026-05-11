"""Wave 0 stub - REQ-31-08. Implementation lands in plan 04."""
import pytest


@pytest.mark.xfail(strict=True, reason="REQ-31-08 idempotency lands in plan 04")
def test_ingest_idempotent_on_unchanged_repo(tiny_markdown_corpus, fake_embedding_provider, db_session):
    from app.corpus.ingest import run_ingestion
    r1 = run_ingestion(root=tiny_markdown_corpus, provider=fake_embedding_provider, session=db_session)
    r2 = run_ingestion(root=tiny_markdown_corpus, provider=fake_embedding_provider, session=db_session)
    assert r1.files_ingested > 0
    assert r2.files_ingested == 0
    assert r2.files_unchanged == r1.files_scanned
