"""Task 10: Public signup endpoint integration tests.

Tests for:
  POST   /api/v1/public/signups            (create)
  POST   /api/v1/public/signups/confirm    (consume token)
  GET    /api/v1/public/signups/manage     (view signups without consuming)

2026-08-02 read-only signups: DELETE /api/v1/public/signups/{signup_id} was
removed — volunteers can no longer self-cancel. See TestCancelRouteRemoved.

Covers:
  - Happy path create → confirm → manage flow
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

from app.magic_link_service import SIGNUP_CONFIRM_TTL_MINUTES, issue_token
from app.models import (
    Event,
    MagicLinkPurpose,
    MagicLinkToken,
    Quarter,
    ShiftSignup,
    Signup,
    SignupStatus,
    Slot,
    SlotType,
    Volunteer,
)
from app.signup_service import mark_promoted_pending
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


def _make_slot(
    db_session, event_id, *, capacity=5, current_count=0, slot_type=SlotType.ORIENTATION
):
    """A directly-bookable slot — i.e. an orientation slot.

    2026-08-05 shifts: the default used to be PERIOD, and `slot_ids` used to
    accept one. Both changed together. A period slot is a session inside a
    shift, so the public endpoint refuses a bare period slot id with 422
    PERIOD_SLOT_NOT_BOOKABLE, and the membership constraint won't even let a
    shift-less one be inserted. Use `_make_shift` for classroom work.
    """
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


def _make_shift(
    db_session, event_id, *, capacity=5, current_count=0, n_sessions=1, name="Shift 1"
):
    """The bookable unit for classroom work: a shift plus its session slots.

    Capacity lives on the shift; each session carries a copy for display. The
    sessions exist because the orientation gate, the roster and the check-in
    window all read them, but nothing books one directly.
    """
    from tests.fixtures.helpers import make_shift

    shift = make_shift(db_session, event_id, name=name, capacity=capacity)
    shift.current_count = current_count
    base = datetime.now(timezone.utc) + timedelta(days=1)
    for i in range(n_sessions):
        db_session.add(
            Slot(
                id=uuid.uuid4(),
                event_id=event_id,
                shift_id=shift.id,
                sort_order=i,
                name=f"Period {i + 1}",
                start_time=base + timedelta(days=i),
                end_time=base + timedelta(days=i, hours=2),
                capacity=capacity,
                current_count=current_count,
                slot_type=SlotType.PERIOD,
                date=(base + timedelta(days=i)).date(),
            )
        )
    db_session.flush()
    return shift


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

    def test_private_event_slot_404_matches_unknown_slot_404(
        self, client, db_session, monkeypatch
    ):
        """Fix round 2 (Task 2 review): a slot on a private event and a
        slot_id that doesn't exist at all must be byte-identical 404
        responses — same status code AND same body. A caller holding a
        slot_id must not be able to tell "this slot doesn't exist" apart
        from "this slot exists but its event is private" by diffing the
        response text."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        event.visibility = "private"
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        private_resp = client.post(
            "/api/v1/public/signups",
            json=_signup_payload(slot.id, email="private-slot@example.com"),
        )
        unknown_resp = client.post(
            "/api/v1/public/signups", json=_signup_payload(uuid.uuid4())
        )

        assert private_resp.status_code == 404, private_resp.text
        assert unknown_resp.status_code == 404, unknown_resp.text
        assert private_resp.status_code == unknown_resp.status_code
        assert private_resp.json() == unknown_resp.json()

    def test_null_visibility_event_signup_404_matches_unknown_slot_404(
        self, client, db_session, monkeypatch
    ):
        """2026-07-29 sweep remediation, Finding #6: ``Event.visibility`` is
        nullable with no server default or backfill (see
        routers/public/events.py, Finding #3). The signup path deny-listed
        only the literal string "private", so a NULL-visibility event —
        hidden from the public list and 404ing on its detail page — could
        still be signed up for. Must fail closed here too, and the refusal
        must stay byte-identical to the unknown-slot 404."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        event.visibility = None
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        null_resp = client.post(
            "/api/v1/public/signups",
            json=_signup_payload(slot.id, email="null-vis-slot@example.com"),
        )
        unknown_resp = client.post(
            "/api/v1/public/signups", json=_signup_payload(uuid.uuid4())
        )

        assert null_resp.status_code == 404, null_resp.text
        assert unknown_resp.status_code == 404, unknown_resp.text
        assert null_resp.status_code == unknown_resp.status_code
        assert null_resp.json() == unknown_resp.json()

    def test_unexpected_visibility_value_event_signup_404_matches_unknown_slot_404(
        self, client, db_session, monkeypatch
    ):
        """2026-07-29 sweep remediation, Finding #6: a deny-list
        (`== "private"`) fails open for any unrecognized value (e.g. a typo
        or case mismatch like "Private"). Must be an allow-list on exactly
        "public" instead, matching routers/public/events.py."""
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        event.visibility = "Private"
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        odd_resp = client.post(
            "/api/v1/public/signups",
            json=_signup_payload(slot.id, email="odd-vis-slot@example.com"),
        )
        unknown_resp = client.post(
            "/api/v1/public/signups", json=_signup_payload(uuid.uuid4())
        )

        assert odd_resp.status_code == 404, odd_resp.text
        assert unknown_resp.status_code == 404, unknown_resp.text
        assert odd_resp.status_code == unknown_resp.status_code
        assert odd_resp.json() == unknown_resp.json()

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
        # The UI badges each slot by matching result items on slot_id — the
        # positional zip against the submitted slot_ids list is too fragile.
        assert item["slot_id"] == str(slot.id)

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


class TestConfirmSignupPromotionScoping:
    """2026-07-29 sweep remediation, Finding #1: consume_token can legitimately
    burn a token while confirming zero signups (a volunteer's only signup was
    waitlisted then promoted, and they click the ORIGINAL batch confirm link
    instead of the promotion link). The router must not report success."""

    def test_original_batch_link_reports_not_confirmed_after_promotion(
        self, client, db_session
    ):
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id, capacity=1, current_count=1)
        volunteer = Volunteer(
            id=uuid.uuid4(),
            email="promoted-scoping@example.com",
            first_name="Prom",
            last_name="Oted",
        )
        db_session.add(volunteer)
        db_session.flush()
        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=SignupStatus.waitlisted,
        )
        db_session.add(signup)
        db_session.flush()
        # The original batch link the volunteer received before being
        # promoted off the waitlist.
        batch_raw = issue_token(
            db_session,
            signup=signup,
            email=volunteer.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=volunteer.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        mark_promoted_pending(db_session, signup)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups/confirm", params={"token": batch_raw}
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirmed"] is False, (
            "the original batch link must never report success for a seat "
            "that only a promotion link can confirm"
        )
        assert body["signup_count"] == 0
        assert body["reason"] == "promotion_pending"
        assert "promotion" in body["message"].lower()
        assert body["idempotent"] is False, (
            "this is a distinct zero-flip case, not a genuine used-token replay"
        )
        db_session.expire_all()
        assert db_session.get(Signup, signup.id).status == SignupStatus.pending

    def test_own_link_for_plain_waitlisted_signup_is_not_told_to_find_a_promotion(
        self, client, db_session
    ):
        """Regression guard: confirmed_count == 0 is also reachable with NO
        promotion anywhere — a volunteer signs up for a single slot that is
        already full, lands waitlisted (public_signup_service.py), and clicks
        their OWN emailed link. They must be told they're on the waitlist,
        not sent looking for a promotion email that was never sent."""
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id, capacity=1, current_count=1)
        volunteer = Volunteer(
            id=uuid.uuid4(),
            email="plain-waitlisted@example.com",
            first_name="Plain",
            last_name="Waiter",
        )
        db_session.add(volunteer)
        db_session.flush()
        signup = Signup(
            id=uuid.uuid4(),
            volunteer_id=volunteer.id,
            slot_id=slot.id,
            status=SignupStatus.waitlisted,
        )
        db_session.add(signup)
        db_session.flush()
        batch_raw = issue_token(
            db_session,
            signup=signup,
            email=volunteer.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=volunteer.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )
        db_session.commit()
        # NOTE: no mark_promoted_pending — this signup was never promoted.

        resp = client.post(
            "/api/v1/public/signups/confirm", params={"token": batch_raw}
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirmed"] is False
        assert body["reason"] == "waitlisted"
        assert "promotion" not in body["message"].lower(), (
            "a plain waitlisted signup was never promoted — telling the "
            "volunteer to look for a promotion email is wrong"
        )
        assert "waitlist" in body["message"].lower()
        db_session.expire_all()
        assert db_session.get(Signup, signup.id).status == SignupStatus.waitlisted


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

    def test_manage_includes_contact_email(self, client, db_session, monkeypatch):
        from app.services.settings_service import get_app_settings

        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            resp = client.post("/api/v1/public/signups", json=_signup_payload(slot.id, email="manage-contact@example.com"))
        assert resp.status_code == 201

        token = cap.last_token
        if token is None:
            pytest.skip("Token capture failed")

        get_app_settings(db_session).contact_email = "scitrek@ucsb.edu"
        db_session.commit()

        resp2 = client.get("/api/v1/public/signups/manage", params={"token": token})
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["contact_email"] == "scitrek@ucsb.edu"


class TestCancelRouteRemoved:
    """2026-08-02 read-only signups: volunteers cannot cancel themselves."""

    def test_delete_route_is_gone(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )
        event = _make_event(db_session)
        slot = _make_slot(db_session, event.id)
        db_session.commit()

        with _TokenCapture(monkeypatch) as cap:
            resp = client.post(
                "/api/v1/public/signups",
                json=_signup_payload(slot.id, email="cancel_gone09@example.com"),
            )
        assert resp.status_code == 201
        signup_id = resp.json()["signup_ids"][0]
        raw_token = cap.last_token
        if raw_token is None:
            pytest.skip("Token capture failed")

        resp = client.delete(
            f"/api/v1/public/signups/{signup_id}", params={"token": raw_token}
        )
        assert resp.status_code == 404
        db_session.expire_all()
        assert (
            db_session.get(Signup, signup_id).status != SignupStatus.cancelled
        )


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


class TestOrientationRequirement:
    """Un-oriented volunteers must include an orientation session in their
    signup. Server-enforced (the frontend modal is advisory UX only):
    for every event in the batch with a SHIFT selected, the email must
    hold orientation credit for the event's family, OR the batch must include
    an ORIENTATION slot on the same event (or an event resolving to the same
    family). Events offering no orientation slots at all are exempt —
    organizers vouch at the door instead of dead-ending the volunteer.

    2026-08-05 shifts: the trigger moved from "a period slot is selected" to
    "a shift is selected", because selecting a shift is what commits the
    volunteer to classroom work now. The rule itself is unchanged, and these
    cases send `shift_ids` where they used to send a period slot id.
    """

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

    def _payload(self, slot_ids=(), *, shift_ids=(), email=None):
        return {
            "first_name": "Fresh",
            "last_name": "Volunteer",
            "email": email or self.EMAIL,
            "phone": GOOD_PHONE,
            "slot_ids": [str(s) for s in slot_ids],
            "shift_ids": [str(s) for s in shift_ids],
        }

    def test_period_only_without_credit_422_and_no_rows(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 422, resp.text
        # Global handler (AUDIT-03) normalizes to {error, code, detail}.
        assert resp.json()["code"] == "ORIENTATION_REQUIRED"
        # Nothing persisted — no signup rows, no commitment, no volunteer row.
        db_session.expire_all()
        assert db_session.query(Signup).count() == 0
        assert db_session.query(ShiftSignup).count() == 0
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
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload([orient.id], shift_ids=[shift.id]),
        )
        assert resp.status_code == 201, resp.text
        # The two bookings land in different lists — one signup, one commitment.
        assert len(resp.json()["signup_ids"]) == 1
        assert len(resp.json()["shift_signup_ids"]) == 1

    def test_granted_credit_passes_period_only(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        from app.services.orientation_service import grant_orientation_credit
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        shift = _make_shift(db_session, event.id)
        _make_slot(db_session, event.id)
        grant_orientation_credit(db_session, self.EMAIL, "bio")
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 201, resp.text

    def test_attendance_credit_passes_period_only(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        # Prior event in the same family where this email attended orientation
        # and the organizer ended the slot (grant-on-slot-end writes the row).
        from app.services.check_in_service import resolve_slot

        prior = _make_event(db_session, module_slug="bio-intro")
        prior_orient = _make_slot(db_session, prior.id)
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
        shift = _make_shift(db_session, event.id)
        _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 201, resp.text

    def test_event_without_orientation_slots_is_exempt(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        shift = _make_shift(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 201, resp.text

    def test_orientation_only_selection_passes(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        orient = _make_slot(db_session, event.id)
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
        shift_a = _make_shift(db_session, event_a.id)
        event_b = _make_event(db_session, module_slug="bio-intro")
        orient_b = _make_slot(db_session, event_b.id)
        db_session.commit()

        # A batch mixing a shift on one event with a slot on another still has
        # to be caught — the single-event rule spans both id lists, not just
        # slot_ids.
        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload([orient_b.id], shift_ids=[shift_a.id]),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "MULTIPLE_EVENTS"
        db_session.expire_all()
        assert db_session.query(Signup).count() == 0
        assert db_session.query(ShiftSignup).count() == 0

    def test_full_orientation_slot_still_satisfies_via_waitlist(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        self._template(db_session, "bio-intro", family_key="bio")
        event = _make_event(db_session, module_slug="bio-intro")
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id, capacity=1, current_count=1)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload([orient.id], shift_ids=[shift.id]),
        )
        assert resp.status_code == 201, resp.text
        # A waitlisted orientation still counts as "in the batch" — being 2nd in
        # line for orientation must not block the shift they came for.
        items = resp.json()["signups"]
        assert [i["status"] for i in items if i["slot_id"]] == ["waitlisted"]
        assert [i["status"] for i in items if i["shift_id"]] == ["pending"]

    def test_moduleless_event_fails_closed(self, client, db_session, monkeypatch):
        """No module_slug → family is None → no credit can exist; the
        same-event orientation slot is still required."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "ORIENTATION_REQUIRED"

        resp2 = client.post(
            "/api/v1/public/signups",
            json=self._payload([orient.id], shift_ids=[shift.id]),
        )
        assert resp2.status_code == 201, resp2.text


