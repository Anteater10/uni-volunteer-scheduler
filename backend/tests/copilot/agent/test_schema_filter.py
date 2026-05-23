import pytest
from app.copilot.agent.boundary.schema_filter import apply


def test_strips_unlisted_top_level_fields():
    row = {"id": 1, "name": "Sarah", "email": "s@x.com"}
    out = apply(row, allowed_fields=["id", "name"])
    assert out == {"id": 1, "name": "Sarah"}


def test_strips_unlisted_fields_in_list_of_dicts():
    rows = [{"id": 1, "name": "A", "phone": "555"}, {"id": 2, "name": "B", "phone": "666"}]
    out = apply(rows, allowed_fields=["id", "name"])
    assert out == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]


def test_preserves_nested_structure_when_listed():
    row = {"id": 1, "module": {"name": "Forces", "owner_id": 47}}
    out = apply(row, allowed_fields=["id", "module.name"])
    assert out == {"id": 1, "module": {"name": "Forces"}}


def test_empty_result_when_nothing_allowed():
    assert apply({"x": 1}, allowed_fields=[]) == {}
