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
    )
    logger.info("sentry initialised (environment=%s)", settings.environment)
    return True
