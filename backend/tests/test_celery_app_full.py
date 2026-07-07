"""Full coverage for app.celery_app — email send paths, dispatch, all tasks."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app import celery_app as celery_mod
from app import models
from app.celery_app import (
    _check_daily_send_limit,
    _send_email,
    _send_via_sendgrid,
    _send_via_smtp,
    expire_pending_signups,
    send_broadcast_email,
    send_email_notification,
    send_signup_confirmation_email,
    weekly_digest,
)
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make Celery tasks reuse the test db_session."""

    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: _Proxy(db_session))


# ---------------------------------------------------------------------------
# _check_daily_send_limit — warning at 80%
# ---------------------------------------------------------------------------


def _seed_n_sent_notifications(db_session, n, *, kind_prefix="k"):
    """Seed N SentNotification rows pinned to a real signup (FK requires it)."""
    s = _seed_confirmed_signup(db_session, email_tag=kind_prefix)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(n):
        db_session.add(models.SentNotification(
            signup_id=s.id, kind=f"{kind_prefix}{i}",
            sent_at=today_start + timedelta(minutes=i),
        ))
    db_session.flush()


def test_daily_send_limit_warns_at_80_percent(db_session, monkeypatch, caplog):
    """At 80%+ usage but < 100%, function returns True and logs warning."""
    monkeypatch.setattr(celery_mod.settings, "resend_daily_limit", 10)
    _seed_n_sent_notifications(db_session, 8, kind_prefix="warn")

    import logging
    with caplog.at_level(logging.WARNING, logger="app.celery_app"):
        ok = _check_daily_send_limit(db_session)
    assert ok is True
    assert any("%" in r.message for r in caplog.records)


def test_daily_send_limit_blocks_at_limit(db_session, monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "resend_daily_limit", 5)
    _seed_n_sent_notifications(db_session, 5, kind_prefix="lim")
    assert _check_daily_send_limit(db_session) is False


# ---------------------------------------------------------------------------
# _send_via_smtp
# ---------------------------------------------------------------------------


def test_send_via_smtp_skips_when_no_from_address(monkeypatch, caplog):
    monkeypatch.setattr(celery_mod.settings, "email_from_address", None)
    import logging
    with caplog.at_level(logging.WARNING, logger="app.celery_app"):
        _send_via_smtp("to@x.com", "s", "b")
    assert any("email_from_address" in r.message for r in caplog.records)


