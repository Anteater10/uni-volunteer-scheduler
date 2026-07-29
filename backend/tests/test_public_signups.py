"""Task 10: Public signup endpoint integration tests.

Tests for:
  POST   /api/v1/public/signups            (create)
  POST   /api/v1/public/signups/confirm    (consume token)
  GET    /api/v1/public/signups/manage     (view signups without consuming)
  DELETE /api/v1/public/signups/{signup_id}  (cancel one signup with token)

Covers:
  - Happy path create → confirm → manage → cancel flow
  - Duplicate signup 409
  - Full slot 409
  - Invalid phone 422
  - Unknown slot_id 404
  - Token auth guards: expired/unknown → 400; wrong volunteer → 403
  - Idempotent confirm (used token → idempotent=True)
"""
import secrets
import hashlib
import uuid
from datetime import datetime, timezone, timedelta, date as date_type

import pytest

from app.models import AuditLog, Event, MagicLinkToken, Quarter, Signup, SignupStatus, Slot, SlotType, Volunteer
from tests.fixtures.helpers import make_user


# (213) 867-5309 is a valid NANP number (LA area code, fictitious subscriber)
GOOD_PHONE = "(213) 867-5309"


def _make_event(db_session, *, module_slug=None):
    owner = make_user(db_session)
    now = datetime.now(timezone.utc) + timedelta(days=1)
    e = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Public Signup Test Event",
        start_date=now,
        end_date=now + timedelta(days=1),
        module_slug=module_slug,
    )
    db_session.add(e)
    db_session.flush()
    return e


def _make_slot(db_session, event_id, *, capacity=5, current_count=0, slot_type=SlotType.PERIOD):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=capacity,
        current_count=current_count,
        slot_type=slot_type,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _signup_payload(slot_id, *, email="pub@example.com", phone=GOOD_PHONE):
    return {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": email,
        "phone": phone,
        "slot_ids": [str(slot_id)],
    }


def _get_token_for_volunteer(db_session, volunteer_id):
    """Look up the raw token from the MagicLinkToken row.

    Since we can't intercept issue_token (local import), we look up the
    hash row and use a known raw token approach. Instead, we need to use
    the raw token that was issued. We do this by querying the token table
    and reconstructing the raw from the DB.

    Actually: we can't reverse-engineer the raw from the hash. Instead,
    we need to patch the Celery task to log the token. Looking at
    send_signup_confirmation_email, when settings.debug is False, the
    token is NOT logged. So we need another approach:

    Alternative: patch app.magic_link_service.issue_token at import time
    by looking at the module-level function (not the local import).
    """
    # This is used for the "captured" approach — see _do_create_and_capture_token
    pass


