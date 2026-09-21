"""public_signup_service paths no test reached (roadmap #168 ratchet)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app import models
from app.schemas import PublicSignupCreate, SignupResponseCreate
from app.services import public_signup_service as svc
from tests.fixtures.factories import EventFactory, SlotFactory
from tests.fixtures.helpers import _bind_factories

SCHEMA = [{"id": "tshirt", "label": "T-shirt size", "type": "text", "required": True}]


def _payload(*, slot_ids=(), shift_ids=(), responses=(), phone="(805) 555-1212", email=None):
    return PublicSignupCreate(
        email=email or f"gap-{uuid.uuid4().hex[:8]}@example.com",
        first_name="Gap",
        last_name="Test",
        phone=phone,
        slot_ids=list(slot_ids),
        shift_ids=list(shift_ids),
        responses=[SignupResponseCreate(**r) for r in responses],
    )


def _event(db_session, **kw):
    _bind_factories(db_session)
    return EventFactory(**kw)


def _orientation(event):
    return SlotFactory(event=event, slot_type=models.SlotType.ORIENTATION, capacity=5)


def _shift_id(event):
    """A shift on an event with no orientation slots, which is exempt from
    the orientation gate, so the shift books without credit."""
    return SlotFactory(event=event, capacity=5).shift_id


class TestGuardsForRowsThatVanished:
    """The event ids these guards receive come from slot/shift rows read
    moments earlier without a lock. If the event is deleted in between, the
    guard steps aside and the booking loop's 404 answers instead."""

    def test_visibility_guard_steps_aside_for_a_missing_event(self, db_session):
        assert svc._ensure_event_visible(db_session, uuid.uuid4()) is None

    def test_window_guard_steps_aside_for_a_missing_event(self, db_session):
        assert svc._ensure_signup_window(db_session, uuid.uuid4()) is None

    def test_window_guard_bypass_skips_the_check(self, db_session):
        assert svc._ensure_signup_window(db_session, uuid.uuid4(), bypass=True) is None


def test_an_invalid_phone_is_a_422(db_session):
    event = _event(db_session)
    slot = _orientation(event)
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        svc.create_public_signup(db_session, _payload(slot_ids=[slot.id], phone="555-0000"))
    assert exc.value.status_code == 422


class TestCustomAnswers:
    def test_answers_are_stored_on_an_orientation_signup(self, db_session):
        event = _event(db_session, form_schema=SCHEMA)
        slot = _orientation(event)
        db_session.flush()

        out = svc.create_public_signup(
            db_session,
            _payload(slot_ids=[slot.id], responses=[{"field_id": "tshirt", "value": "M"}]),
        )

        assert out.missing_required == []
        row = db_session.query(models.SignupResponse).filter_by(
            signup_id=out.signup_ids[0]
        ).one()
        assert row.field_id == "tshirt"

    def test_answers_are_stored_on_a_shift_commitment(self, db_session):
        event = _event(db_session, form_schema=SCHEMA)
        shift_id = _shift_id(event)
        db_session.flush()

        out = svc.create_public_signup(
            db_session,
            _payload(shift_ids=[shift_id], responses=[{"field_id": "tshirt", "value": "L"}]),
        )

        assert out.shift_signup_ids
        row = db_session.query(models.SignupResponse).filter_by(
            shift_signup_id=out.shift_signup_ids[0]
        ).one()
        assert row.field_id == "tshirt"

    def test_sending_nothing_reports_every_required_question(self, db_session):
        """Soft warning, never a refusal: organizers are the authority."""
        event = _event(db_session, form_schema=SCHEMA)
        slot = _orientation(event)
        db_session.flush()

        out = svc.create_public_signup(db_session, _payload(slot_ids=[slot.id]))

        assert out.missing_required == ["tshirt"]


class TestConfirmTokenExposure:
    def test_the_token_is_returned_only_under_the_testing_flag(self, db_session, monkeypatch):
        event = _event(db_session)
        a, b = _orientation(event), _orientation(event)
        db_session.flush()

        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)
        hidden = svc.create_public_signup(db_session, _payload(slot_ids=[a.id]))
        assert hidden.confirm_token is None

        monkeypatch.setenv("EXPOSE_TOKENS_FOR_TESTING", "1")
        shown = svc.create_public_signup(db_session, _payload(slot_ids=[b.id]))
        assert shown.confirm_token
