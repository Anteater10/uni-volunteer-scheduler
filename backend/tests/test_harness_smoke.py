def test_harness_collects(client):
    r = client.get("/api/v1/health")
    assert r.status_code in (200, 404)  # route may not exist yet; collection is what we verify