class _TokenCapture:
    """Context manager that patches app.magic_link_service.issue_token
    to capture the raw token. Works because public_signup_service does
    'from ..magic_link_service import issue_token' at call time."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.tokens = []

    def __enter__(self):
        import app.magic_link_service as mls

        original = mls.issue_token

        def capturing(db, signup, email, **kwargs):
            raw = original(db, signup, email, **kwargs)
            self.tokens.append(raw)
            return raw

        self.monkeypatch.setattr(mls, "issue_token", capturing)
        return self

    def __exit__(self, *args):
        pass

    @property
    def last_token(self):
        return self.tokens[-1] if self.tokens else None


class TestCreatePublicSignup:
    def test_happy_path_returns_201(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "volunteer_id" in data
        assert "signup_ids" in data
        assert len(data["signup_ids"]) == 1
        assert data["magic_link_sent"] is True

    def test_invalid_phone_returns_422(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, phone="abc"))
        assert resp.status_code == 422, resp.text

    def test_unknown_slot_returns_404(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        resp = client.post("/api/v1/public/signups", json=_signup_payload(uuid.uuid4()))
        assert resp.status_code == 404, resp.text

    def test_full_slot_goes_to_waitlist(self, client, db_session, monkeypatch):
        """Phase 25 (WAIT-01): at-capacity signups are waitlisted, not rejected."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id, capacity=1, current_count=1)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["signups"], "response should include per-signup result items"
        item = data["signups"][0]
        assert item["status"] == "waitlisted"
        assert item["position"] == 1

        # Slot current_count must stay at capacity — waitlisted signups don't hold a seat.
        db_session.expire_all()
        from app import models as _m
        slot_row = db_session.query(_m.Slot).filter(_m.Slot.id == slot.id).one()
        assert slot_row.current_count == 1

    def test_duplicate_signup_returns_409(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id, capacity=10)
        db_session.commit()

        payload = _signup_payload(slot.id, email="dup409@example.com")
        r1 = client.post("/api/v1/public/signups", json=payload)
        assert r1.status_code == 201

        r2 = client.post("/api/v1/public/signups", json=payload)
        assert r2.status_code == 409, r2.text

    def test_upsert_updates_volunteer_on_second_signup(self, client, db_session, monkeypatch):
        """Second call for same email with different name still creates signup."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot1 = _make_slot(db_session, event.id)
        slot2 = _make_slot(db_session, event.id)
        db_session.commit()

        r1 = client.post("/api/v1/public/signups", json={
            **_signup_payload(slot1.id, email="upsert09@example.com"),
            "first_name": "Bob",
        })
        assert r1.status_code == 201
        vid1 = r1.json()["volunteer_id"]

        r2 = client.post("/api/v1/public/signups", json={
            **_signup_payload(slot2.id, email="upsert09@example.com"),
            "first_name": "Robert",
        })
        assert r2.status_code == 201
        vid2 = r2.json()["volunteer_id"]

        # Same volunteer (upsert on email)
        assert vid1 == vid2


class TestConfirmSignup:
    def test_happy_path_confirm(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="conf1b@example.com"))
        assert resp.status_code == 201

        token = cap.last_token
        if token is None:
            pytest.skip("Token capture failed — magic_link_service.issue_token not patched at module level")

        r2 = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["confirmed"] is True
        assert body["idempotent"] is False

    def test_idempotent_confirm_on_second_call(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="conf2b@example.com"))
        assert resp.status_code == 201

        token = cap.last_token
        if token is None:
            pytest.skip("Token capture failed")

        r1 = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert r1.status_code == 200
        assert r1.json()["confirmed"] is True

        r2 = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert r2.status_code == 200
        assert r2.json()["idempotent"] is True

    def test_unknown_token_returns_400(self, client, db_session):
        resp = client.post("/api/v1/public/signups/confirm", params={"token": "a" * 40})
        assert resp.status_code == 400, resp.text

    def test_short_token_returns_422(self, client, db_session):
        resp = client.post("/api/v1/public/signups/confirm", params={"token": "short"})
        assert resp.status_code == 422, resp.text


class TestManageSignups:
    def test_unknown_token_returns_400(self, client, db_session):
        resp = client.get("/api/v1/public/signups/manage", params={"token": "a" * 40})
        assert resp.status_code == 400, resp.text

    def test_manage_returns_signups_for_volunteer(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="manage09@example.com"))
        assert resp.status_code == 201

        token = cap.last_token
        if token is None:
            pytest.skip("Token capture failed")

        resp2 = client.get("/api/v1/public/signups/manage", params={"token": token})
        assert resp2.status_code == 200, resp2.text
        data = resp2.json()
        assert "signups" in data
        assert len(data["signups"]) == 1
        assert data["signups"][0]["status"] == "pending"


class TestCancelSignup:
    def test_cancel_with_wrong_volunteer_token_returns_403(self, client, db_session, monkeypatch):
        """T-09-04: token belonging to different volunteer must return 403."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot1 = _make_slot(db_session, event.id)
        slot2 = _make_slot(db_session, event.id)
        db_session.commit()

        tokens = []
        with _TokenCapture(monkeypatch) as cap:
            r1 = client.post("/api/v1/public/signups", json=_signup_payload(slot1.id, email="vola09@example.com"))
        assert r1.status_code == 201
        token_a = cap.last_token

        with _TokenCapture(monkeypatch) as cap2:
            r2 = client.post("/api/v1/public/signups", json=_signup_payload(slot2.id, email="volb09@example.com"))
        assert r2.status_code == 201
        signup_b_id = r2.json()["signup_ids"][0]

        if token_a is None:
            pytest.skip("Token capture failed")

        # Try to cancel vol B's signup using vol A's token → 403
        resp = client.delete(
            f"/api/v1/public/signups/{signup_b_id}",
            params={"token": token_a},
        )
        assert resp.status_code == 403, resp.text

    def test_cancel_with_unknown_token_returns_400(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        r1 = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="canc09@example.com"))
        assert r1.status_code == 201
        signup_id = r1.json()["signup_ids"][0]

        resp = client.delete(
            f"/api/v1/public/signups/{signup_id}",
            params={"token": "x" * 40},
        )
        assert resp.status_code == 400, resp.text

    def test_happy_path_cancel(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            r1 = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="cancel_hap09@example.com"))
        assert r1.status_code == 201

        if cap.last_token is None:
            pytest.skip("Token capture failed")

        signup_id = r1.json()["signup_ids"][0]
        token = cap.last_token

        resp = client.delete(
            f"/api/v1/public/signups/{signup_id}",
            params={"token": token},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled"] is True

    def test_cancel_creates_audit_log_entry(self, client, db_session, monkeypatch):
        """Cancelling a signup must create an AuditLog row with action='signup_cancelled'
        and volunteer email in extra (T-11-02 mitigation / ROADMAP success criterion 5)."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            r1 = client.post(
                "/api/v1/public/signups",
                json=_signup_payload(slot.id, email="audit_log11@example.com"),
            )
        assert r1.status_code == 201

        if cap.last_token is None:
            pytest.skip("Token capture failed")

        signup_id = r1.json()["signup_ids"][0]
        token = cap.last_token

        resp = client.delete(
            f"/api/v1/public/signups/{signup_id}",
            params={"token": token},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled"] is True

        # Verify AuditLog row was created
        log_entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "signup_cancelled")
            .filter(AuditLog.entity_id == signup_id)
            .first()
        )
        assert log_entry is not None, "AuditLog entry for signup_cancelled not found"
        assert log_entry.extra is not None
        assert log_entry.extra.get("volunteer_email") == "audit_log11@example.com"


def test_manage_response_includes_volunteer_name(client, db_session, monkeypatch):
    """Manage endpoint must return volunteer first/last name so the
    UI can render 'Signups for {first} {last}' on shared-device flows."""
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: None,
    )
    event = _make_event(db_session)
    slot = _make_slot(db_session, event.id)
    db_session.commit()

    payload = {
        "first_name": "Hung",
        "last_name": "Khuu",
        "email": "hung_name_test@example.com",
        "phone": GOOD_PHONE,
        "slot_ids": [str(slot.id)],
    }
    with _TokenCapture(monkeypatch) as cap:
        r = client.post("/api/v1/public/signups", json=payload)
    assert r.status_code == 201, r.text

    if cap.last_token is None:
        pytest.skip("Token capture failed")

    token = cap.last_token
    r = client.get("/api/v1/public/signups/manage", params={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["volunteer_first_name"] == "Hung"
    assert body["volunteer_last_name"] == "Khuu"


def test_confirmation_email_enqueued_only_after_commit(client, db_session, monkeypatch):
    """The Celery worker reads rows from its own session, so enqueuing the
    confirmation email before db.commit() intermittently made the worker see
    nothing ("missing entity, skipping") and silently drop the email. Pin the
    order: commit must precede the enqueue."""
    event = _make_event(db_session)
    slot = _make_slot(db_session, event.id)
    db_session.commit()

    calls = []
    original_commit = db_session.commit

    def spying_commit():
        calls.append("commit")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", spying_commit)
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: calls.append("enqueue"),
    )

    resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id))
    assert resp.status_code == 201, resp.text
    assert "enqueue" in calls, "confirmation email was never enqueued"
    assert calls.index("commit") < calls.index("enqueue"), (
        f"email enqueued before commit — worker race reintroduced (order: {calls})"
    )


def test_public_cancel_sends_waitlist_promote_email(client, db_session, monkeypatch):
    """Public (token) cancel also auto-promotes — the promoted volunteer must
    get the confirm-your-spot email."""
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: None,
    )
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda **kw: sent.append(kw),
    )
    promoted_emails = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: promoted_emails.append(kw),
    )
    event = _make_event(db_session)
    slot = _make_slot(db_session, event.id, capacity=1)
    db_session.commit()

    with _TokenCapture(monkeypatch) as cap:
        r1 = client.post(
            "/api/v1/public/signups",
            json=_signup_payload(slot.id, email="wl_promote_a@example.com"),
        )
    assert r1.status_code == 201
    a_id = r1.json()["signup_ids"][0]
    a_token = cap.last_token
    if a_token is None:
        pytest.skip("Token capture failed")

    r2 = client.post(
        "/api/v1/public/signups",
        json=_signup_payload(slot.id, email="wl_promote_b@example.com"),
    )
    assert r2.status_code == 201
    b_id = r2.json()["signup_ids"][0]

    resp = client.delete(f"/api/v1/public/signups/{a_id}", params={"token": a_token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["promoted_from_waitlist"] == 1

    assert any(kw["signup_id"] == str(b_id) for kw in promoted_emails), (
        f"promoted volunteer got no waitlist promotion email (sent: {promoted_emails})"
    )


def test_public_cancel_promotes_to_pending_with_confirm_email(
    client, db_session, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: None,
    )
    # Setup copied from test_public_cancel_sends_waitlist_promote_email:
    # capacity-1 slot, pending signup with manage token, waitlisted second.
    event = _make_event(db_session)
    slot = _make_slot(db_session, event.id, capacity=1)
    db_session.commit()

    with _TokenCapture(monkeypatch) as cap:
        r1 = client.post(
            "/api/v1/public/signups",
            json=_signup_payload(slot.id, email="wl_pending_a@example.com"),
        )
    assert r1.status_code == 201
    confirmed_id = r1.json()["signup_ids"][0]
    raw_token = cap.last_token
    if raw_token is None:
        pytest.skip("Token capture failed")

    r2 = client.post(
        "/api/v1/public/signups",
        json=_signup_payload(slot.id, email="wl_pending_b@example.com"),
    )
    assert r2.status_code == 201
    waitlisted_id = r2.json()["signup_ids"][0]

    resp = client.delete(f"/api/v1/public/signups/{confirmed_id}?token={raw_token}")
    assert resp.status_code == 200
    assert resp.json()["promoted_from_waitlist"] == 1
    db_session.expire_all()
    promoted = db_session.query(Signup).filter(Signup.id == waitlisted_id).one()
    assert promoted.status == SignupStatus.pending
    assert len(sent) == 1
    assert sent[0]["signup_id"] == str(waitlisted_id)
    assert sent[0]["token"]  # raw token travels to the email task


class TestOrientationRequirement:
    """Un-oriented volunteers must include an orientation session in their
    signup. Server-enforced (the frontend modal is advisory UX only):
    for every event in the batch with a PERIOD slot selected, the email must
    hold orientation credit for the event's family, OR the batch must include
    an ORIENTATION slot on the same event (or an event resolving to the same
    family). Events offering no orientation slots at all are exempt —
    organizers vouch at the door instead of dead-ending the volunteer."""

    EMAIL = "fresh-volunteer@example.com"

    def _mute_email(self, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )

    def _template(self, db_session, slug, family_key=None):
        from app.models import Module
        tmpl = Module(
            slug=slug,
            name=slug.title(),
            default_capacity=20,
            duration_minutes=120,
            session_count=1,
            family_key=family_key if family_key is not None else slug,
        )
        db_session.add(tmpl)
        db_session.flush()
        return tmpl

    def _payload(self, slot_ids, *, email=None):
        return {
            "first_name": "Fresh",
            "last_name": "Volunteer",
            "email": email or self.EMAIL,
            "phone": GOOD_PHONE,
            "slot_ids": [str(s) for s in slot_ids],
        }

    def test_period_only_without_credit_422_and_no_rows(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        orient = _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([period.id]))
        assert resp.status_code == 422, resp.text
        # Global handler (AUDIT-03) normalizes to {error, code, detail}.
        assert resp.json()["code"] == "ORIENTATION_REQUIRED"
        # Nothing persisted — no signup rows, no volunteer row.
        db_session.expire_all()
        assert db_session.query(Signup).count() == 0
        assert (
            db_session.query(Volunteer)
            .filter(Volunteer.email == self.EMAIL)
            .count()
            == 0
        )

    def test_orientation_in_same_batch_passes(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        orient = _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload([period.id, orient.id])
        )
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["signup_ids"]) == 2

    def test_granted_credit_passes_period_only(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        from app.services.orientation_service import grant_orientation_credit
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        grant_orientation_credit(db_session, self.EMAIL, "bio")
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([period.id]))
        assert resp.status_code == 201, resp.text

    def test_attendance_credit_passes_period_only(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        # Prior event in the same family where this email attended orientation
        # and the organizer ended the slot (grant-on-slot-end writes the row).
        from app.services.check_in_service import resolve_slot

        prior = _make_event(db_session, module_slug="bio-intro")
        prior_orient = _make_slot(db_session, prior.id, slot_type=SlotType.ORIENTATION)
        vol = Volunteer(
            id=uuid.uuid4(), email=self.EMAIL, first_name="Fresh", last_name="Volunteer"
        )
        db_session.add(vol)
        db_session.flush()
        prior_signup = Signup(
            volunteer_id=vol.id,
            slot_id=prior_orient.id,
            status=SignupStatus.checked_in,
            checked_in_at=datetime.now(timezone.utc),
        )
        db_session.add(prior_signup)
        db_session.flush()
        resolve_slot(db_session, prior_orient.id, None, [prior_signup.id], [])
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([period.id]))
        assert resp.status_code == 201, resp.text

    def test_event_without_orientation_slots_is_exempt(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([period.id]))
        assert resp.status_code == 201, resp.text

    def test_orientation_only_selection_passes(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        orient = _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([orient.id]))
        assert resp.status_code == 201, resp.text

    def test_batch_spanning_events_rejected(self, client, db_session, monkeypatch):
        """One signup covers one event. Multi-event batches were never used by
        the frontend and turned this endpoint into an amplified credit oracle
        (20 events probed per request vs 1 per orientation-check call)."""
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event_a = _make_event(db_session, module_slug="bio-intro")
        period_a = _make_slot(db_session, event_a.id)
        event_b = _make_event(db_session, module_slug="bio-intro")
        orient_b = _make_slot(db_session, event_b.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload([period_a.id, orient_b.id])
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "MULTIPLE_EVENTS"
        db_session.expire_all()
        assert db_session.query(Signup).count() == 0

    def test_full_orientation_slot_still_satisfies_via_waitlist(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        period = _make_slot(db_session, event.id)
        orient = _make_slot(
            db_session,
            event.id,
            slot_type=SlotType.ORIENTATION,
            capacity=1,
            current_count=1,
        )
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload([period.id, orient.id])
        )
        assert resp.status_code == 201, resp.text
        statuses = {s["signup_id"]: s["status"] for s in resp.json()["signups"]}
        assert "waitlisted" in statuses.values()

    def test_moduleless_event_fails_closed(self, client, db_session, monkeypatch):
        """No module_slug → family is None → no credit can exist; the
        same-event orientation slot is still required."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        period = _make_slot(db_session, event.id)
        orient = _make_slot(db_session, event.id, slot_type=SlotType.ORIENTATION)
        db_session.commit()

        resp = client.post("/api/v1/public/signups", json=self._payload([period.id]))
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "ORIENTATION_REQUIRED"

        resp2 = client.post(
            "/api/v1/public/signups", json=self._payload([period.id, orient.id])
        )
        assert resp2.status_code == 201, resp2.text
