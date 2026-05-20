"""Phase 32 Plan 05 — GET /api/v1/copilot/citations/{chunk_id} integration tests.

Six tests cover the click-through citation lookup endpoint:

1. Happy path — admin can GET a known chunk and receives the full quote.
2. Unknown chunk_id returns 404 with the canonical detail string.
3. Non-admin/non-organizer users (e.g. participants) are 403'd.
4. Non-UUID path segments are rejected by FastAPI parsing as 422
   (path-traversal defense — RESEARCH §V5 / §Pattern 6).
5. When ``settings.corpus_source_origin_url`` is empty (default),
   ``document_url`` is the empty string — no internal repo path leak.
6. When the origin is set, ``document_url`` is computed as
   ``f"{origin}/{source_path}"`` with no double slashes regardless of
   whether the origin has a trailing slash or the source path has a
   leading slash.

Corpus rows (ingestion_run + corpus_documents + corpus_chunks) are
seeded with the same NOT-NULL columns the Phase 31 schema requires —
see ``test_corpus_fts_migration._seed_doc_and_chunk`` for the
authoritative shape (``git_commit_sha``, ``source_globs::jsonb``,
``chunker_version`` on the run; ``embedding`` as a vector-string,
``content_sha256`` on the chunk).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text as sa_text

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


_HEX64 = "a" * 64
_SHA40 = "0" * 40
_ZERO_VEC = "[" + ",".join(["0"] * 1024) + "]"


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    # Default to empty origin so the empty-default test is the dominant
    # case; tests that need a non-empty origin set it themselves.
    monkeypatch.setattr(settings, "corpus_source_origin_url", "")


def _seed_chunk(
    db_session,
    *,
    content: str = "Volunteers help SciTrek run quarterly events.",
    source_path: str = "docs/handbook.md",
    char_start: int = 0,
    char_end: int = 42,
) -> uuid.UUID:
    """Seed one ingestion_run + corpus_document + corpus_chunk; return chunk_id."""
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    db_session.execute(
        sa_text(
            "INSERT INTO ingestion_runs (id, status, git_commit_sha, "
            "source_globs, embedding_provider, embedding_model, "
            "embedding_dim, chunker_version) "
            "VALUES (:id, 'succeeded', :sha, '[]'::jsonb, 'local-bge', "
            "'BAAI/bge-large-en-v1.5', 1024, 'v1')"
        ),
        {"id": run_id, "sha": _SHA40},
    )
    db_session.execute(
        sa_text(
            "INSERT INTO corpus_documents "
            "(id, source_path, source_kind, content_sha256, byte_size, "
            "ingestion_run_id) "
            "VALUES (:id, :p, 'markdown', :h, :b, :r)"
        ),
        {
            "id": doc_id,
            "p": source_path,
            "h": _HEX64,
            "b": len(content),
            "r": run_id,
        },
    )
    db_session.execute(
        sa_text(
            "INSERT INTO corpus_chunks "
            "(id, document_id, chunk_index, content, content_sha256, "
            "char_start, char_end, embedding, embedding_provider, "
            "embedding_model, ingestion_run_id) "
            "VALUES (:id, :d, 0, :c, :h, :cs, :ce, :v, "
            "'local-bge', 'BAAI/bge-large-en-v1.5', :r)"
        ),
        {
            "id": chunk_id,
            "d": doc_id,
            "c": content,
            "h": _HEX64,
            "cs": char_start,
            "ce": char_end,
            "v": _ZERO_VEC,
            "r": run_id,
        },
    )
    db_session.flush()
    return chunk_id


def _admin(db_session, email="cit_admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _organizer(db_session, email="cit_org@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


def _participant(db_session, email="cit_part@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.participant)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_citation_success(client, db_session):
    """200 + correct shape when admin fetches a real chunk."""
    content = "Volunteers help SciTrek run quarterly events."
    chunk_id = _seed_chunk(
        db_session,
        content=content,
        source_path="docs/handbook.md",
        char_start=0,
        char_end=len(content),
    )
    admin = _admin(db_session)
    db_session.commit()

    rc = client.get(
        f"/api/v1/copilot/citations/{chunk_id}",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text
    body = rc.json()
    assert body["source_path"] == "docs/handbook.md"
    assert body["char_start"] == 0
    assert body["char_end"] == len(content)
    assert body["content"] == content
    # Empty origin (default) → empty document_url.
    assert body["document_url"] == ""


def test_get_citation_404_for_unknown_id(client, db_session):
    """Well-formed UUID that doesn't match any chunk returns 404."""
    admin = _admin(db_session)
    db_session.commit()

    missing = uuid.uuid4()
    rc = client.get(
        f"/api/v1/copilot/citations/{missing}",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 404
    assert rc.json() == {"detail": "Citation not found"}


def test_get_citation_403_unauthorized(client, db_session):
    """Participants (non-admin, non-organizer) are 403'd."""
    chunk_id = _seed_chunk(db_session)
    part = _participant(db_session)
    db_session.commit()

    rc = client.get(
        f"/api/v1/copilot/citations/{chunk_id}",
        headers=auth_headers(client, part),
    )
    assert rc.status_code == 403


def test_get_citation_422_on_invalid_uuid(client, db_session):
    """Path-traversal-style inputs are rejected at the parse layer."""
    admin = _admin(db_session)
    db_session.commit()

    # Not a UUID. FastAPI's UUID converter rejects this before our
    # handler runs — RESEARCH §V5 (Pattern 6).
    rc = client.get(
        "/api/v1/copilot/citations/not-a-uuid",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 422


def test_document_url_empty_when_origin_unset(client, db_session, monkeypatch):
    """No origin → no leak: document_url is the empty string."""
    monkeypatch.setattr(settings, "corpus_source_origin_url", "")
    chunk_id = _seed_chunk(db_session, source_path="docs/handbook.md")
    organizer = _organizer(db_session)
    db_session.commit()

    rc = client.get(
        f"/api/v1/copilot/citations/{chunk_id}",
        headers=auth_headers(client, organizer),
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["document_url"] == ""


def test_document_url_computed_when_origin_set(client, db_session, monkeypatch):
    """Origin set → document_url = origin/source_path with no double slashes."""
    # Trailing slash on origin AND leading slash on source_path stress
    # both .rstrip("/") and .lstrip("/") normalisation paths.
    monkeypatch.setattr(
        settings,
        "corpus_source_origin_url",
        "https://github.com/Anteater10/uni-volunteer-scheduler/blob/main/",
    )
    chunk_id = _seed_chunk(db_session, source_path="/docs/handbook.md")
    admin = _admin(db_session)
    db_session.commit()

    rc = client.get(
        f"/api/v1/copilot/citations/{chunk_id}",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text
    url = rc.json()["document_url"]
    assert url == (
        "https://github.com/Anteater10/uni-volunteer-scheduler/blob/main"
        "/docs/handbook.md"
    )
    assert "//docs" not in url  # no double-slash regression
