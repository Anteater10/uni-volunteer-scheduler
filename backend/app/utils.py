"""Shared utilities for routers and services."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now. Use instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)