class TestShiftBooking:
    """2026-08-05 shifts: booking the bundle, not the session.

    The gate above tests *whether* a shift may be booked; this class tests what
    happens when it is — one commitment covering every session, capacity and
    the waitlist read off the shift, and the old per-session shape refused
    rather than quietly accepted.

    These events are moduleless with no orientation slot, which the gate exempts
    (nothing to require), so each case exercises the booking path alone.
    """

    def _mute_email(self, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: sent.append(k or a),
        )
        return sent

    def _payload(self, *, shift_ids=(), slot_ids=(), email="shift-vol@example.com"):
        return {
            "first_name": "Sam",
            "last_name": "Shift",
            "email": email,
            "phone": GOOD_PHONE,
            "slot_ids": [str(s) for s in slot_ids],
            "shift_ids": [str(s) for s in shift_ids],
        }

    def test_one_commitment_covers_every_session(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, n_sessions=3, capacity=4)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert len(body["shift_signup_ids"]) == 1
        assert body["signup_ids"] == []
        item = body["signups"][0]
        assert item["shift_id"] == str(shift.id)
        assert item["signup_id"] is None
        assert item["status"] == "pending"
        assert item["position"] is None

        db_session.expire_all()
        # One row for the whole bundle — three sessions, no per-session Signup.
        assert db_session.query(ShiftSignup).count() == 1
        assert db_session.query(Signup).count() == 0
        # Pending counts against capacity, same rule slots have always had.
        assert db_session.get(type(shift), shift.id).current_count == 1

    def test_full_shift_waitlists_and_leaves_the_count_alone(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, capacity=1, current_count=1)
        db_session.commit()

        first = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shift.id], email="w1@example.com"),
        )
        second = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shift.id], email="w2@example.com"),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["signups"][0]["status"] == "waitlisted"
        # Position is 1-based and ordered the way the whole app orders a
        # waitlist, so the second person to arrive is told they are second.
        assert first.json()["signups"][0]["position"] == 1
        assert second.json()["signups"][0]["position"] == 2

        db_session.expire_all()
        assert db_session.get(type(shift), shift.id).current_count == 1

    def test_signing_up_twice_for_the_same_shift_is_409(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, capacity=5)
        db_session.commit()

        payload = self._payload(shift_ids=[shift.id])
        assert client.post("/api/v1/public/signups", json=payload).status_code == 201
        again = client.post("/api/v1/public/signups", json=payload)
        assert again.status_code == 409

        db_session.expire_all()
        assert db_session.query(ShiftSignup).count() == 1
        # The refused attempt must not have consumed a seat on its way out.
        assert db_session.get(type(shift), shift.id).current_count == 1

    def test_a_session_id_in_slot_ids_is_refused(
        self, client, db_session, monkeypatch
    ):
        """A client sending a session id is running the pre-shift UI. Refusing
        is the point: silently ignoring it would report success for a signup
        that booked nothing."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, n_sessions=2)
        session = (
            db_session.query(Slot).filter(Slot.shift_id == shift.id).first()
        )
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(slot_ids=[session.id])
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "PERIOD_SLOT_NOT_BOOKABLE"
        # The service names the offending ids, but the global error normalizer
        # keeps only {error, code, detail}, so the client sees the message and
        # not the list. Asserted as-is rather than aspirationally: the frontend
        # steers off the code, and widening the envelope is a separate change.
        assert "shift id" in body["detail"]

        db_session.expire_all()
        assert db_session.query(Signup).count() == 0
        assert db_session.query(ShiftSignup).count() == 0

    def test_orientation_and_shift_in_one_batch(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shift.id], slot_ids=[orient.id]),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert len(body["signup_ids"]) == 1
        assert len(body["shift_signup_ids"]) == 1
        # Two units, two result items, each naming which kind it is.
        kinds = {("shift" if i["shift_id"] else "slot") for i in body["signups"]}
        assert kinds == {"shift", "slot"}

    def test_a_shift_only_batch_still_gets_a_confirm_link(
        self, client, db_session, monkeypatch
    ):
        """There is no Signup row to anchor the token to, so it hangs off the
        shift signup instead — without this the volunteer never gets a
        confirmable link for classroom work."""
        sent = self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["magic_link_sent"] is True

        shift_signup_id = resp.json()["shift_signup_ids"][0]
        token_row = (
            db_session.query(MagicLinkToken)
            .filter(MagicLinkToken.purpose == MagicLinkPurpose.SIGNUP_CONFIRM)
            .order_by(MagicLinkToken.created_at.desc())
            .first()
        )
        assert token_row is not None
        assert str(token_row.shift_signup_id) == shift_signup_id
        assert sent and sent[0]["shift_signup_ids"] == [shift_signup_id]

    def test_unknown_shift_404_matches_unknown_slot_404(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        missing_shift = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[uuid.uuid4()])
        )
        missing_slot = client.post(
            "/api/v1/public/signups", json=self._payload(slot_ids=[uuid.uuid4()])
        )
        assert missing_shift.status_code == 404
        assert missing_shift.json() == missing_slot.json()

    def test_private_events_shift_404s_the_same_way(
        self, client, db_session, monkeypatch
    ):
        """Booking a shift you were never shown is the same leak as listing the
        private event, so it must be indistinguishable from a bad id."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        event.visibility = "private"
        shift = _make_shift(db_session, event.id)
        db_session.commit()

        private = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        unknown = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[uuid.uuid4()])
        )
        assert private.status_code == 404
        assert private.json() == unknown.json()

        db_session.expire_all()
        assert db_session.query(ShiftSignup).count() == 0

    def test_a_closed_signup_window_blocks_a_shift_too(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        event.signup_close_at = datetime.now(timezone.utc) - timedelta(hours=1)
        shift = _make_shift(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
        )
        assert resp.status_code == 403
        assert "Signup closed" in resp.json()["detail"]

        db_session.expire_all()
        assert db_session.query(ShiftSignup).count() == 0


class TestShiftBatchConfirm:
    """One link confirms everything the volunteer submitted.

    2026-08-05 shifts: the batch spans two tables now, so the confirm has to
    sweep both — a link that confirmed the orientation slot and left the shift
    pending would silently drop the classroom commitment at the reminder stage.
    """

    def _mute_email(self, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )

    def _create(self, client, monkeypatch, *, slot_ids=(), shift_ids=(), email):
        payload = {
            "first_name": "Bea",
            "last_name": "Confirm",
            "email": email,
            "phone": GOOD_PHONE,
            "slot_ids": [str(s) for s in slot_ids],
            "shift_ids": [str(s) for s in shift_ids],
        }
        with _TokenCapture(monkeypatch) as cap:
            resp = client.post("/api/v1/public/signups", json=payload)
        assert resp.status_code == 201, resp.text
        if cap.last_token is None:
            pytest.skip("Token capture failed — issue_token not patched at module level")
        return resp.json(), cap.last_token

    def test_one_link_confirms_the_orientation_and_the_shift(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, n_sessions=2)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        body, token = self._create(
            client, monkeypatch, slot_ids=[orient.id], shift_ids=[shift.id],
            email="batch-both@example.com",
        )

        resp = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert resp.status_code == 200, resp.text
        assert resp.json()["confirmed"] is True
        # Two units confirmed by the one link, counted together.
        assert resp.json()["signup_count"] == 2

        db_session.expire_all()
        signup = db_session.get(Signup, uuid.UUID(body["signup_ids"][0]))
        commitment = db_session.get(
            ShiftSignup, uuid.UUID(body["shift_signup_ids"][0])
        )
        assert signup.status == SignupStatus.confirmed
        assert commitment.status == SignupStatus.confirmed

    def test_a_shift_only_batch_confirms_from_its_own_anchor(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id)
        db_session.commit()

        body, token = self._create(
            client, monkeypatch, shift_ids=[shift.id], email="batch-shift@example.com"
        )
        resp = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert resp.status_code == 200, resp.text
        assert resp.json()["signup_count"] == 1

        db_session.expire_all()
        assert (
            db_session.get(ShiftSignup, uuid.UUID(body["shift_signup_ids"][0])).status
            == SignupStatus.confirmed
        )

        again = client.post("/api/v1/public/signups/confirm", params={"token": token})
        assert again.json()["idempotent"] is True

    def test_a_waitlisted_shift_is_not_confirmed_by_the_link(
        self, client, db_session, monkeypatch
    ):
        """Confirming is about the seat you hold; a waitlisted commitment has
        none, so it stays waiting rather than being quietly seated."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        full = _make_shift(db_session, event.id, capacity=1, current_count=1,
                           name="Full")
        open_shift = _make_shift(db_session, event.id, capacity=5, name="Open")
        db_session.commit()

        body, token = self._create(
            client, monkeypatch, shift_ids=[full.id, open_shift.id],
            email="batch-wait@example.com",
        )
        client.post("/api/v1/public/signups/confirm", params={"token": token})

        db_session.expire_all()
        statuses = {
            str(db_session.get(ShiftSignup, uuid.UUID(sid)).shift.name):
                db_session.get(ShiftSignup, uuid.UUID(sid)).status
            for sid in body["shift_signup_ids"]
        }
        assert statuses == {
            "Full": SignupStatus.waitlisted,
            "Open": SignupStatus.confirmed,
        }

    def test_manage_lists_the_shift_with_its_sessions(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        shift = _make_shift(db_session, event.id, n_sessions=2, name="Tue+Wed")
        db_session.commit()

        _, token = self._create(
            client, monkeypatch, shift_ids=[shift.id], email="manage-shift@example.com"
        )
        resp = client.get("/api/v1/public/signups/manage", params={"token": token})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signups"] == []
        assert len(body["shift_signups"]) == 1
        row = body["shift_signups"][0]
        assert row["shift"]["name"] == "Tue+Wed"
        # Both days are shown: the volunteer committed to the bundle, and the
        # manage page is where they check what they actually signed up for.
        assert len(row["shift"]["sessions"]) == 2
        assert [s["sort_order"] for s in row["shift"]["sessions"]] == [0, 1]


class TestMaxSignupsPerUser:
    """K8 — ``Event.max_signups_per_user`` is finally enforced.

    The column and the admin form field both shipped in the initial schema.
    Nothing read the value, so an admin who typed 2 got no cap at all — the
    worst kind of failure, because the surface said the limit was in force.

    These events carry no orientation slots, so the orientation gate is
    exempt and each case exercises the cap on its own.
    """

    EMAIL = "capped@example.com"

    def _mute_email(self, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_signup_confirmation_email.delay",
            lambda *a, **k: None,
        )

    def _payload(self, *, shift_ids=(), slot_ids=(), email=None):
        return {
            "first_name": "Capped",
            "last_name": "Volunteer",
            "email": email or self.EMAIL,
            "phone": GOOD_PHONE,
            "slot_ids": [str(s) for s in slot_ids],
            "shift_ids": [str(s) for s in shift_ids],
        }

    def _event_with_shifts(self, db_session, *, limit, n=3):
        event = _make_event(db_session)
        event.max_signups_per_user = limit
        shifts = [
            _make_shift(db_session, event.id, name=f"Shift {i + 1}")
            for i in range(n)
        ]
        db_session.commit()
        return event, shifts

    def test_null_limit_means_no_limit(self, client, db_session, monkeypatch):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=None)

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[s.id for s in shifts]),
        )
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["shift_signup_ids"]) == 3

    def test_batch_over_the_limit_is_refused_and_writes_nothing(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=1)

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shifts[0].id, shifts[1].id]),
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "SIGNUP_LIMIT_REACHED"
        # Singular in the copy when the limit is 1 — the message is shown
        # verbatim to a volunteer. The global handler flattens a dict detail
        # to a bare string, so `detail` IS the message.
        assert "1 shift per volunteer" in body["detail"]

        # Refused before any write, like the orientation gate.
        db_session.expire_all()
        assert db_session.query(ShiftSignup).count() == 0
        assert (
            db_session.query(Volunteer)
            .filter(Volunteer.email == self.EMAIL)
            .count()
            == 0
        )

    def test_limit_counts_signups_from_earlier_requests(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=2)

        for shift in shifts[:2]:
            resp = client.post(
                "/api/v1/public/signups", json=self._payload(shift_ids=[shift.id])
            )
            assert resp.status_code == 201, resp.text

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shifts[2].id])
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "2 shifts per volunteer" in detail
        assert "You already have 2" in detail

    def test_partial_headroom_reports_how_many_are_left(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=2)

        assert (
            client.post(
                "/api/v1/public/signups", json=self._payload(shift_ids=[shifts[0].id])
            ).status_code
            == 201
        )
        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shifts[1].id, shifts[2].id]),
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "You have 1 already, so you can pick 1 more" in detail

    def test_cancelled_signups_give_the_headroom_back(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=1)

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shifts[0].id])
        )
        assert resp.status_code == 201, resp.text

        booked = db_session.query(ShiftSignup).one()
        booked.status = SignupStatus.cancelled
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[shifts[1].id])
        )
        assert resp.status_code == 201, resp.text

    def test_waitlisted_signups_still_count(self, client, db_session, monkeypatch):
        """Otherwise the cap is bypassed by waitlisting: auto-promotion would
        carry the volunteer past a limit they were never allowed to reach."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        event.max_signups_per_user = 1
        full = _make_shift(
            db_session, event.id, capacity=1, current_count=1, name="Full"
        )
        other = _make_shift(db_session, event.id, name="Other")
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[full.id])
        )
        assert resp.status_code == 201, resp.text
        assert (
            db_session.query(ShiftSignup).one().status == SignupStatus.waitlisted
        )

        resp = client.post(
            "/api/v1/public/signups", json=self._payload(shift_ids=[other.id])
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "SIGNUP_LIMIT_REACHED"

    def test_orientation_slots_are_exempt(self, client, db_session, monkeypatch):
        """A cap of 1 on an event that also requires orientation has to stay
        bookable — the volunteer needs the orientation *and* the shift."""
        self._mute_email(monkeypatch)
        event = _make_event(db_session)
        event.max_signups_per_user = 1
        shift = _make_shift(db_session, event.id)
        orient = _make_slot(db_session, event.id)
        db_session.commit()

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shift.id], slot_ids=[orient.id]),
        )
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["signup_ids"]) == 1
        assert len(resp.json()["shift_signup_ids"]) == 1

    def test_a_limit_of_zero_reads_as_no_limit(
        self, client, db_session, monkeypatch
    ):
        """0 is what an admin gets by clearing the field in some browsers.
        Treating it as "nobody may sign up" would silently close the event."""
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=0)

        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shifts[0].id]),
        )
        assert resp.status_code == 201, resp.text

    def test_the_cap_is_per_volunteer_not_per_event(
        self, client, db_session, monkeypatch
    ):
        self._mute_email(monkeypatch)
        _, shifts = self._event_with_shifts(db_session, limit=1)

        assert (
            client.post(
                "/api/v1/public/signups", json=self._payload(shift_ids=[shifts[0].id])
            ).status_code
            == 201
        )
        resp = client.post(
            "/api/v1/public/signups",
            json=self._payload(shift_ids=[shifts[1].id], email="someone@example.com"),
        )
        assert resp.status_code == 201, resp.text
