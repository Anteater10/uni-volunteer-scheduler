"""Phase 28 — unit tests for qr_service + confirmation-email QR embedding."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services import qr_service
from app import emails, models
from tests.fixtures.factories import (
    SignupFactory,
    SlotFactory,
    EventFactory,
    VolunteerFactory,
    UserFactory,
)


# ----------------------------------------------------------------------
# generate_qr_png — pure PNG
# ----------------------------------------------------------------------


def test_generate_qr_png_nonempty_for_sample_url():
    payload = "https://example.com/manage?manage_token=abc123"
    png = qr_service.generate_qr_png(payload)
    assert isinstance(png, bytes)
    assert len(png) > 0
    # PIL must be able to load the bytes — proves they're a valid PNG.
    img = Image.open(io.BytesIO(png))
    img.verify()  # raises if corrupt


def test_generate_qr_png_rejects_empty_payload():
    with pytest.raises(ValueError):
        qr_service.generate_qr_png("")


def test_generate_qr_png_scales_with_payload_length():
    short = qr_service.generate_qr_png("x")
    long = qr_service.generate_qr_png("x" * 200)
    # Longer data → denser QR → larger PNG (loose check).
    assert len(long) >= len(short)


# ----------------------------------------------------------------------
# generate_signup_qr — builds manage URL, issues token if needed
# ----------------------------------------------------------------------


def _bind_factories(db):
    for f in (
        SignupFactory,
        SlotFactory,
        EventFactory,
        VolunteerFactory,
        UserFactory,
    ):
        f._meta.sqlalchemy_session = db


def test_generate_signup_qr_issues_manage_token_and_returns_url(db_session):
    _bind_factories(db_session)
    signup = SignupFactory()
    db_session.flush()

    png, url = qr_service.generate_signup_qr(db_session, signup.id)

    assert isinstance(png, bytes) and len(png) > 0
    assert "/manage?manage_token=" in url
    # Verify the token row landed
    tokens = (
        db_session.query(models.MagicLinkToken)
        .filter_by(signup_id=signup.id)
        .all()
    )
    assert len(tokens) >= 1
    assert any(
        t.purpose == models.MagicLinkPurpose.SIGNUP_MANAGE for t in tokens
    )


def test_generate_signup_qr_uses_supplied_raw_token(db_session):
    _bind_factories(db_session)
    signup = SignupFactory()
    db_session.flush()

    # Pre-inject: issue a token, get raw back
    from app.magic_link_service import issue_token

    raw = issue_token(
        db_session,
        signup=signup,
        email=signup.volunteer.email,
        purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=signup.volunteer_id,
    )
    db_session.flush()

    png, url = qr_service.generate_signup_qr(
        db_session, signup.id, raw_token=raw
    )
    assert raw in url


def test_generate_signup_qr_missing_signup_raises(db_session):
    import uuid

    with pytest.raises(LookupError):
        qr_service.generate_signup_qr(db_session, uuid.uuid4())


# ----------------------------------------------------------------------
# send_confirmation builder — emits QR + CID + img tag
# ----------------------------------------------------------------------


def test_send_confirmation_includes_cid_attachment_and_img_tag(db_session):
    _bind_factories(db_session)
    signup = SignupFactory()
    db_session.flush()

    payload = emails.send_confirmation(signup)

    assert "html_body" in payload
    cid = f"qr-{signup.id}"
    assert f'cid:{cid}' in payload["html_body"]
    assert "Show this to the organizer when you arrive" in payload["html_body"]

    atts = payload.get("inline_attachments") or []
    assert len(atts) == 1
    assert atts[0]["cid"] == cid
    assert atts[0]["subtype"] == "png"
    assert isinstance(atts[0]["content"], bytes) and len(atts[0]["content"]) > 0

    # Plain-text body carries the fallback URL line (QR-01 copy).
    assert "/manage?manage_token=" in payload["text_body"]


def test_send_confirmation_without_session_still_returns_payload():
    """Defensive path: a signup detached from a session (e.g. unit-test
    synthesis) still yields a valid email — no QR, no attachment."""
    event = models.Event(
        id=None,
        owner_id=None,
        title="Solo event",
        visibility="public",
    )
    slot = models.Slot(
        id=None,
        event=event,
        start_time=__import__("datetime").datetime(2026, 4, 20, 10, 0),
        end_time=__import__("datetime").datetime(2026, 4, 20, 12, 0),
        capacity=10,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
    )
    volunteer = models.Volunteer(
        id=None,
        email="solo@example.com",
        first_name="Solo",
        last_name="Test",
    )
    signup = models.Signup(
        id=None,
        volunteer=volunteer,
        volunteer_id=None,
        slot=slot,
        slot_id=None,
        status=models.SignupStatus.confirmed,
    )
    payload = emails.send_confirmation(signup)
    assert payload["subject"].startswith("Your signup for")
    assert "inline_attachments" not in payload


# ----------------------------------------------------------------------
# build_signup_confirmation_email (public-signup batch path) — QR
# ----------------------------------------------------------------------


def test_build_signup_confirmation_email_attaches_qr_per_signup(db_session):
    _bind_factories(db_session)
    signup = SignupFactory()
    db_session.flush()

    subject, html, attachments = emails.build_signup_confirmation_email(
        signup.volunteer,
        [signup],
        token="rawtoken-for-test-0123456789ab",
        event=signup.slot.event,
        db=db_session,
    )
    assert "Confirm" in subject or subject  # sanity
    assert f"cid:qr-{signup.id}" in html
    assert any(a["cid"] == f"qr-{signup.id}" for a in attachments)


def test_build_signup_confirmation_email_no_db_no_attachments(db_session):
    _bind_factories(db_session)
    signup = SignupFactory()
    db_session.flush()

    subject, html, attachments = emails.build_signup_confirmation_email(
        signup.volunteer,
        [signup],
        token="rawtoken-for-test-0123456789ab",
        event=signup.slot.event,
    )
    assert attachments == []
    assert "cid:qr-" not in html