def test_send_via_smtp_sends_with_tls_and_auth(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    monkeypatch.setattr(celery_mod.settings, "smtp_host", "smtp.example")
    monkeypatch.setattr(celery_mod.settings, "smtp_port", 587)
    monkeypatch.setattr(celery_mod.settings, "smtp_use_tls", True)
    monkeypatch.setattr(celery_mod.settings, "smtp_username", "u")
    monkeypatch.setattr(celery_mod.settings, "smtp_password", "p")

    smtp_instance = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp_instance
    smtp_cm.__exit__.return_value = False
    with patch.object(celery_mod.smtplib, "SMTP", return_value=smtp_cm) as smtp_cls:
        _send_via_smtp("to@x.com", "subject", "body", html_body="<b>hi</b>")
    smtp_cls.assert_called_once_with("smtp.example", 587, timeout=10)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("u", "p")
    smtp_instance.send_message.assert_called_once()


def test_send_via_smtp_no_tls_no_auth(monkeypatch):
    """Local Mailpit path — no TLS, no auth."""
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    monkeypatch.setattr(celery_mod.settings, "smtp_host", "mailpit")
    monkeypatch.setattr(celery_mod.settings, "smtp_port", 1025)
    monkeypatch.setattr(celery_mod.settings, "smtp_use_tls", False)
    monkeypatch.setattr(celery_mod.settings, "smtp_username", None)
    monkeypatch.setattr(celery_mod.settings, "smtp_password", None)

    smtp_instance = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp_instance
    smtp_cm.__exit__.return_value = False
    with patch.object(celery_mod.smtplib, "SMTP", return_value=smtp_cm):
        _send_via_smtp("to@x.com", "s", "b")
    smtp_instance.starttls.assert_not_called()
    smtp_instance.login.assert_not_called()
    smtp_instance.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# _send_via_sendgrid
# ---------------------------------------------------------------------------


def test_send_via_sendgrid_skips_when_no_key(monkeypatch, caplog):
    monkeypatch.setattr(celery_mod.settings, "sendgrid_api_key", None)
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    import logging
    with caplog.at_level(logging.WARNING, logger="app.celery_app"):
        _send_via_sendgrid("to@x.com", "s", "b")
    assert any("sendgrid_api_key" in r.message for r in caplog.records)


def test_send_via_sendgrid_skips_when_no_from(monkeypatch, caplog):
    monkeypatch.setattr(celery_mod.settings, "sendgrid_api_key", "key")
    monkeypatch.setattr(celery_mod.settings, "email_from_address", None)
    import logging
    with caplog.at_level(logging.WARNING, logger="app.celery_app"):
        _send_via_sendgrid("to@x.com", "s", "b")
    assert any("email_from_address" in r.message for r in caplog.records)


def test_send_via_sendgrid_sends_with_html_and_text(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "sendgrid_api_key", "SG.test")
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    sg_instance = MagicMock()
    with patch.object(celery_mod, "SendGridAPIClient", return_value=sg_instance) as sg_cls:
        _send_via_sendgrid("to@x.com", "subj", "plain", html_body="<b>hi</b>")
    sg_cls.assert_called_once_with("SG.test")
    sg_instance.send.assert_called_once()


def test_send_via_sendgrid_sends_text_only(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "sendgrid_api_key", "SG.test")
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    sg_instance = MagicMock()
    with patch.object(celery_mod, "SendGridAPIClient", return_value=sg_instance):
        _send_via_sendgrid("to@x.com", "subj", "plain")
    sg_instance.send.assert_called_once()


def test_send_via_sendgrid_sends_html_only(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "sendgrid_api_key", "SG.test")
    monkeypatch.setattr(celery_mod.settings, "email_from_address", "from@x.com")
    sg_instance = MagicMock()
    with patch.object(celery_mod, "SendGridAPIClient", return_value=sg_instance):
        _send_via_sendgrid("to@x.com", "subj", "", html_body="<b>only html</b>")
    sg_instance.send.assert_called_once()


# ---------------------------------------------------------------------------
# _send_email — dispatch + exception
# ---------------------------------------------------------------------------


def test_send_email_dispatches_to_sendgrid(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "email_mode", "sendgrid")
    called = []
    monkeypatch.setattr(
        celery_mod, "_send_via_sendgrid",
        lambda *a, **k: called.append(("sg", a, k)),
    )
    monkeypatch.setattr(
        celery_mod, "_send_via_smtp",
        lambda *a, **k: called.append(("smtp", a, k)),
    )
    _send_email("to@x.com", "s", "b", html_body="<i>x</i>")
    assert called and called[0][0] == "sg"


def test_send_email_dispatches_to_smtp(monkeypatch):
    monkeypatch.setattr(celery_mod.settings, "email_mode", "smtp")
    called = []
    monkeypatch.setattr(
        celery_mod, "_send_via_smtp",
        lambda *a, **k: called.append(("smtp", a, k)),
    )
    monkeypatch.setattr(
        celery_mod, "_send_via_sendgrid",
        lambda *a, **k: called.append(("sg", a, k)),
    )
    _send_email("to@x.com", "s", "b")
    assert called and called[0][0] == "smtp"


def test_send_email_reraises_on_exception(monkeypatch, caplog):
    monkeypatch.setattr(celery_mod.settings, "email_mode", "smtp")

    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(celery_mod, "_send_via_smtp", boom)
    import logging
    with caplog.at_level(logging.ERROR, logger="app.celery_app"):
        with pytest.raises(RuntimeError):
            _send_email("to@x.com", "s", "b")
    assert any("email_send_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# send_email_notification — kind branch + user_id branch
# ---------------------------------------------------------------------------


def _seed_confirmed_signup(db_session, *, email_tag=""):
    owner = make_user(db_session, email=f"owner_ce{email_tag}@example.com")
    _bind_factories(db_session)
    vol = VolunteerFactory(email=f"vol_ce{email_tag}@example.com")
    _, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    s = SignupFactory(volunteer=vol, slot=slot, status=models.SignupStatus.confirmed)
    db_session.flush()
    return s


def test_send_email_notification_unknown_kind_raises(
    db_session, monkeypatch, patch_session_local
):
    s = _seed_confirmed_signup(db_session, email_tag="uk")
    db_session.commit()
    with pytest.raises(ValueError, match="Unknown notification kind"):
        send_email_notification.run(signup_id=str(s.id), kind="not_a_real_kind")


def test_send_email_notification_kind_signup_missing_returns(
    db_session, monkeypatch, patch_session_local
):
    """Unknown signup_id with valid kind returns silently."""
    import uuid
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: None)
    send_email_notification.run(signup_id=str(uuid.uuid4()), kind="cancellation")


def test_send_email_notification_kind_dedup_skips_second_send(
    db_session, monkeypatch, patch_session_local
):
    s = _seed_confirmed_signup(db_session, email_tag="dd")
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    assert len(sends) == 1


def test_send_email_notification_user_id_path(
    db_session, monkeypatch, patch_session_local
):
    """Transactional user_id branch — no signup_id/kind, sends + creates Notification."""
    user = make_user(db_session, email="ce_user@example.com")
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_email_notification.run(
        user_id=str(user.id), subject="Hi", body="There",
    )
    assert len(sends) == 1
    db_session.expire_all()
    notif = db_session.query(models.Notification).filter_by(user_id=user.id).first()
    assert notif is not None
    assert notif.subject == "Hi"


def test_send_email_notification_user_id_none_returns(patch_session_local):
    """No user_id and no kind → silent return."""
    send_email_notification.run()


def test_send_email_notification_user_not_found(db_session, patch_session_local):
    import uuid
    send_email_notification.run(
        user_id=str(uuid.uuid4()), subject="x", body="y",
    )


def test_send_email_notification_user_with_email_off(
    db_session, monkeypatch, patch_session_local
):
    """notify_email=False → no email sent but Notification row still written."""
    user = make_user(db_session, email="ce_off@example.com")
    user.notify_email = False
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_email_notification.run(
        user_id=str(user.id), subject="S", body="B",
    )
    assert sends == []


def test_send_email_notification_daily_limit_blocks(
    db_session, monkeypatch, patch_session_local
):
    monkeypatch.setattr(celery_mod.settings, "resend_daily_limit", 1)
    _seed_n_sent_notifications(db_session, 1, kind_prefix="senlim")
    user = make_user(db_session, email="ce_lim@example.com")
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_email_notification.run(user_id=str(user.id), subject="S", body="B")
    assert sends == []


def test_send_email_notification_volunteer_no_email(
    db_session, monkeypatch, patch_session_local
):
    """Defensive: signup.volunteer.email empty → return without send."""
    s = _seed_confirmed_signup(db_session, email_tag="ne")
    s.volunteer.email = ""
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    assert sends == []


# ---------------------------------------------------------------------------
# weekly_digest
# ---------------------------------------------------------------------------


def test_weekly_digest_sends_grouped_by_volunteer(
    db_session, monkeypatch, patch_session_local
):
    s = _seed_confirmed_signup(db_session, email_tag="wd")
    s.slot.start_time = datetime.now(timezone.utc) + timedelta(days=2)
    s.slot.end_time = s.slot.start_time + timedelta(hours=2)
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    weekly_digest.run()
    assert len(sends) == 1
    assert sends[0][0] == s.volunteer.email
    assert "Weekly volunteer digest" in sends[0][1]


def test_weekly_digest_no_signups_in_window(
    db_session, monkeypatch, patch_session_local
):
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    weekly_digest.run()
    assert sends == []


# ---------------------------------------------------------------------------
# send_broadcast_email
# ---------------------------------------------------------------------------


def test_broadcast_email_sends(db_session, monkeypatch, patch_session_local):
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append((a, k)))
    send_broadcast_email.run(
        signup_id="abc", to_email="to@x.com",
        subject="hi", text_body="t", html_body="<b>h</b>",
    )
    assert len(sends) == 1


