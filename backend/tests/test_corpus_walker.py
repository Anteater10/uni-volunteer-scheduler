"""Wave 0 stubs - REQ-31-05/06/07. Implementation lands in plan 03."""
import pytest


@pytest.mark.xfail(strict=True, reason="REQ-31-07 deterministic order lands in plan 03")
def test_walker_deterministic_order(tiny_markdown_corpus):
    from app.corpus.walker import walk_sources
    a = list(walk_sources(root=tiny_markdown_corpus))
    b = list(walk_sources(root=tiny_markdown_corpus))
    assert [d.source_path for d in a] == [d.source_path for d in b]


@pytest.mark.xfail(strict=True, reason="REQ-31-06 deny-list lands in plan 03")
def test_walker_respects_deny_list(tiny_markdown_corpus):
    from app.corpus.walker import walk_sources
    paths = [d.source_path for d in walk_sources(root=tiny_markdown_corpus)]
    assert not any("node_modules" in p for p in paths)
    assert not any("test_" in p.rsplit("/", 1)[-1] for p in paths)


@pytest.mark.xfail(strict=True, reason="REQ-31-05 no-DB-cursor lands in plan 03")
def test_walker_opens_no_db_connection(tiny_markdown_corpus, monkeypatch):
    # Patch SQLAlchemy engine creation to raise - walker must not need it.
    from app import database

    def boom(*a, **kw):
        raise AssertionError("walker opened a DB connection")

    monkeypatch.setattr(database, "engine", None)
    monkeypatch.setattr(database, "SessionLocal", boom)
    from app.corpus.walker import walk_sources
    list(walk_sources(root=tiny_markdown_corpus))  # must complete without touching DB
