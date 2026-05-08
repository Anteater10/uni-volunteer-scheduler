"""/admin/audit-logs humanized response — Phase 16 Plan 02 (D-19 / D-34)."""
from app import models
from tests.fixtures.helpers import auth_headers, make_user


def test_audit_logs_list_rows_are_humanized(client, db_session):
    admin = make_user(
        db_session, email="humz-admin@example.com", role=models.UserRole.admin
    )
    # Create a target row the humanize service can resolve.
    target = make_user(
        db_session, email="humz-target@example.com", role=models.UserRole.organizer
    )
    # Directly insert a user_deactivate audit row so it has stable labels.
    row = models.AuditLog(
        actor_id=admin.id,
        action="user_deactivate",
        entity_type="User",
        entity_id=str(target.id),
        extra={},
    )
    db_session.add(row)
    db_session.commit()

    headers = auth_headers(client, admin)
    resp = client.get("/api/v1/admin/audit-logs?page=1&page_size=50", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body and "total" in body and "pages" in body

    # Find the row we inserted.
    matching = [r for r in body["items"] if r.get("action") == "user_deactivate"]
    assert matching, "expected at least one humanized user_deactivate row"
    row0 = matching[0]
    for key in ("action_label", "actor_label", "actor_role", "entity_label"):
        assert key in row0, f"missing humanized key: {key}"
    assert row0["action_label"] == "Deactivated a user"
    assert row0["actor_role"] == "admin"
    # entity_label should resolve to the target user's name/email
    assert "humz-target" in row0["entity_label"] or row0["entity_label"]


def test_audit_logs_csv_export_has_humanized_headers(client, db_session):
    admin = make_user(
        db_session, email="humz-csv-admin@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/audit-logs.csv", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    first_line = resp.text.splitlines()[0]
    for col in ("When", "Who", "Role", "What", "Target", "Raw Action", "Entity ID"):
        assert col in first_line, f"missing humanized CSV column: {col}"