def test_broadcast_email_skips_no_to(db_session, monkeypatch, patch_session_local):
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_broadcast_email.run(
        signup_id="abc", to_email="", subject="s", text_body="t", html_body="<b/>",
    )
    assert sends == []


def test_broadcast_email_blocked_by_daily_limit(
    db_session, monkeypatch, patch_session_local
):
    monkeypatch.setattr(celery_mod.settings, "resend_daily_limit", 1)
    _seed_n_sent_notifications(db_session, 1, kind_prefix="bclim")
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))
    send_broadcast_email.run(
        signup_id="abc", to_email="to@x.com", subject="s", text_body="t", html_body="<b/>",
    )
    assert sends == []


# ---------------------------------------------------------------------------
# send_signup_confirmation_email
# ---------------------------------------------------------------------------


def test_signup_confirmation_email_sends(
    db_session, monkeypatch, patch_session_local
):
    s = _seed_confirmed_signup(db_session, email_tag="cf")
    db_session.commit()
    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append((a, k)))
    monkeypatch.setattr(
        celery_mod.settings, "frontend_url", "https://example.test", raising=False,
    )
    send_signup_confirmation_email.run(
        volunteer_id=str(s.volunteer.id),
        signup_ids=[str(s.id)],
        token="raw-token",
        event_id=str(s.slot.event_id),
    )
    assert len(sends) == 1


def test_signup_confirmation_email_debug_logs_token(
    db_session, monkeypatch, patch_session_local, caplog
):
    s = _seed_confirmed_signup(db_session, email_tag="cfd")
    db_session.commit()
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: None)
    monkeypatch.setattr(celery_mod.settings, "debug", True, raising=False)
    monkeypatch.setattr(
        celery_mod.settings, "frontend_url", "https://example.test", raising=False,
    )
    import logging
    with caplog.at_level(logging.DEBUG, logger="app.celery_app"):
        send_signup_confirmation_email.run(
            volunteer_id=str(s.volunteer.id),
            signup_ids=[str(s.id)],
            token="raw-debug-token",
            event_id=str(s.slot.event_id),
        )
    assert any("raw-debug-token" in r.message for r in caplog.records)


