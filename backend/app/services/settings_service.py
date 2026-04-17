"""Phase 29 (HIDE-01) — accessor for the site-wide singleton settings row.

The site_settings table is a one-row singleton (id=1). This accessor
returns the row, creating it lazily if the migration didn't run in a
test context (it's cheap and keeps callers from NPE-ing).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


def get_app_settings(db: Session) -> models.SiteSettings:
    """Return the singleton ``site_settings`` row, creating it if missing.

    Default values mirror the migration defaults:
      - ``default_privacy_mode`` = PrivacyMode.full
      - ``hide_past_events_from_public`` = True
    """
    row = db.query(models.SiteSettings).filter(models.SiteSettings.id == 1).first()
    if row is None:
        row = models.SiteSettings(id=1)
        db.add(row)
        db.flush()
    return row
