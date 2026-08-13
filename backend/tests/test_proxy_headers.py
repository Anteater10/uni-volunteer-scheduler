"""W5 sweep S-01: every uvicorn entrypoint behind a proxy must trust its headers.

`deps.rate_limit` keys its Redis bucket on `request.client.host`. Behind a
TLS-terminating proxy — Render's router, or the Caddy container in
docker-compose.prod.yml — that attribute is the *proxy's* address unless uvicorn
is started with `--proxy-headers`, so every caller in the world shares one
bucket per path.

That is an availability bug before it is a security one. The public check-in
endpoints allow 30 requests / 60s and the volunteer flow spends two or more per
person, so with the headers untrusted, a dozen volunteers scanning the event QR
at the same time start returning 429 to each other. It fails on a classroom
floor, mid-event, with no obvious cause.

It also silently degrades two throttles that are doing real work (the venue-code
guesser's ceiling, and the IP half of `check_reset_rate_limit`) and makes the
addresses logged in `auth.py` and `magic.py` useless for an investigation.

These are file-content assertions rather than behavioural ones on purpose. The
flag lives in a start command, so nothing in the running app can observe whether
it was passed — the only place the regression is visible is the file that omits
it. Losing it is a one-word edit and produces no failing request anywhere.
"""
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent

RENDER_ENTRYPOINT = BACKEND / "start_render.sh"
PROD_COMPOSE = REPO / "docker-compose.prod.yml"


def _uvicorn_lines(text: str) -> list[str]:
    """Every logical line that starts a uvicorn server.

    Joins shell line-continuations first, so a command split across lines for
    readability is still seen as one invocation.
    """
    joined = text.replace("\\\n", " ")
    return [
        line
        for line in joined.splitlines()
        # Skip comments: this module's own rationale mentions the flag by name,
        # and so does the comment block in start_render.sh. Matching those
        # would make the test pass while the actual command lacked the flag.
        if "uvicorn" in line and not line.strip().startswith("#")
    ]


@pytest.mark.parametrize(
    "path",
    [RENDER_ENTRYPOINT, PROD_COMPOSE],
    ids=["start_render.sh", "docker-compose.prod.yml"],
)
def test_uvicorn_entrypoints_trust_proxy_headers(path: Path) -> None:
    if not path.exists():
        # The local test container mounts only ./backend at /app, so the
        # repo-root compose file is genuinely absent there. CI checks out the
        # whole repo, so this case runs in the place that gates merges. Skip
        # loudly rather than assert, so a missing file is never read as a pass.
        pytest.skip(f"{path} not present in this checkout (mounted subtree only)")
    lines = _uvicorn_lines(path.read_text())
    assert lines, f"no uvicorn invocation found in {path.name}"
    for line in lines:
        assert "--proxy-headers" in line, (
            f"{path.name} starts uvicorn without --proxy-headers:\n  {line.strip()}\n"
            "Without it request.client.host is the proxy for every request, so "
            "deps.rate_limit collapses every caller into one bucket per path."
        )
        assert "--forwarded-allow-ips" in line, (
            f"{path.name} passes --proxy-headers but not --forwarded-allow-ips:\n"
            f"  {line.strip()}\n"
            "uvicorn only trusts the header from addresses on that list; the "
            "default is 127.0.0.1, so a proxy on any other address is ignored "
            "and --proxy-headers silently does nothing."
        )


def test_render_entrypoint_still_migrates_before_serving() -> None:
    """Guard the ordering the outage of 2026-08-13 depended on.

    `alembic upgrade head` must run before uvicorn, and `set -eu` must stay, so
    a failed migration is a failed start rather than a server answering requests
    against a schema it does not match.
    """
    text = RENDER_ENTRYPOINT.read_text()
    assert "set -eu" in text
    migrate_at = text.index("alembic upgrade head")
    # Index into the original text, not the continuation-joined form — the
    # joined line does not appear verbatim in the file. The last "uvicorn"
    # occurrence is the command; earlier ones are in the comment block.
    serve_at = text.rindex("uvicorn")
    assert migrate_at < serve_at, (
        "start_render.sh must migrate before serving traffic"
    )
