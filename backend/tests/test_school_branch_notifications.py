"""School-branch routing, signup dispatch, and admin email coverage."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app import celery_app as celery_mod
from app import models
from app.celery_app import send_admin_signup_notification_email
from app.emails import build_admin_signup_notification_email
from app.services.signup_notification_service import eligible_admin_ids_for_event
from tests.fixtures.helpers import make_user


GOOD_PHONE = "(213) 867-5309"


def _world(db, *, branch=models.SchoolBranch.high_school, slug=None):
    slug = slug or f"branch-{uuid.uuid4().hex[:10]}"
    module = models.Module(slug=slug, name="Branch <Module>", school_branch=branch)
    owner = make_user(db, role=models.UserRole.organizer)
    start = datetime.now(timezone.utc) + timedelta(days=2)
    event = models.Event(
        owner_id=owner.id,
        title="DNA <Lab>",
        start_date=start,
        end_date=start + timedelta(hours=4),
        visibility="public",
        module_slug=slug,
    )
    db.add_all([module, event])
    db.flush()
    slot = models.Slot(
        event_id=event.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        capacity=10,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
        date=start.date(),
    )
    db.add(slot)
    db.flush()
    return module, event, slot


def _admin(db, email, branch, *, active=True, notify=True, deleted=False):
    user = make_user(db, email=email, role=models.UserRole.admin)
    user.school_branch = branch
    user.is_active = active
    user.notify_email = notify
    if deleted:
        user.deleted_at = datetime.now(timezone.utc)
    db.flush()
    return user


def test_inclusive_routing_and_recipient_filters(db_session):
    module, event, _ = _world(db_session, branch=models.SchoolBranch.high_school)
    high = _admin(db_session, "high-route@example.com", models.SchoolBranch.high_school)
    both = _admin(db_session, "both-route@example.com", models.SchoolBranch.both)
    middle = _admin(db_session, "middle-route@example.com", models.SchoolBranch.middle_school)
    _admin(db_session, "off-route@example.com", models.SchoolBranch.high_school, notify=False)
    _admin(db_session, "inactive-route@example.com", models.SchoolBranch.high_school, active=False)
    _admin(db_session, "deleted-route@example.com", models.SchoolBranch.high_school, deleted=True)
    make_user(db_session, email="organizer-route@example.com", role=models.UserRole.organizer)

    assert set(eligible_admin_ids_for_event(db_session, event.id)) == {high.id, both.id}
    module.school_branch = models.SchoolBranch.middle_school
    db_session.flush()
    assert set(eligible_admin_ids_for_event(db_session, event.id)) == {middle.id, both.id}


def test_both_and_legacy_events_route_to_every_eligible_admin(db_session, caplog):
    high = _admin(db_session, "high-all@example.com", models.SchoolBranch.high_school)
    middle = _admin(db_session, "middle-all@example.com", models.SchoolBranch.middle_school)
    both = _admin(db_session, "both-all@example.com", models.SchoolBranch.both)
    _, both_event, _ = _world(db_session, branch=models.SchoolBranch.both)
    expected = {high.id, middle.id, both.id}
    assert set(eligible_admin_ids_for_event(db_session, both_event.id)) == expected

    owner = make_user(db_session, role=models.UserRole.organizer)
    start = datetime.now(timezone.utc) + timedelta(days=3)
    legacy = models.Event(
        owner_id=owner.id,
        title="Legacy",
        start_date=start,
        end_date=start + timedelta(hours=2),
        visibility="public",
        module_slug="missing-module",
    )
    db_session.add(legacy)
    db_session.flush()
    with caplog.at_level(logging.WARNING, logger="app.services.signup_notification_service"):
        assert set(eligible_admin_ids_for_event(db_session, legacy.id)) == expected
    assert "fallback_branch=both" in caplog.text


def test_admin_email_summary_contains_status_link_and_escaped_html(db_session, monkeypatch):
    module, event, slot = _world(db_session)
    admin = _admin(db_session, "summary-admin@example.com", models.SchoolBranch.high_school)
    volunteer = models.Volunteer(
        email="volunteer@example.com", first_name="A<lice", last_name="Smith"
    )
    db_session.add(volunteer)
    db_session.flush()
    signup = models.Signup(
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=models.SignupStatus.waitlisted,
    )
    db_session.add(signup)
    db_session.flush()
    monkeypatch.setattr(celery_mod.settings, "frontend_url", "https://scheduler.test")

    subject, text_body, html_body = build_admin_signup_notification_email(
        admin, volunteer, [signup], event, module
    )
    assert subject == "New signup — DNA <Lab>"
    assert "Waitlisted" in text_body
    assert f"/admin/events/{event.id}/roster" in text_body
    assert "DNA &lt;Lab&gt;" in html_body
    assert "A&lt;lice Smith" in html_body
    assert "DNA <Lab>" not in html_body


def test_public_submission_enqueues_one_summary_per_admin(
    client, db_session, monkeypatch
):
    _, event, first = _world(db_session)
    second = models.Slot(
        event_id=event.id,
        start_time=first.start_time + timedelta(hours=1),
        end_time=first.end_time + timedelta(hours=1),
        capacity=10,
        current_count=0,
        slot_type=models.SlotType.ORIENTATION,
        date=first.date,
    )
    db_session.add(second)
    high = _admin(db_session, "dispatch-high@example.com", models.SchoolBranch.high_school)
    both = _admin(db_session, "dispatch-both@example.com", models.SchoolBranch.both)
    db_session.commit()

    confirmations = []
    admin_tasks = []
    monkeypatch.setattr(
        celery_mod.send_signup_confirmation_email,
        "delay",
        lambda **kwargs: confirmations.append(kwargs),
    )
    monkeypatch.setattr(
        celery_mod.send_admin_signup_notification_email,
        "delay",
        lambda **kwargs: admin_tasks.append(kwargs),
    )
    response = client.post(
        "/api/v1/public/signups",
        json={
            "first_name": "Batch",
            "last_name": "Volunteer",
            "email": "batch@example.com",
            "phone": GOOD_PHONE,
            "slot_ids": [str(first.id), str(second.id)],
        },
    )
    assert response.status_code == 201, response.text
    assert len(confirmations) == 1
    assert {task["user_id"] for task in admin_tasks} == {str(high.id), str(both.id)}
    assert all(len(task["signup_ids"]) == 2 for task in admin_tasks)


def test_admin_enqueue_failure_does_not_undo_committed_signup(
    client, db_session, monkeypatch
):
    _, _, slot = _world(db_session)
    _admin(db_session, "enqueue-fail@example.com", models.SchoolBranch.high_school)
    db_session.commit()
    monkeypatch.setattr(celery_mod.send_signup_confirmation_email, "delay", lambda **_: None)

    def fail(**_kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(celery_mod.send_admin_signup_notification_email, "delay", fail)
    response = client.post(
        "/api/v1/public/signups",
        json={
            "first_name": "Committed",
            "last_name": "Volunteer",
            "email": "committed@example.com",
            "phone": GOOD_PHONE,
            "slot_ids": [str(slot.id)],
        },
    )
    assert response.status_code == 201, response.text
    assert db_session.query(models.Signup).count() == 1


def test_rejected_signup_enqueues_no_admin_alert(client, db_session, monkeypatch):
    _world(db_session)
    _admin(db_session, "rejected-admin@example.com", models.SchoolBranch.high_school)
    db_session.commit()
    admin_tasks = []
    monkeypatch.setattr(
        celery_mod.send_admin_signup_notification_email,
        "delay",
        lambda **kwargs: admin_tasks.append(kwargs),
    )
    response = client.post(
        "/api/v1/public/signups",
        json={
            "first_name": "Rejected",
            "last_name": "Volunteer",
            "email": "rejected@example.com",
            "phone": GOOD_PHONE,
            "slot_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 404
    assert admin_tasks == []


def test_worker_revalidates_and_records_notification(
    db_session, monkeypatch
):
    module, event, slot = _world(db_session)
    admin = _admin(db_session, "worker-admin@example.com", models.SchoolBranch.high_school)
    volunteer = models.Volunteer(
        email="worker-volunteer@example.com", first_name="Worker", last_name="Volunteer"
    )
    db_session.add(volunteer)
    db_session.flush()
    signup = models.Signup(
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=models.SignupStatus.pending,
    )
    db_session.add(signup)
    db_session.commit()

    class SessionProxy:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass

    sends = []
    monkeypatch.setattr(celery_mod, "SessionLocal", lambda: SessionProxy())
    monkeypatch.setattr(celery_mod, "_send_email", lambda *args, **kwargs: sends.append((args, kwargs)))
    monkeypatch.setattr(celery_mod.settings, "frontend_url", "https://scheduler.test")
    send_admin_signup_notification_email.run(
        user_id=str(admin.id),
        volunteer_id=str(volunteer.id),
        signup_ids=[str(signup.id)],
        shift_signup_ids=[],
        event_id=str(event.id),
    )
    assert len(sends) == 1
    notification = db_session.query(models.Notification).filter_by(user_id=admin.id).one()
    assert notification.subject == f"New signup — {event.title}"
    assert "Pending" in notification.body

    # Defensive worker exits are observable and never send: a provider cap,
    # an entity removed after enqueue, and a stale/empty booking batch.
    monkeypatch.setattr(celery_mod, "_check_daily_send_limit", lambda _db: False)
    send_admin_signup_notification_email.run(
        user_id=str(admin.id),
        volunteer_id=str(volunteer.id),
        signup_ids=[str(signup.id)],
        shift_signup_ids=[],
        event_id=str(event.id),
    )
    assert len(sends) == 1

    monkeypatch.setattr(celery_mod, "_check_daily_send_limit", lambda _db: True)
    send_admin_signup_notification_email.run(
        user_id=str(admin.id),
        volunteer_id=str(uuid.uuid4()),
        signup_ids=[str(signup.id)],
        shift_signup_ids=[],
        event_id=str(event.id),
    )
    assert len(sends) == 1

    send_admin_signup_notification_email.run(
        user_id=str(admin.id),
        volunteer_id=str(volunteer.id),
        signup_ids=[],
        shift_signup_ids=[],
        event_id=str(event.id),
    )
    assert len(sends) == 1

    # Revalidation happens at execution time: changing the account to a
    # non-matching branch prevents a queued task from sending.
    admin.school_branch = models.SchoolBranch.middle_school
    db_session.commit()
    send_admin_signup_notification_email.run(
        user_id=str(admin.id),
        volunteer_id=str(volunteer.id),
        signup_ids=[str(signup.id)],
        shift_signup_ids=[],
        event_id=str(event.id),
    )
    assert len(sends) == 1