def test_signup_confirmation_email_missing_entity_returns(
    db_session, monkeypatch, patch_session_local
):
    import uuid as _uuid
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: None)
    send_signup_confirmation_email.run(
        volunteer_id=str(_uuid.uuid4()),
        signup_ids=[],
        token="t",
        event_id=str(_uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# Beat / RedBeat configuration invariants
# ---------------------------------------------------------------------------


def test_redbeat_lock_timeout_outlives_beat_loop_interval():
    """RedBeat extends its scheduler lock once per beat tick, and ticks can be
    up to beat_max_loop_interval (celery default 300s) apart. A lock TTL at or
    below that interval expires before the next extend, raising
    LockNotOwnedError and crash-looping the beat container. RedBeat's own
    default keeps a 5x safety ratio (lock_timeout = max_interval * 5)."""
    from celery.beat import DEFAULT_MAX_INTERVAL

    max_interval = celery_mod.celery.conf.beat_max_loop_interval or DEFAULT_MAX_INTERVAL
    assert celery_mod.celery.conf.redbeat_lock_timeout >= 5 * max_interval


# ---------------------------------------------------------------------------
# Release hardening — dedup marker durability, daily-cap accounting, and
# waitlist-promote copy
# ---------------------------------------------------------------------------


def test_send_marker_survives_post_send_failure(db_session, monkeypatch):
    """If the send succeeds but the session dies right after, the retry must
    NOT send a second email — the dedup marker has to be durable (committed)
    before the send happens."""
    s = _seed_confirmed_signup(db_session, email_tag="ms")
    db_session.commit()

    sends = []
    monkeypatch.setattr(celery_mod, "_send_email", lambda *a, **k: sends.append(a))

    class _FlakySession:
        """Proxies the test session; first commit AFTER a send raises."""

        def __init__(self, session):
            self._s = session
            self.exploded = False

        def __getattr__(self, name):
            return getattr(self._s, name)

        def commit(self):
            if sends and not self.exploded:
                self.exploded = True
                raise RuntimeError("connection lost after send")
            self._s.commit()

        def close(self):
            pass

    flaky = _FlakySession(db_session)
    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: flaky)

    try:
        send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    except RuntimeError:
        pass
    # What a real worker does between retries: the broken session is torn down.
    db_session.rollback()

    send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    assert len(sends) == 1, (
        f"retry after post-send session failure re-sent the email ({len(sends)} sends)"
    )


def test_send_failure_releases_marker(db_session, monkeypatch, patch_session_local):
    """If the send itself fails, the marker must not stick around — the retry
    has to be able to actually send."""
    s = _seed_confirmed_signup(db_session, email_tag="rf")
    db_session.commit()

    def _boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(celery_mod, "_send_email", _boom)
    with pytest.raises(RuntimeError, match="smtp down"):
        send_email_notification.run(signup_id=str(s.id), kind="cancellation")
    db_session.rollback()

    marker = (
        db_session.query(models.SentNotification)
        .filter(
            models.SentNotification.signup_id == s.id,
            models.SentNotification.kind == "cancellation",
        )
        .first()
    )
    assert marker is None, "failed send left a dedup marker — retries will never send"


def test_daily_send_limit_counts_transactional_notifications(db_session, monkeypatch):
    """The circuit breaker must count the user_id transactional path
    (Notification rows), not just the kind-based SentNotification path —
    otherwise real sends blow past the provider cap uncounted."""
    monkeypatch.setattr(celery_mod.settings, "resend_daily_limit", 5)
    user = make_user(db_session, email="cap_txn@example.com")
    now = datetime.now(timezone.utc)
    for i in range(5):
        db_session.add(models.Notification(
            user_id=user.id,
            type=models.NotificationType.email,
            subject=f"t{i}",
            body="b",
            delivery_method="email",
            delivered_at=now,
        ))
    db_session.flush()

    assert celery_mod._check_daily_send_limit(db_session) is False


def test_waitlist_promote_email_does_not_ask_to_confirm(db_session):
    """Promotees are already confirmed (promote_waitlist_fifo sets status
    directly) — the email must not tell them to 'confirm your spot'."""
    from app.emails import BUILDERS

    s = _seed_confirmed_signup(db_session, email_tag="wp")
    db_session.commit()

    payload = BUILDERS["waitlist_promote"](s)
    assert "confirm your spot" not in payload["subject"].lower()
    assert "waitlist" in payload["subject"].lower()
    assert "confirmed" in payload["subject"].lower()
