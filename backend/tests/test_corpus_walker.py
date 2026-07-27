"""Phase 31 plan 03 — allow-list source walker tests.

REQ-31-05 (no DB cursor), REQ-31-06 (deny-list), REQ-31-07 (deterministic
ordering) plus two boundary tests added in plan 03 (python docstring-only
extraction, LF/CRLF normalization).
"""

import hashlib

from app.corpus.walker import walk_sources

# The shipped SOURCE_GLOBS_V1 is markdown-only (the corpus is the curated
# knowledge base, not the codebase), so the code-derived emitters are only
# reachable by passing globs explicitly. These are the globs the walker used to
# ship with; the emitters stay covered in case a code-aware corpus is ever
# wanted again.
CODE_GLOBS = [
    "docs/*.md",
    "backend/alembic/versions/*.py",
    "backend/app/**/*.py",
    "frontend/src/**/*.jsx",
    "frontend/src/**/*.js",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
]


def test_shipped_globs_ingest_only_curated_markdown():
    """Guard: the corpus is the curated knowledge base, not the codebase.

    Ingesting code and planning docs as "knowledge" is what made the copilot
    answer admin/organizer questions out of developer docstrings and stale phase
    plans. Retrieval fusion has no notion of an authoritative source, so the
    knowledge base wins by being the only domain voice in the corpus. If this
    test fails because a source was added back, add source weighting to the
    fusion SQL first — see the note on SOURCE_GLOBS_V1.
    """
    from app.corpus.walker import SOURCE_GLOBS_V1

    assert all(g.endswith(".md") for g in SOURCE_GLOBS_V1), SOURCE_GLOBS_V1
    assert "docs/knowledge-base/**/*.md" in SOURCE_GLOBS_V1
    # No code, no planning docs, no dev journals, no repo-root markdown.
    for pattern in (
        "backend/app/**/*.py",
        "backend/alembic/versions/*.py",
        ".planning/phases/**/*.md",
        ".planning/ROADMAP.md",
        "docs/copilot-journal/**/*.md",
        "docs/learning/**/*.md",
        "*.md",
    ):
        assert pattern not in SOURCE_GLOBS_V1


def test_walker_deterministic_order(tiny_markdown_corpus):
    a = list(walk_sources(root=tiny_markdown_corpus))
    b = list(walk_sources(root=tiny_markdown_corpus))
    assert [d.source_path for d in a] == [d.source_path for d in b]


def test_walker_respects_deny_list(tiny_markdown_corpus):
    paths = [d.source_path for d in walk_sources(root=tiny_markdown_corpus)]
    assert not any("node_modules" in p for p in paths)
    assert not any("test_" in p.rsplit("/", 1)[-1] for p in paths)


def test_walker_opens_no_db_connection(tiny_markdown_corpus, monkeypatch):
    # Patch SQLAlchemy engine creation to raise — walker must not need it.
    from app import database

    def boom(*a, **kw):
        raise AssertionError("walker opened a DB connection")

    monkeypatch.setattr(database, "engine", None)
    monkeypatch.setattr(database, "SessionLocal", boom)
    list(walk_sources(root=tiny_markdown_corpus))  # must complete without touching DB


