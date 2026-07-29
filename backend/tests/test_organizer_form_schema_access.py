"""Organizer access to the two form-schema editors.

Both endpoints were admin-only while the buttons that call them sat on
organizer-visible pages, so an organizer could open the "Form fields" drawer,
make edits and only discover on save that they were not allowed. Neither had
any test at all — these pin the widened rule, and the participant cases keep it
from drifting into "any authenticated user".
"""
from app import models
from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

SCHEMA = [
    {
        "id": "dietary_needs",
        "label": "Dietary needs",
        "type": "text",
        "required": False,
        "order": 0,
    }
]


def _headers(client, db_session, role, email):
    user = make_user(db_session, email=email, role=role)
    db_session.commit()
    return auth_headers(client, user)


class TestEventFormSchema:
    def test_organizer_can_set_event_form_schema(self, client, db_session):
        owner = make_user(db_session, email="owner-fs@example.com", role=models.UserRole.admin)
        event, _ = make_event_with_slot(db_session, owner=owner)
        db_session.commit()
        headers = _headers(client, db_session, models.UserRole.organizer, "org-fs@example.com")

        resp = client.put(
            f"/api/v1/admin/events/{event.id}/form-schema",
            json={"schema": SCHEMA},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        # Read back through the public signup form — the only GET for a
        # resolved event schema — so the assertion covers what a volunteer
        # would actually be asked.
        got = client.get(f"/api/v1/public/events/{event.id}/form-schema")
        assert got.status_code == 200, got.text
        ids = [f["id"] for f in got.json()["schema"]]
        assert "dietary_needs" in ids

    def test_organizer_can_clear_event_form_schema(self, client, db_session):
        owner = make_user(db_session, email="owner-fs2@example.com", role=models.UserRole.admin)
        event, _ = make_event_with_slot(db_session, owner=owner)
        db_session.commit()
        headers = _headers(client, db_session, models.UserRole.organizer, "org-fs2@example.com")

        client.put(
            f"/api/v1/admin/events/{event.id}/form-schema",
            json={"schema": SCHEMA},
            headers=headers,
        )
        resp = client.put(
            f"/api/v1/admin/events/{event.id}/form-schema",
            json={"schema": None},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    def test_participant_cannot_set_event_form_schema(self, client, db_session):
        owner = make_user(db_session, email="owner-fs3@example.com", role=models.UserRole.admin)
        event, _ = make_event_with_slot(db_session, owner=owner)
        db_session.commit()
        headers = _headers(
            client, db_session, models.UserRole.participant, "part-fs@example.com"
        )

        resp = client.put(
            f"/api/v1/admin/events/{event.id}/form-schema",
            json={"schema": SCHEMA},
            headers=headers,
        )
        assert resp.status_code == 403


class TestTemplateDefaultFormSchema:
    def _make_template(self, client, db_session, slug="fs-module"):
        admin_headers = _headers(
            client, db_session, models.UserRole.admin, f"admin-{slug}@example.com"
        )
        resp = client.post(
            "/api/v1/admin/modules",
            json={
                "slug": slug,
                "name": "Form schema module",
                "type": "module",
                "session_count": 1,
            },
            headers=admin_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return slug

    def test_organizer_can_set_template_default_schema(self, client, db_session):
        # The rest of the module-template routes already admit organizers,
        # including delete — editing questions was the lone exception.
        slug = self._make_template(client, db_session)
        headers = _headers(
            client, db_session, models.UserRole.organizer, "org-tfs@example.com"
        )

        resp = client.put(
            f"/api/v1/admin/modules/{slug}/default-form-schema",
            json={"schema": SCHEMA},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    def test_participant_cannot_set_template_default_schema(self, client, db_session):
        slug = self._make_template(client, db_session, slug="fs-module-2")
        headers = _headers(
            client, db_session, models.UserRole.participant, "part-tfs@example.com"
        )

        resp = client.put(
            f"/api/v1/admin/modules/{slug}/default-form-schema",
            json={"schema": SCHEMA},
            headers=headers,
        )
        assert resp.status_code == 403
