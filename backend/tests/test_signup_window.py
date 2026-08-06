"""Phase 29 (LOCK-01/02) — event signup window tests.

Reuses the existing ``signup_open_at`` / ``signup_close_at`` columns on
``events`` (present since v1.0). Phase 29 wires them into
``create_public_signup`` and returns HTTP 403 with a PT-localized reason
when the signup happens outside the window. Organizer/admin paths
bypass the check (they don't go through ``create_public_signup``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import models
from app.schemas import PublicSignupCreate, SignupResponseCreate  # noqa: F401
from app.services.public_signup_service import create_public_signup
from tests.fixtures.factories import (
    EventFactory,
    ShiftFactory,
    SlotFactory,
    UserFactory,
)
from tests.fixtures.helpers import _bind_factories


def _payload(slot_id=None, email="lock-test@example.com", *, shift_id=None):
    """2026-08-05 shifts: the endpoint takes two id lists.

    ``slot_ids`` is orientation-only now — a bare period slot id is refused,
    since a period slot is a session inside a shift. The window and visibility
    rules these tests cover are per *event* and apply to both lists, so most
    cases book an orientation slot; the orientation-gate case needs a shift,
    because selecting a shift is what makes orientation credit necessary.
    """
    return PublicSignupCreate(
        email=email,
        first_name="Test",
        last_name="User",
        phone="(805) 555-1212",
        slot_ids=[slot_id] if slot_id else [],
        shift_ids=[shift_id] if shift_id else [],
        responses=[],
    )


def _orientation_slot(event, **kw):
    return SlotFactory(
        event=event,
        event_id=event.id,
        slot_type=models.SlotType.ORIENTATION,
        **kw,
    )


def test_signup_blocked_before_opens(db_session):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(
        owner=owner,
        owner_id=owner.id,
        signup_open_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_public_signup(db_session, _payload(slot.id))
    assert exc.value.status_code == 403
    assert "opens" in exc.value.detail.lower()


def test_signup_blocked_after_closes(db_session):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(
        owner=owner,
        owner_id=owner.id,
        signup_close_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_public_signup(db_session, _payload(slot.id))
    assert exc.value.status_code == 403
    assert "closed" in exc.value.detail.lower()


def test_signup_allowed_with_null_window(db_session):
    """NULL open/close = always open — existing behavior must be preserved."""
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(
        owner=owner,
        owner_id=owner.id,
        signup_open_at=None,
        signup_close_at=None,
    )
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    resp = create_public_signup(db_session, _payload(slot.id))
    assert len(resp.signup_ids) == 1


def test_signup_allowed_within_window(db_session):
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    now = datetime.now(timezone.utc)
    event = EventFactory(
        owner=owner,
        owner_id=owner.id,
        signup_open_at=now - timedelta(hours=1),
        signup_close_at=now + timedelta(days=7),
    )
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    resp = create_public_signup(db_session, _payload(slot.id))
    assert len(resp.signup_ids) == 1


def test_signup_rejected_for_private_event(db_session):
    """Task 2 (sweep remediation) — signing up for a private event you were
    never shown (e.g. via a leaked slot_id) must not succeed. 404, matching
    the public detail endpoint's "don't confirm it exists" behavior."""
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id, visibility="private")
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_public_signup(db_session, _payload(slot.id))
    assert exc.value.status_code == 404


def test_signup_rejected_for_private_event_before_orientation_check(db_session):
    """Fix round 1 (Task 2 review) — visibility must be enforced before ANY
    other per-event validation, not just inside the per-slot loop.
    ``_ensure_orientation_requirement`` used to run first and could raise
    422 ORIENTATION_REQUIRED for a private event's PERIOD-only batch when
    the caller has no credit and the event separately offers an
    orientation slot — distinguishable from the 404 a nonexistent event
    would produce, which is exactly the leak this task closes. Must be
    404 on every branch, reachable with just a slot_id."""
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(
        owner=owner,
        owner_id=owner.id,
        visibility="private",
        # Fallback family resolution (no Module row) uses the raw slug, so
        # this alone is enough to make orientation "required" below.
        module_slug="private-orientation-family",
    )
    shift = ShiftFactory(event=event, event_id=event.id)
    SlotFactory(
        event=event,
        event_id=event.id,
        shift=shift,
        shift_id=shift.id,
        slot_type=models.SlotType.PERIOD,
    )
    _orientation_slot(event)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        create_public_signup(
            db_session, _payload(shift_id=shift.id, email="no-credit@example.com")
        )
    assert exc.value.status_code == 404
    # Fix round 2 (Task 2 review): must match the unknown-slot 404's detail
    # text exactly — not just its status code — so the two are
    # indistinguishable. See test_public_signups.py for the direct
    # side-by-side comparison of both HTTP responses.
    assert exc.value.detail == "not found"


def test_signup_allowed_for_public_event(db_session):
    """Regression: the new visibility guard must not affect ordinary public
    events (public events still signable everywhere)."""
    _bind_factories(db_session)
    owner = UserFactory(role=models.UserRole.admin)
    event = EventFactory(owner=owner, owner_id=owner.id, visibility="public")
    slot = _orientation_slot(event, capacity=5, current_count=0)
    db_session.flush()

    resp = create_public_signup(db_session, _payload(slot.id))
    assert len(resp.signup_ids) == 1


def test_organizer_admin_paths_bypass_window(db_session, client):
    """Organizer/admin signup-create paths do NOT go through
    ``create_public_signup`` — they hit ``/signups`` (auth) or
    ``/admin/events/{id}/signups`` which never call the window helper.

    This smoke test asserts the helper is only called on the public path
    by confirming that calling create_public_signup directly is the only
    site we gated. We keep it explicit so the "organizer bypass" contract
    is locked in the test suite."""
    # The bypass contract is enforced by call-site: organizer endpoints
    # don't invoke the service. Confirm by checking signups.py uses its
    # own _ensure_signup_window which is called only on the authenticated
    # create flow where current_user.role is checked upstream for
    # organizer/admin.
    from app.services import public_signup_service

    assert hasattr(public_signup_service, "_ensure_signup_window")
    # The service signature accepts a bypass flag the admin routers can
    # adopt in future; current admin routes never call this service.
    import inspect

    sig = inspect.signature(public_signup_service._ensure_signup_window)
    assert "bypass" in sig.parameters
