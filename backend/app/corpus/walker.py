"""Allow-list source walker for the Phase 31 corpus pipeline.

Reads bytes from disk. Opens **zero** database connections, reads **zero**
JSON/CSV. The walker is path-restricted by :data:`SOURCE_GLOBS_V1` and
:data:`DENY_LIST` so PII fixtures cannot enter the pipeline by construction.

Public surface:
    walk_sources(*, root: Path) -> list[SourceDocument]
    SourceDocument(source_path, source_kind, title, content, byte_size)
    SOURCE_GLOBS_V1, DENY_LIST

Source kinds emitted:
    * ``markdown`` — one document per ``*.md`` file. Title = first H1. This is
      the only kind ``SOURCE_GLOBS_V1`` can currently produce.

The code-derived emitters below (``alembic_migration``, ``python_module``,
``python_function``, ``frontend_component``) are retained and tested but are
unreachable through the current globs — ingesting code as "knowledge" is what
made the copilot answer domain questions out of developer docstrings. They stay
so the capability is one glob away if a code-aware assistant is ever wanted,
but read the note on ``SOURCE_GLOBS_V1`` before re-enabling one.

Determinism:
    * Output is sorted lexicographically by ``source_path``.
    * File bytes are CRLF-normalized to LF and per-line trailing whitespace
      stripped before hashing / counting bytes.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# The corpus is a CURATED knowledge base, not the codebase.
#
# It used to be the codebase: Python/JS docstrings, alembic migration
# docstrings, .planning/phases/** plans, docs/learning/ + docs/copilot-journal/
# dev notes, ROADMAP.md, README.md, CLAUDE.md. Retrieval and rerank were fine;
# the *content* was the problem. Those are engineering and project-management
# artifacts written for developers, so domain questions from admins and
# organizers ("what is an event") were answered out of the wrong audience's
# documents — including stale planning docs describing behavior that had since
# been replaced.
#
# Fusion in ``retrieval/hybrid.py`` scores chunks purely on text similarity;
# there is no notion of an authoritative source. So precedence is achieved by
# *composition*: the knowledge base is the only thing in here that speaks about
# the domain, which means nothing competes with it. Adding a wrong-audience
# source back would silently re-create the original bug — if you need one, add
# source weighting to the fusion SQL first.
#
# The two ops documents are kept deliberately: they answer deployment and
# restore questions (Rafael's handoff) and overlap with nothing in the
# knowledge base. The CCPA policy is kept because admins action CCPA requests
# and the knowledge base only describes the buttons, not the policy.
SOURCE_GLOBS_V1: list[str] = [
    "docs/knowledge-base/**/*.md",  # primary + authoritative (see its README)
    "docs/deployment.md",
    "docs/demo-runbook.md",
    "docs/ccpa-policy.md",
]

DENY_LIST: list[str] = [
    "**/__pycache__/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/.venv/**",
    "**/.git/**",
    "**/.pytest_cache/**",
    "**/.claude/**",
    "**/test_*.py",
    "**/*.test.*",
    "**/__tests__/**",
    "backend/.env*",
    "frontend/.env*",
    ".planning/notes/private-*",
]


@dataclass(frozen=True)
class SourceDocument:
    """One unit of corpus content addressable by its repo-relative path."""

    source_path: str  # repo-relative, POSIX
    source_kind: str
    title: str | None
    content: str
    byte_size: int


# ---------- internal helpers ----------


def _normalize(text: str) -> str:
    """CRLF → LF, strip per-line trailing whitespace.

    Ensures the same logical content produces the same bytes regardless
    of git's autocrlf behavior or editor settings (RESEARCH §Step 3
    determinism contract).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a recursive glob (with ``**``) to a regex.

    Unlike :func:`fnmatch.translate`, this handles ``**`` as "zero or more
    path segments" and treats single ``*`` as "anything except ``/``" —
    the conventional gitignore-style semantics the deny-list and
    allow-list patterns assume.
    """
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # `**/` matches zero or more directory segments
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _matches_any(rel_path: str, patterns: list[str]) -> bool:
    return any(_glob_to_regex(pat).match(rel_path) for pat in patterns)


def _first_h1(text: str) -> str | None:
    for line in text.split("\n"):
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _leading_block_comment(text: str) -> str | None:
    """Extract the leading block comment from a JS/TS source file.

    Recognizes ``/* ... */`` (including JSDoc ``/** ... */``) and a run of
    ``// ...`` lines at the top of file. Stops at the first non-comment,
    non-blank line. Returns ``None`` if no leading comment exists.
    """
    stripped = text.lstrip()
    if stripped.startswith("/*"):
        end = stripped.find("*/")
        if end == -1:
            return None
        return stripped[: end + 2]
    # Possibly a run of // comments
    lines = text.split("\n")
    collected: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("//"):
            collected.append(line)
        elif s == "":
            if collected:
                # blank inside the comment block — keep, but if the next
                # non-blank is not a comment we'll bail out at that point
                collected.append(line)
            else:
                # leading blank lines, ignore
                continue
        else:
            break
    # Trim trailing blanks
    while collected and collected[-1].strip() == "":
        collected.pop()
    if not collected:
        return None
    return "\n".join(collected)


def _emit_markdown(path: Path, rel: str) -> list[SourceDocument]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    content = _normalize(raw)
    return [
        SourceDocument(
            source_path=rel,
            source_kind="markdown",
            title=_first_h1(content),
            content=content,
            byte_size=len(content.encode("utf-8")),
        )
    ]


def _emit_alembic(path: Path, rel: str) -> list[SourceDocument]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    content = _normalize(raw)
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    doc = ast.get_docstring(tree)
    if not doc:
        return []
    # Title = revision string if we can find one as a module-level assignment.
    title: str | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if (
                isinstance(tgt, ast.Name)
                and tgt.id == "revision"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                title = node.value.value
                break
    return [
        SourceDocument(
            source_path=rel,
            source_kind="alembic_migration",
            title=title,
            content=doc,
            byte_size=len(doc.encode("utf-8")),
        )
    ]


def _emit_python(path: Path, rel: str) -> list[SourceDocument]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    content = _normalize(raw)
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    out: list[SourceDocument] = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        out.append(
            SourceDocument(
                source_path=rel,
                source_kind="python_module",
                title=path.stem,
                content=mod_doc,
                byte_size=len(mod_doc.encode("utf-8")),
            )
        )
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                out.append(
                    SourceDocument(
                        source_path=rel,
                        source_kind="python_function",
                        title=node.name,
                        content=doc,
                        byte_size=len(doc.encode("utf-8")),
                    )
                )
    return out


def _emit_frontend(path: Path, rel: str) -> list[SourceDocument]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    content = _normalize(raw)
    comment = _leading_block_comment(content)
    if not comment:
        return []
    return [
        SourceDocument(
            source_path=rel,
            source_kind="frontend_component",
            title=path.stem,
            content=comment,
            byte_size=len(comment.encode("utf-8")),
        )
    ]


def _classify(rel_path: str) -> str:
    """Return the emitter kind for a path that passed the allow-list filter.

    Every path reaching this function has already matched ``SOURCE_GLOBS_V1``
    and survived ``DENY_LIST``, so the dispatch below is exhaustive by
    construction. Markdown is checked first because the allow-list emits
    ``.md`` from many roots; non-markdown is always one of the explicit
    backend/frontend prefixes.
    """
    if rel_path.endswith(".md"):
        return "markdown"
    if rel_path.startswith("backend/alembic/versions/") and rel_path.endswith(".py"):
        return "alembic"
    if rel_path.startswith("backend/app/") and rel_path.endswith(".py"):
        return "python"
    # Only remaining allow-listed kind is frontend (.jsx/.js/.ts/.tsx).
    return "frontend"


# ---------- public entrypoint ----------


def walk_sources(
    *, root: Path, globs: list[str] | None = None
) -> list[SourceDocument]:
    """Walk ``root`` and emit one ``SourceDocument`` per ingestible unit.

    Opens no DB connections; reads no JSON/CSV. Output is sorted by
    ``source_path`` for determinism.

    ``globs`` defaults to :data:`SOURCE_GLOBS_V1`. It is a parameter only so the
    code-derived emitters stay directly testable now that the default globs are
    markdown-only; production callers pass nothing. ``DENY_LIST`` applies
    regardless of what is passed.
    """
    active_globs = SOURCE_GLOBS_V1 if globs is None else globs
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _matches_any(rel, DENY_LIST):
            continue
        if not _matches_any(rel, active_globs):
            continue
        candidates.append(path)

    # Lexicographic sort by repo-relative POSIX path for deterministic ordering.
    candidates.sort(key=lambda p: p.relative_to(root).as_posix())

    out: list[SourceDocument] = []
    for path in candidates:
        rel = path.relative_to(root).as_posix()
        kind = _classify(rel)
        if kind == "markdown":
            out.extend(_emit_markdown(path, rel))
        elif kind == "alembic":
            out.extend(_emit_alembic(path, rel))
        elif kind == "python":
            out.extend(_emit_python(path, rel))
        else:  # frontend
            out.extend(_emit_frontend(path, rel))
    return out
