"""Regression coverage for the portals feature removal.

Portals (curated public event-collection links) were deleted outright: 0
rows in either table in the dev DB, no live UI entry point, and the public
`GET /portals/{slug}` endpoint leaked the staff `EventRead` schema to
anonymous callers. These tests pin that the routes are gone rather than
silently 404ing through some other catch-all, and that the model/schema
symbols were actually removed (not just unregistered).
"""
import pytest

from app import models, schemas


def test_public_portal_slug_route_is_gone(client):
    resp = client.get("/api/v1/portals/scitrek")
    assert resp.status_code == 404


def test_portals_list_route_is_gone(client):
    resp = client.get("/api/v1/portals/")
    assert resp.status_code == 404


def test_portal_attach_event_route_is_gone(client):
    resp = client.post("/api/v1/portals/some-id/events/some-event-id")
    assert resp.status_code == 404


@pytest.mark.parametrize("name", ["Portal", "PortalEvent"])
def test_portal_models_are_deleted(name):
    assert not hasattr(models, name)


@pytest.mark.parametrize("name", ["PortalBase", "PortalCreate", "PortalRead", "PortalDetail"])
def test_portal_schemas_are_deleted(name):
    assert not hasattr(schemas, name)
