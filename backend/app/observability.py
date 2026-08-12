"""Process-level observability: logging config + optional Sentry.

Before this module existed nothing called ``logging.basicConfig``/
``dictConfig`` anywhere, so every ``logging.getLogger(__name__)`` in the
app wrote through unconfigured root handlers — WARNING-and-up only, no
timestamps. Both entry points (uvicorn via ``app.main``, celery via
``app.celery_app``) call :func:`configure_logging` + :func:`init_sentry`.
"""
from __future__ import annotations

import logging
import logging.config

from .config import settings

logger = logging.getLogger(__name__)

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    """Configure root logging from ``settings.log_level``. Idempotent."""
    level_name = (settings.log_level or "INFO").upper()
    if level_name not in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        level_name = "INFO"
    logging.config.dictConfig({
        "version": 1,
        # uvicorn/celery own loggers keep working; we only set the root.
        "disable_existing_loggers": False,
        "formatters": {"default": {"format": _FORMAT}},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            }
        },
        "root": {"level": level_name, "handlers": ["stdout"]},
    })


def mask_email(value: object) -> str:
    """Return an email safe to write to a log line.

    BASE-SEC-39. Volunteer addresses were logged in full at INFO on every
    magic-link build and every broadcast delivery, so the application log
    accumulated a roster of who signed up for what — student PII sitting in a
    stream that gets shipped to whatever aggregator the host provides and is
    read by people who have no business seeing it. Masking keeps the log's
    only real use (matching one delivery to one complaint) while removing the
    part that makes it a dataset: ``a****y@ucsb.edu``.

    The domain stays because it is not personal and is what actually explains
    delivery failures. Anything unparseable is dropped entirely rather than
    guessed at.
    """
    s = str(value or "").strip()
    if "@" not in s:
        return "(redacted)"
    local, _, domain = s.rpartition("@")
    if not local or not domain:
        return "(redacted)"
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked}@{domain}"


# Header names are matched case-insensitively; both spellings show up
# depending on which integration built the event.
_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _scrub_event(event, hint):
    """Last line of defence before an error leaves the building.

    ``max_request_body_size="never"`` should already prevent bodies being
    attached; this drops them again regardless, along with the headers that
    carry a bearer token. Belt and braces on purpose — the cost of a
    redundant check here is nothing, and the cost of missing one is a
    plaintext password sitting in a third party's dashboard.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers.pop(name, None)
    return event


def init_sentry() -> bool:
    """Initialise Sentry when SENTRY_DSN is configured. Returns True on init.

    Deliberately optional: an empty DSN (the default) is a silent no-op, and
    a missing sentry-sdk package degrades to a warning instead of taking the
    app down — error monitoring must never be the thing that breaks boot.
    """
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "error monitoring disabled"
        )
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # Error monitoring only — no performance tracing volume.
        traces_sample_rate=0.0,
        # A 500 anywhere on an authenticated route would otherwise ship the
        # request body to a third party. On /auth/change-password that body
        # is a plaintext password; on the public signup path it is a
        # volunteer's name, email and phone. Neither belongs in an error
        # tracker, and no amount of after-the-fact scrubbing is as reliable
        # as never capturing it.
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub_event,
    )
    logger.info("sentry initialised (environment=%s)", settings.environment)
    return True