def test_walker_extracts_python_docstrings_not_bodies(tmp_path):
    # Comprehensive fixture covering every source kind the walker emits,
    # plus edge cases (no-H1 markdown, no-docstring python, broken-python,
    # JSDoc + // leading comments on frontend files, alembic revision).

    # 1. Python module with module-, function-, async-function-, and class-
    #    level docstrings. Bodies must NOT appear in any emitted document.
    pkg = tmp_path / "backend" / "app"
    pkg.mkdir(parents=True)
    (pkg / "foo.py").write_text(
        '"""Module docstring for foo."""\n'
        "\n"
        "SECRET_BODY_TOKEN = 'do-not-ingest'\n"
        "\n"
        "def bar():\n"
        '    """Bar function docstring."""\n'
        "    SECRET_BODY_TOKEN_IN_FN = 'also-do-not-ingest'\n"
        "    return 42\n"
        "\n"
        "async def baz():\n"
        '    """Baz async docstring."""\n'
        "    return 0\n"
        "\n"
        "class Quux:\n"
        '    """Quux class docstring."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    # 2. Python file with NO docstrings — should emit zero documents.
    (pkg / "no_doc.py").write_text("x = 1\n", encoding="utf-8")
    # 3. Broken python — must NOT crash the walker, just skip.
    (pkg / "broken.py").write_text("def (((: not valid\n", encoding="utf-8")

    # 4. Alembic migration with module docstring + revision string.
    alembic = tmp_path / "backend" / "alembic" / "versions"
    alembic.mkdir(parents=True)
    (alembic / "0001_init.py").write_text(
        '"""Initial migration."""\n'
        "\n"
        "revision = '0001_init'\n"
        "down_revision = None\n",
        encoding="utf-8",
    )
    # Alembic file with no docstring — must emit nothing.
    (alembic / "0002_empty.py").write_text("revision = '0002'\n", encoding="utf-8")
    # Alembic with broken syntax — must not crash.
    (alembic / "0003_broken.py").write_text("def (((\n", encoding="utf-8")

    # 5. Frontend files: JSDoc block, // line block, and a file with no
    #    leading comment (should be skipped).
    fe = tmp_path / "frontend" / "src"
    fe.mkdir(parents=True)
    (fe / "WithJSDoc.jsx").write_text(
        "/**\n * Header comment.\n * Multi-line.\n */\n"
        "export default function X() { return null; }\n",
        encoding="utf-8",
    )
    (fe / "WithLineComments.ts").write_text(
        "\n\n// first line comment\n// second line comment\n\n"
        "export const x = 1;\n",
        encoding="utf-8",
    )
    (fe / "NoComment.js").write_text("export const y = 2;\n", encoding="utf-8")
    # Block-comment that never closes — defensive: walker must not crash.
    (fe / "Unterminated.tsx").write_text("/* never closes\n", encoding="utf-8")

    # 6. Markdown without an H1 (exercises the _first_h1 None branch).
    md_dir = tmp_path / "docs"
    md_dir.mkdir()
    (md_dir / "noheading.md").write_text("just a paragraph\n", encoding="utf-8")

    # 7. A path that does NOT match any allow-list pattern (exercises the
    #    "skip non-allow-listed file" branch).
    (tmp_path / "random.txt").write_text("ignored\n", encoding="utf-8")

    docs = walk_sources(root=tmp_path, globs=CODE_GLOBS)
    by_kind: dict[str, list] = {}
    for d in docs:
        by_kind.setdefault(d.source_kind, []).append(d)

    # Python module + 3 python_functions (bar, baz, Quux), 1 alembic, 2 frontend, 1 markdown.
    assert {d.title for d in by_kind["python_function"]} == {"bar", "baz", "Quux"}
    assert by_kind["python_module"][0].content == "Module docstring for foo."
    assert by_kind["alembic_migration"][0].title == "0001_init"
    assert by_kind["alembic_migration"][0].content == "Initial migration."
    assert len(by_kind["frontend_component"]) == 2
    assert any("Header comment." in d.content for d in by_kind["frontend_component"])
    assert any("first line comment" in d.content for d in by_kind["frontend_component"])
    # No body tokens leak into ingested content.
    for d in docs:
        assert "SECRET_BODY_TOKEN" not in d.content
    # No-H1 markdown emits with title=None.
    md = next(d for d in by_kind["markdown"] if d.source_path == "docs/noheading.md")
    assert md.title is None
    # Random non-allow-listed file does not appear.
    assert "random.txt" not in {d.source_path for d in docs}


def test_walker_lf_normalizes_line_endings(tmp_path):
    # Two markdown files with identical logical content but different EOLs.
    docs_dir = tmp_path / "docs" / "knowledge-base"
    docs_dir.mkdir(parents=True)
    lf = "# Title\n\nLine one.\nLine two.\n"
    crlf = lf.replace("\n", "\r\n")
    (docs_dir / "lf.md").write_bytes(lf.encode("utf-8"))
    (docs_dir / "crlf.md").write_bytes(crlf.encode("utf-8"))
    docs = {d.source_path: d for d in walk_sources(root=tmp_path)}
    a = docs["docs/knowledge-base/lf.md"]
    b = docs["docs/knowledge-base/crlf.md"]
    assert a.byte_size == b.byte_size
    assert (
        hashlib.sha256(a.content.encode("utf-8")).hexdigest()
        == hashlib.sha256(b.content.encode("utf-8")).hexdigest()
    )


def test_walker_extracts_line_comments_with_leading_blanks(tmp_path):
    """Frontend file with blank lines before and inside a `//` comment block.

    Covers the leading-blank `continue` branch in `_extract_leading_comment`
    plus the "blank line inside comment block" append path that previous
    fixtures skipped over.
    """
    from app.corpus.walker import walk_sources

    fe = tmp_path / "frontend" / "src"
    fe.mkdir(parents=True)
    contents = (
        "\n"
        "\n"
        "// Component header.\n"
        "\n"
        "// More details about it.\n"
        "export const x = 1;\n"
    )
    (fe / "Thing.tsx").write_text(contents, encoding="utf-8")
    docs = walk_sources(root=tmp_path, globs=CODE_GLOBS)
    fe_docs = [d for d in docs if d.source_kind == "frontend_component"]
    assert fe_docs and "Component header." in fe_docs[0].content
    assert "More details about it." in fe_docs[0].content
