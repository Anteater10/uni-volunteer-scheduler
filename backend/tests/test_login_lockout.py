"""BASE-SEC-08: brute force must be bounded per account, not just per IP.

Login's only protection was 30 requests/minute per IP per path. Addresses are
cheap and home connections rotate theirs, so an attacker spread guesses across
many of them, stayed under the limit on each, and was never blocked — while the
account being attacked held no state recording that it was under attack. The
same limiter also fails open when Redis is unreachable (a deliberate trade so a
Redis outage cannot stop signups), which is precisely when a brute-force control
most needs to be running.

These tests pin the account-side control: the counter survives the failed
request, the lock engages at the threshold, the lock refuses even the correct
password, a success clears the state, and the reply never becomes an
account-existence oracle.
"""
from datetime import datetime, timedelta, timezone

from app import models
from app.config import settings
from tests.fixtures.helpers import make_user

PASSWORD = "correct-horse-battery-staple"


def _staff(db_session, email):
    return make_user(
        db_session,
        email=email,
        role=models.UserRole.admin,
        password=PASSWORD,
    )


def _attempt(client, email, password):
    return client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )


def test_a_failed_attempt_is_counted_and_survives_the_request(client, db_session):
    """The count has to be committed, or every attempt looks like the first.

    This is the whole bug: a counter incremented on a session that is discarded
    when the 401 is raised never reaches a threshold, so guessing stays
    unbounded no matter how high the threshold is.
    """
    user = _staff(db_session, "lockout-count@example.com")
    db_session.commit()

    assert _attempt(client, user.email, "wrong").status_code == 401

    db_session.expire_all()
    db_session.refresh(user)
    assert user.failed_login_count == 1
    assert user.last_failed_login_at is not None
    assert user.locked_until is None


def test_the_account_locks_at_the_threshold(client, db_session):
    user = _staff(db_session, "lockout-threshold@example.com")
    db_session.commit()

    for _ in range(settings.login_max_failed_attempts):
        assert _attempt(client, user.email, "wrong").status_code == 401

    db_session.expire_all()
    db_session.refresh(user)
    assert user.locked_until is not None
    assert user.locked_until > datetime.now(timezone.utc)
    # The counter resets with the lock: otherwise one attempt after the window
    # expires would immediately re-lock the account, permanently.
    assert user.failed_login_count == 0


def test_a_locked_account_refuses_even_the_correct_password(client, db_session):
    """The lock is the control. If the right password still works during it,
    an attacker who guesses correctly on attempt 11 has lost nothing."""
    user = _staff(db_session, "lockout-correct@example.com")
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    db_session.commit()

    resp = _attempt(client, user.email, PASSWORD)
    assert resp.status_code == 401
    # Byte-identical to a wrong password: a distinct "locked" reply would let an
    # attacker separate real staff addresses from invented ones.
    assert resp.json()["detail"] == "Incorrect email or password"


def test_an_expired_lock_lets_the_user_back_in(client, db_session):
    """locked_until is absolute, so it expires on its own with no sweeper."""
    user = _staff(db_session, "lockout-expired@example.com")
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert _attempt(client, user.email, PASSWORD).status_code == 200


def test_a_successful_login_clears_the_failure_state(client, db_session):
    """Staff who mistype twice and then get it right must not accumulate
    towards a lockout across weeks."""
    user = _staff(db_session, "lockout-clears@example.com")
    db_session.commit()

    assert _attempt(client, user.email, "wrong").status_code == 401
    assert _attempt(client, user.email, "wrong").status_code == 401
    assert _attempt(client, user.email, PASSWORD).status_code == 200

    db_session.expire_all()
    db_session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


def test_locking_writes_an_audit_row(client, db_session):
    """The login reply cannot say "locked" without becoming an existence
    oracle, so the audit log is the only way an admin learns this happened."""
    user = _staff(db_session, "lockout-audit@example.com")
    db_session.commit()

    for _ in range(settings.login_max_failed_attempts):
        _attempt(client, user.email, "wrong")

    rows = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "user_login_locked")
        .all()
    )
    assert len(rows) == 1
    assert str(rows[0].entity_id) == str(user.id)


def test_an_unknown_email_is_still_indistinguishable(client, db_session):
    """Per-account counting must not turn the endpoint into an oracle: an
    address with no account has nothing to count, and must look the same."""
    user = _staff(db_session, "lockout-oracle@example.com")
    db_session.commit()

    real = _attempt(client, user.email, "wrong")
    fake = _attempt(client, "no-such-person@example.com", "wrong")

    assert real.status_code == fake.status_code == 401
    assert real.json()["detail"] == fake.json()["detail"]
