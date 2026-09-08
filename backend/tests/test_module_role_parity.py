"""Organizer == admin on every module/template endpoint (issue #9).

Andy ruled 2026-09-08: **an organizer is an admin with fewer views.** They see,
edit and perform all changes on all events, never only the ones they own. The
module/template routes already honour that — every one takes
``Depends(require_staff)`` rather than ``require_admin``, and none filters by
owner — but *nothing held it there*. Before this file, neither
``test_admin_modules.py`` nor ``test_modules_crud.py`` mentioned the organizer
role at all, so narrowing any of these guards back to ``require_admin`` would
have kept a green suite.

That mattered most right before Phase L3, which reworks
``deps.py:get_current_user`` — the single chokepoint all seven of these
endpoints resolve their caller through. A tightening there would silently cost
organizers access, with every admin-side test still passing.

So the assertion here is deliberately about *parity*, not about specific status
codes: whatever an admin gets, an organizer gets. A test pinned to "200" would
start failing for unrelated reasons the first time a response shape changed,
and would not actually be checking the thing the ruling is about.

Scope note: this covers the seven admin-router module endpoints. It does **not**
cover the copilot's tool-layer owner filters, which are wrong in the same way
and are tracked separately as ROADMAP #36 / #100. Fixing those is P4's job, not
this file's.

Issue #9 also asked for a written audit of these surfaces. This file is that
audit, in the only form that cannot go stale.
"""
import pytest

from app import models
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def admin_h(client, db_session):
    u = make_user(db_session, email="admin-parity@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, u)


@pytest.fixture
def organizer_h(client, db_session):
    u = make_user(
        db_session, email="organizer-parity@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    return auth_headers(client, u)


@pytest.fixture
def participant_h(client, db_session):
    """The control. Parity is only meaningful if somebody is still refused."""
    u = make_user(
        db_session,
        email="participant-parity@example.com",
        role=models.UserRole.participant,
    )
    db_session.commit()
    return auth_headers(client, u)


def _seed_module(client, headers, slug):
    r = client.post(
        "/api/v1/admin/modules",
        json={"slug": slug, "name": f"Module {slug}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return slug


def _delete_first(client, headers, slug):
    """Restore only means something on a soft-deleted module.

    Without this the restore case returned 409 for BOTH roles — parity held,
    but the endpoint was never exercised. The second assertion below is what
    caught that, and it is why the assertion exists.
    """
    r = client.delete(f"/api/v1/admin/modules/{slug}", headers=headers)
    assert r.status_code in (200, 204), r.text


# Each case: (label, setup_or_None, callable(client, headers, slug) -> response).
# ``slug`` is a module seeded fresh per case, so ordering between cases cannot
# matter — a delete case must not strand a later restore case. ``setup`` runs as
# ADMIN for both arms, so it never itself proves or disproves parity.
CASES = [
    ("list", None, lambda c, h, s: c.get("/api/v1/admin/modules", headers=h)),
    (
        "create",
        None,
        lambda c, h, s: c.post(
            "/api/v1/admin/modules",
            json={"slug": f"{s}-new", "name": "Created"},
            headers=h,
        ),
    ),
    (
        "update",
        None,
        lambda c, h, s: c.patch(
            f"/api/v1/admin/modules/{s}", json={"name": "Renamed"}, headers=h
        ),
    ),
    ("delete", None, lambda c, h, s: c.delete(f"/api/v1/admin/modules/{s}", headers=h)),
    (
        "restore",
        _delete_first,
        lambda c, h, s: c.post(f"/api/v1/admin/modules/{s}/restore", headers=h),
    ),
    (
        "clone",
        None,
        lambda c, h, s: c.post(
            f"/api/v1/admin/modules/{s}/clone",
            json={"new_slug": f"{s}-clone", "new_name": "Cloned"},
            headers=h,
        ),
    ),
    (
        "default-form-schema",
        None,
        lambda c, h, s: c.put(
            f"/api/v1/admin/modules/{s}/default-form-schema",
            json={"schema": []},
            headers=h,
        ),
    ),
]


@pytest.mark.parametrize("label,setup,call", CASES, ids=[c[0] for c in CASES])
def test_organizer_gets_the_same_answer_as_admin(
    client, db_session, admin_h, organizer_h, label, setup, call
):
    """Parity, not a fixed status code — see the module docstring."""
    admin_slug = _seed_module(client, admin_h, f"parity-admin-{label}")
    organizer_slug = _seed_module(client, admin_h, f"parity-org-{label}")
    if setup:
        setup(client, admin_h, admin_slug)
        setup(client, admin_h, organizer_slug)

    as_admin = call(client, admin_h, admin_slug)
    as_organizer = call(client, organizer_h, organizer_slug)

    assert as_organizer.status_code == as_admin.status_code, (
        f"{label}: organizer got {as_organizer.status_code}, admin got "
        f"{as_admin.status_code}. Organizers are admins with fewer views "
        f"(ruled 2026-09-08) — if this endpoint is now meant to be admin-only, "
        f"that is a product decision, not a refactor side effect."
    )
    assert as_organizer.status_code < 400, (
        f"{label}: both roles were refused ({as_organizer.status_code}). "
        f"Parity held, but the endpoint stopped working for staff entirely."
    )


@pytest.mark.parametrize("label,setup,call", CASES, ids=[c[0] for c in CASES])
def test_participant_is_still_refused(
    client, db_session, admin_h, participant_h, label, setup, call
):
    """The guard is ``require_staff``, not "no guard".

    Without this, the parity test above would still pass if somebody deleted
    the dependency altogether.
    """
    slug = _seed_module(client, admin_h, f"parity-deny-{label}")
    if setup:
        setup(client, admin_h, slug)

    r = call(client, participant_h, slug)

    assert r.status_code in (401, 403), (
        f"{label}: a participant got {r.status_code}. These routes are "
        f"staff-only; parity between admin and organizer is not parity with "
        f"everyone."
    )
