"""K9 — only one thing is allowed to schedule reminders.

Phase 24 introduced ``app.tasks.reminders.check_and_send_reminders``, which
honours ``VolunteerPreference.email_reminders_enabled`` and quiet hours. The
pre-Phase-24 beats (``send_reminders_24h`` / ``send_reminders_1h``) were left
in the schedule. Two consequences, both live in production:

1. A volunteer with a slot tomorrow got two 24-hour reminder emails, because
   the two paths write different ``sent_notifications.kind`` values
   (``reminder_24h`` vs ``reminder_pre_24h``) and so never deduped each other.
2. Switching reminders off in the UI only silenced the Phase 24 path. The
   legacy tasks never read the preference row at all, so the opt-out did not
   work.

These tests pin the schedule, not the tasks — the task functions remain
defined and callable.
"""
import inspect

from app import celery_app as celery_mod
from app.services import reminder_service


def _schedule():
    return celery_mod.celery.conf.beat_schedule


def test_legacy_reminder_beats_are_not_scheduled():
    tasks = {entry["task"] for entry in _schedule().values()}
    assert "app.celery_app.send_reminders_24h" not in tasks
    assert "app.celery_app.send_reminders_1h" not in tasks


def test_phase_24_scan_is_the_only_scheduled_reminder_path():
    reminder_entries = [
        name
        for name, entry in _schedule().items()
        if "reminder" in entry["task"].lower()
    ]
    assert reminder_entries == ["check-reminders"]
    assert (
        _schedule()["check-reminders"]["task"]
        == "app.tasks.reminders.check_and_send_reminders"
    )


def test_the_surviving_path_is_the_one_that_can_be_opted_out_of():
    # The reason the legacy beats had to go rather than the new one: only
    # reminder_service reads the preference row before sending.
    kept = inspect.getsource(reminder_service.send_reminder)
    assert "email_reminders_enabled" in kept
    assert "opted_out" in kept

    for legacy in (celery_mod.send_reminders_24h, celery_mod.send_reminders_1h):
        dropped = inspect.getsource(legacy)
        assert "email_reminders_enabled" not in dropped


def test_legacy_tasks_still_exist_for_manual_use():
    # Removing the beats must not have removed the tasks; the audit only
    # called for unscheduling them.
    assert callable(celery_mod.send_reminders_24h)
    assert callable(celery_mod.send_reminders_1h)
