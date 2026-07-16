"""Phase 24 — volunteer_preferences service + API tests."""
import os
import threading
import time
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import reminder_service

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs",
)


def test_get_preferences_upserts_default_row(db_session):
    email = "newvolunteer@example.com"
    pref = reminder_service.get_preferences(db_session, email)
    assert pref.volunteer_email == email
    assert pref.email_reminders_enabled is True
    assert pref.sms_opt_in is False

    # Second call returns the same row (no duplicate)
    pref2 = reminder_service.get_preferences(db_session, email)
    assert pref2.volunteer_email == email
    rows = (
        db_session.query(models.VolunteerPreference)
        .filter(models.VolunteerPreference.volunteer_email == email)
        .all()
    )
    assert len(rows) == 1


def test_update_preferences_toggles_email_reminders(db_session):
    email = "toggle@example.com"
    pref = reminder_service.update_preferences(
        db_session, email, email_reminders_enabled=False
    )
    assert pref.email_reminders_enabled is False
    pref2 = reminder_service.update_preferences(
        db_session, email, email_reminders_enabled=True
    )
    assert pref2.email_reminders_enabled is True


def test_update_preferences_sets_phone_and_sms(db_session):
    email = "sms@example.com"
    pref = reminder_service.update_preferences(
        db_session, email, sms_opt_in=True, phone_e164="+15551234567"
    )
    assert pref.sms_opt_in is True
    assert pref.phone_e164 == "+15551234567"


def test_concurrent_get_preferences_race_creates_single_row():
    """Two clients racing the get-or-create for a brand-new volunteer must both
    get the row back with no error.

    Reproduces the manage-page double-fetch (React StrictMode fires the mount
    effect twice in dev builds): both requests SELECT-miss, both INSERT the
    same primary key, and the loser used to die on a duplicate-PK
    IntegrityError — surfaced as a 500 on GET /public/preferences.

    Deterministic interleave on real Postgres (separate connection per session,
    like test_concurrent_check_in.py):
      1. winner runs get_preferences — row flushed but NOT committed
      2. loser (thread) runs get_preferences — its SELECT misses (winner is
         uncommitted, MVCC), its INSERT blocks on the PK index
      3. winner commits — the loser's INSERT resolves against the now-taken PK
    """
    engine = create_engine(TEST_DATABASE_URL, pool_size=4, max_overflow=2)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"

    winner_session = SessionLocal()
    result = {}

    def loser():
        session = SessionLocal()
        try:
            pref = reminder_service.get_preferences(session, email)
            session.commit()
            result["email"] = pref.volunteer_email
        except Exception as exc:
            session.rollback()
            result["error"] = repr(exc)
        finally:
            session.close()

    try:
        winner_pref = reminder_service.get_preferences(winner_session, email)
        thread = threading.Thread(target=loser)
        thread.start()
        # Give the loser time to SELECT-miss and block on the PK index; its
        # INSERT cannot resolve until the winner commits (Postgres lock).
        time.sleep(0.5)
        winner_session.commit()
        thread.join(timeout=10)

        assert result.get("error") is None, f"loser errored: {result['error']}"
        assert result.get("email") == email
        assert winner_pref.volunteer_email == email
        with SessionLocal() as check:
            rows = (
                check.query(models.VolunteerPreference)
                .filter(models.VolunteerPreference.volunteer_email == email)
                .all()
            )
            assert len(rows) == 1
    finally:
        winner_session.close()
        with SessionLocal() as cleanup:
            cleanup.query(models.VolunteerPreference).filter(
                models.VolunteerPreference.volunteer_email == email
            ).delete()
            cleanup.commit()
        engine.dispose()
