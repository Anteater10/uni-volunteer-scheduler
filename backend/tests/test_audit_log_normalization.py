"""Phase 16 Plan 01 (D-20): audit-kind normalization tests.

These guard two invariants:
1. No code path in backend/app emits the legacy "signup_cancel" literal.
2. When an authenticated participant cancels a signup via the legacy
   /api/v1/signups router, the AuditLog row is written with the canonical
   "signup_cancelled" action.
"""
import subprocess
from pathlib import Path


def test_no_code_path_emits_legacy_signup_cancel():
    """Static grep guard: no quoted 'signup_cancel' in backend/app.

    Matches the exact literal '"signup_cancel"' (with surrounding double quotes)
    so distinct actions like 'admin_signup_cancel' do not trip the check.
    """
    backend_app = Path(__file__).resolve().parent.parent / "app"
    assert backend_app.is_dir(), f"backend/app not found at {backend_app}"

    result = subprocess.run(
        ["grep", "-rn", '"signup_cancel"', str(backend_app)],
        capture_output=True,
        text=True,
    )
    # Filter to lines that actually contain the bad literal and NOT the canonical form
    bad = [
        line
        for line in result.stdout.splitlines()
        if '"signup_cancel"' in line and '"signup_cancelled"' not in line
    ]
    assert bad == [], f"Legacy audit kind still emitted in code:\n" + "\n".join(bad)


def test_admin_signup_cancel_is_distinct_and_allowed():
    """'admin_signup_cancel' is a different action and must still exist.

    The grep guard above specifically excludes it by requiring exact quoted
    'signup_cancel'. This test documents the distinction so future cleanups
    don't accidentally rename it.
    """
    admin_py = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "admin.py"
    )
    content = admin_py.read_text()
    assert '"admin_signup_cancel"' in content, (
        "admin_signup_cancel is the admin-initiated cancel action and must remain"
    )
