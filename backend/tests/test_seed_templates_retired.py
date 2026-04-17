"""Phase 16 Plan 01 (D-35): seed module templates retired via soft-delete.

conftest creates tables directly from Base.metadata so no seed rows exist in
the test DB. This test checks that IF any of the retired slugs appear in
module_templates, none of them are active (deleted_at IS NULL).
"""
from app import models


RETIRED_SLUGS = [
    "intro-physics",
    "intro-astro",
    "intro-bio",
    "intro-chem",
    "orientation",
]


def test_seed_templates_have_no_active_rows(db_session):
    active = (
        db_session.query(models.ModuleTemplate)
        .filter(models.ModuleTemplate.slug.in_(RETIRED_SLUGS))
        .filter(models.ModuleTemplate.deleted_at.is_(None))
        .count()
    )
    assert active == 0, (
        f"Retired seed templates still active: expected 0, got {active}. "
        "Run alembic upgrade head to apply 0012."
    )


def test_migration_0012_file_exists():
    """Guard that the migration file exists with expected rename logic."""
    from pathlib import Path

    mig = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "0012_soft_delete_seed_module_templates_and_normalize_audit_kinds.py"
    )
    assert mig.is_file(), f"Migration 0012 not found at {mig}"
    text = mig.read_text()
    for slug in RETIRED_SLUGS:
        assert f"'{slug}'" in text, f"slug {slug} not referenced in migration 0012"
    assert "signup_cancelled" in text, "audit kind rename missing from migration 0012"
