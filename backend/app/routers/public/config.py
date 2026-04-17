"""Public runtime-config endpoint — Phase 27.

Exposes the handful of feature flags the public frontend needs at boot
(currently just ``sms_enabled`` so the signup form can conditionally render
the SMS opt-in checkbox). No auth, no rate-limit — this is static config.
"""
from fastapi import APIRouter

from ...config import settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config")
def public_config() -> dict:
    """Frontend feature flags. Safe to cache; changes rarely."""
    return {
        "sms_enabled": bool(settings.sms_enabled),
    }
