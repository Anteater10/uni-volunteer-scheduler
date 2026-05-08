"""Phase 24 — volunteer_preferences service + API tests."""
from app import models
from app.services import reminder_service


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
