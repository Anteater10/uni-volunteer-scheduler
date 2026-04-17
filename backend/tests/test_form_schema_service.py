"""Phase 22 — custom form fields service tests.

Covers:
  1. effective-schema resolution: event override preferred.
  2. effective-schema fall-back: event override NULL → template default.
  3. append_event_field adds to override, persists without duplicate.
  4. validate_responses returns missing required ids (soft-warn).
  5. persist_responses upserts on (signup_id, field_id).
  6. set_template_default_schema writes an audit log.
  7. set_event_schema validates schema shape and rejects duplicate ids.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models import (
    AuditLog,
    Event,
    ModuleTemplate,
    ModuleType,
    Signup,
    SignupResponse,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from app.services import form_schema_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user(db):
    from tests.fixtures.helpers import make_user
    from app.models import UserRole
    return make_user(db, role=UserRole.admin)


def _make_template(db, *, slug: str, default_form_schema=None):
    tpl = ModuleTemplate(
        slug=slug,
        name=slug.title(),
        default_capacity=20,
        duration_minutes=90,
        type=ModuleType.module,
        session_count=1,
        family_key=slug,
        default_form_schema=default_form_schema or [],
    )
    db.add(tpl)
    db.flush()
    return tpl


def _make_event(db, *, module_slug: str | None, owner_id):
    event = Event(
        owner_id=owner_id,
        title=f"Event {module_slug or 'none'}",
        start_date=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
        module_slug=module_slug,
    )
    db.add(event)
    db.flush()
    return event


def _make_signup(db, event) -> Signup:
    vol = Volunteer(
        email=f"{uuid.uuid4().hex[:8]}@example.test",
        first_name="V", last_name="Olunteer",
    )
    db.add(vol)
    db.flush()
    slot = Slot(
        event_id=event.id,
        start_time=event.start_date,
        end_time=event.end_date,
        capacity=10,
        slot_type=SlotType.PERIOD,
        date=date_type(2026, 4, 15),
    )
    db.add(slot)
    db.flush()
    s = Signup(
        volunteer_id=vol.id,
        slot_id=slot.id,
        status=SignupStatus.confirmed,
    )
    db.add(s)
    db.flush()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_effective_schema_uses_event_override(db_session):
    admin = _make_user(db_session)
    template_schema = [
        {"id": "foo", "label": "Foo?", "type": "text", "required": True, "order": 1}
    ]
    tpl = _make_template(db_session, slug="mod-a", default_form_schema=template_schema)
    event = _make_event(db_session, module_slug="mod-a", owner_id=admin.id)

    override = [
        {"id": "bar", "label": "Bar?", "type": "text", "required": False, "order": 1}
    ]
    event.form_schema = override
    db_session.add(event)
    db_session.flush()

    effective = form_schema_service.get_effective_schema(db_session, event.id)
    assert [f["id"] for f in effective] == ["bar"]


def test_effective_schema_falls_back_to_template_default(db_session):
    admin = _make_user(db_session)
    template_schema = [
        {"id": "tshirt", "label": "T-shirt?", "type": "select",
         "options": ["S", "M"], "order": 1}
    ]
    _make_template(
        db_session, slug="mod-b", default_form_schema=template_schema
    )
    event = _make_event(db_session, module_slug="mod-b", owner_id=admin.id)
    assert event.form_schema is None

    effective = form_schema_service.get_effective_schema(db_session, event.id)
    assert [f["id"] for f in effective] == ["tshirt"]


def test_append_event_field_seeds_from_template_default(db_session):
    admin = _make_user(db_session)
    template_schema = [
        {"id": "foo", "label": "Foo?", "type": "text", "order": 1}
    ]
    _make_template(
        db_session, slug="mod-c", default_form_schema=template_schema
    )
    event = _make_event(db_session, module_slug="mod-c", owner_id=admin.id)

    new_field = {"id": "parking", "label": "Parking?", "type": "checkbox",
                 "options": ["yes", "no"]}
    schema = form_schema_service.append_event_field(
        db_session, event.id, new_field, actor=admin
    )
    db_session.refresh(event)
    assert [f["id"] for f in schema] == ["foo", "parking"]
    # Duplicate append should 409.
    with pytest.raises(HTTPException) as exc:
        form_schema_service.append_event_field(
            db_session, event.id, new_field, actor=admin
        )
    assert exc.value.status_code == 409


def test_validate_responses_returns_missing_required(db_session):
    schema = [
        {"id": "emergency_contact", "label": "Emergency contact", "type": "text",
         "required": True, "order": 1},
        {"id": "tshirt", "label": "T-shirt", "type": "select",
         "options": ["S", "M"], "required": False, "order": 2},
    ]
    # Skip the required field entirely; blank-string fails too.
    missing = form_schema_service.validate_responses(
        schema,
        [{"field_id": "tshirt", "value": "M"}],
    )
    assert missing == ["emergency_contact"]

    missing = form_schema_service.validate_responses(
        schema,
        [
            {"field_id": "emergency_contact", "value": "   "},
            {"field_id": "tshirt", "value": "S"},
        ],
    )
    assert missing == ["emergency_contact"]

    # Fully answered — empty list.
    missing = form_schema_service.validate_responses(
        schema,
        [
            {"field_id": "emergency_contact", "value": "Jane Doe 805-555-1111"},
            {"field_id": "tshirt", "value": "M"},
        ],
    )
    assert missing == []


def test_persist_responses_upserts(db_session):
    admin = _make_user(db_session)
    _make_template(db_session, slug="mod-d")
    event = _make_event(db_session, module_slug="mod-d", owner_id=admin.id)
    signup = _make_signup(db_session, event)

    # First call — creates rows.
    form_schema_service.persist_responses(
        db_session,
        signup.id,
        [
            {"field_id": "emergency_contact", "value": "Jane"},
            {"field_id": "tshirt", "value": "M"},
        ],
    )
    rows = (
        db_session.query(SignupResponse)
        .filter(SignupResponse.signup_id == signup.id)
        .all()
    )
    assert {r.field_id for r in rows} == {"emergency_contact", "tshirt"}

    # Second call — updates (not duplicates).
    form_schema_service.persist_responses(
        db_session,
        signup.id,
        [{"field_id": "tshirt", "value": "L"}],
    )
    rows = (
        db_session.query(SignupResponse)
        .filter(SignupResponse.signup_id == signup.id)
        .all()
    )
    by_id = {r.field_id: r for r in rows}
    assert by_id["tshirt"].value_text == "L"
    assert by_id["emergency_contact"].value_text == "Jane"
    assert len(rows) == 2


def test_set_template_default_schema_writes_audit(db_session):
    admin = _make_user(db_session)
    _make_template(db_session, slug="mod-e")

    schema = [
        {"id": "foo", "label": "Foo?", "type": "text", "required": True, "order": 1}
    ]
    form_schema_service.set_template_default_schema(
        db_session, "mod-e", schema, actor=admin
    )
    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "form_schema_template_set")
        .all()
    )
    assert logs, "expected an audit log entry for template schema set"
    assert logs[-1].entity_id == "mod-e"


def test_set_event_schema_rejects_invalid(db_session):
    admin = _make_user(db_session)
    _make_template(db_session, slug="mod-f")
    event = _make_event(db_session, module_slug="mod-f", owner_id=admin.id)

    # Duplicate id
    bad_schema = [
        {"id": "x", "label": "X", "type": "text", "order": 1},
        {"id": "x", "label": "X again", "type": "text", "order": 2},
    ]
    with pytest.raises(HTTPException) as exc:
        form_schema_service.set_event_schema(
            db_session, event.id, bad_schema, actor=admin
        )
    assert exc.value.status_code == 422

    # Select without options
    with pytest.raises(HTTPException) as exc:
        form_schema_service.set_event_schema(
            db_session,
            event.id,
            [{"id": "s", "label": "S", "type": "select", "order": 1}],
            actor=admin,
        )
    assert exc.value.status_code == 422
